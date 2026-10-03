"""Deduplicator：两级聚类把 Evidence 归并为 Issue（并查集）。"""
from alienqa.i18n import t as tr

from pathlib import Path
import json

from ..evidence.models import Severity
from .models import Issue, Vector
from .similarity import ahash, cosine, hamming, text_jaccard
from ..replay.signals import signal_key

_SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.MAJOR: 3,
    Severity.MINOR: 2,
    Severity.TRIVIAL: 1,
}


class Deduplicator:
    def __init__(
        self,
        mode="deterministic",
        text_threshold=0.5,
        hash_threshold=8,
        embed_func=None,
        embed_model="text-embedding-3-small",
    ):
        self.mode = mode  # "deterministic" | "llm"
        self.text_threshold = text_threshold
        self.hash_threshold = hash_threshold
        self.embed_func = embed_func  # llm 模式可注入，便于测试
        self.embed_model = embed_model

    def embed(self, evidence) -> Vector:
        """把 Evidence 编码成向量（deterministic：2-gram + aHash；llm：文本向量 + aHash）。"""
        vec = Vector()
        if self.mode == "llm":
            vec.text_vec = tuple(self._llm_embed(_evidence_text(evidence)))
        else:
            vec.text_grams = frozenset(_char_bigrams(_evidence_text(evidence)))
        vec.screenshot_hash = _screenshot_hash(evidence)
        return vec

    def cluster(self, evidences) -> list:
        """两级聚类：硬聚类（页面+异常桶）→ 软聚类（文本+截图）→ Issue。"""
        n = len(evidences)
        if n == 0:
            return []
        parent = list(range(n))
        vectors = [self.embed(e) for e in evidences]
        # ① 硬聚类只归并同页、同类且完整技术信号相同的记录。
        groups = {}
        for i, e in enumerate(evidences):
            key = _hard_key(e)
            if key is None:
                continue
            if key in groups:
                _union(parent, groups[key], i)
            else:
                groups[key] = i
        # ② 软聚类：跨硬组按相似度合并
        for i in range(n):
            for j in range(i + 1, n):
                if evidences[i].finding_kind != evidences[j].finding_kind:
                    continue
                if evidences[i].finding_kind is not None:
                    # Modern records never merge on prose/screenshot resemblance alone.
                    if evidences[i].finding_kind != "cognitive_mismatch" or _cognitive_key(evidences[i]) != _cognitive_key(evidences[j]):
                        continue
                if _find(parent, i) == _find(parent, j):
                    continue
                if self._similar(vectors[i], vectors[j]):
                    _union(parent, i, j)
        # 连通分量 → Issue
        comps = {}
        for i in range(n):
            comps.setdefault(_find(parent, i), []).append(i)
        issues = []
        # Keep existing view IDs where possible; new groups use an unused number.
        used = set(e.issue_id for e in evidences if e.issue_id)
        assigned = set()
        for issue_no, members in enumerate(sorted(comps.values(), key=lambda m: min(m)), start=1):
            issue = self._make_issue(issue_no, members, evidences)
            existing = sorted({evidences[i].issue_id for i in members if evidences[i].issue_id} - assigned)
            if existing:
                issue.id = existing[0]
            else:
                number = 1
                while f"ISSUE-{number:03d}" in used | assigned:
                    number += 1
                issue.id = f"ISSUE-{number:03d}"
            assigned.add(issue.id)
            for i in members:
                evidences[i].issue_id = issue.id
            issues.append(issue)
        return issues

    # ---- 内部 ----

    def _similar(self, a: Vector, b: Vector) -> bool:
        if self.mode == "llm" and a.text_vec and b.text_vec:
            text_ok = cosine(a.text_vec, b.text_vec) >= self.text_threshold
        else:
            text_ok = text_jaccard(a.text_grams, b.text_grams) >= self.text_threshold
        if a.screenshot_hash is not None and b.screenshot_hash is not None:
            hash_ok = hamming(a.screenshot_hash, b.screenshot_hash) <= self.hash_threshold
        else:
            hash_ok = True  # 缺截图时只靠文本
        return text_ok and hash_ok

    def _llm_embed(self, text: str) -> list:
        if self.embed_func is not None:
            return list(self.embed_func(text) or [])
        import litellm

        resp = litellm.embedding(model=self.embed_model, input=[text])
        data = getattr(resp, "data", None) or []
        if data:
            item = data[0]
            if isinstance(item, dict):
                return list(item.get("embedding") or [])
            return list(getattr(item, "embedding", []) or [])
        return []

    def _make_issue(self, issue_no, members, evidences) -> Issue:
        evs = sorted(
            (evidences[i] for i in members),
            key=lambda e: _SEVERITY_RANK.get(e.severity, 0),
            reverse=True,
        )
        top = evs[0]
        title = (top.expectation or top.observation_summary or tr("未命名问题"))[:60]
        return Issue(
            id=f"ISSUE-{issue_no:03d}",
            title=title,
            evidence_ids=sorted(e.id for e in evs),
            root_cause_candidate="",
            severity=top.severity,
            grouping_basis=tr("相同页面、动作和具体技术事实") if top.finding_kind == "technical_anomaly" and _hard_key(top) else
                           tr("相同原预期、依据和动作的组织候选") if top.finding_kind == "cognitive_mismatch" else
                           tr("独立证据") if len(evs) == 1 else tr("旧记录相似度组织候选；未证明共同根因"),
        )


# ---- 模块级辅助 ----

def _evidence_text(evidence) -> str:
    return " ".join(p for p in (evidence.expectation, evidence.observation_summary, evidence.reasoning) if p)


def _char_bigrams(text) -> set:
    t = "".join(text.split())
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _hard_key(evidence) -> tuple | None:
    replay = evidence.replay or {}
    page = replay.get("final_url") or replay.get("url") or ""
    if evidence.finding_kind is not None:
        if evidence.finding_kind != "technical_anomaly":
            return None
        records = replay.get("source_signals") or []
        facts = [signal_key(record) for record in records]
        if not page or not facts or any(fact is None for fact in facts):
            return None
        return page, evidence.finding_kind, _action_key(evidence), tuple(sorted(facts))
    signals = tuple((key, tuple(sorted(str(s) for s in replay.get(key) or [])))
                    for key in ("console", "network", "js_exceptions") if replay.get(key))
    http = tuple(sorted((str(k), str(v)) for k, v in (replay.get("http_status") or {}).items()))
    if not page or not (signals or http) or evidence.classification != "technical_bug":
        return None
    return page, evidence.finding_kind, evidence.classification, signals, http


def _action_key(evidence):
    return json.dumps(evidence.action or {}, sort_keys=True, ensure_ascii=False)


def _cognitive_key(evidence):
    replay = evidence.replay or {}
    return (replay.get("final_url") or replay.get("url"), _action_key(evidence), evidence.expectation,
            json.dumps(evidence.expectation_basis, sort_keys=True, ensure_ascii=False))


def _screenshot_hash(evidence) -> int | None:
    artifacts = evidence.artifacts or {}
    path = artifacts.get("after") or artifacts.get("before")
    if not path:
        return None
    try:
        return ahash(Path(path).read_bytes())
    except OSError:
        return None


def _find(parent, i):
    while parent[i] != i:
        parent[i] = parent[parent[i]]
        i = parent[i]
    return i


def _union(parent, a, b):
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[rb] = ra
