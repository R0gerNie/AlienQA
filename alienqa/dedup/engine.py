"""Deduplicator：两级聚类把 Evidence 归并为 Issue（并查集）。"""
from pathlib import Path

from ..evidence.models import Severity
from .models import Issue, Vector
from .similarity import ahash, cosine, hamming, text_jaccard

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
        # ① 硬聚类：同页面 + 同异常类型直接归并
        groups = {}
        for i, e in enumerate(evidences):
            key = _hard_key(e)
            if key in groups:
                _union(parent, groups[key], i)
            else:
                groups[key] = i
        # ② 软聚类：跨硬组按相似度合并
        for i in range(n):
            for j in range(i + 1, n):
                if _find(parent, i) == _find(parent, j):
                    continue
                if self._similar(vectors[i], vectors[j]):
                    _union(parent, i, j)
        # 连通分量 → Issue
        comps = {}
        for i in range(n):
            comps.setdefault(_find(parent, i), []).append(i)
        issues = []
        for issue_no, members in enumerate(sorted(comps.values(), key=lambda m: min(m)), start=1):
            issue = self._make_issue(issue_no, members, evidences)
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
        title = (top.expectation or top.observation_summary or "未命名问题")[:60]
        return Issue(
            id=f"ISSUE-{issue_no:03d}",
            title=title,
            evidence_ids=sorted(e.id for e in evs),
            root_cause_candidate="",
            severity=top.severity,
        )


# ---- 模块级辅助 ----

def _evidence_text(evidence) -> str:
    return " ".join(p for p in (evidence.expectation, evidence.observation_summary, evidence.reasoning) if p)


def _char_bigrams(text) -> set:
    t = "".join(text.split())
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _hard_key(evidence) -> tuple:
    replay = evidence.replay or {}
    page = replay.get("url", "") or ""
    if evidence.classification == "technical_bug":
        if replay.get("console"):
            bucket = "console"
        elif replay.get("network"):
            bucket = "network"
        else:
            bucket = "technical"
    else:
        bucket = evidence.classification
    return (page, bucket)


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
