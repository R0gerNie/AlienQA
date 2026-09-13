"""Evidence Deduplicator 测试：两级聚类、确定性 embed、两模式、回写、severity 取最高。"""
import io

from PIL import Image

from alienqa.dedup import Deduplicator
from alienqa.evidence import Evidence, Severity


def _png_bytes(blank=True):
    im = Image.new("L", (64, 64), 255 if blank else 0)
    if not blank:
        for y in range(64):
            for x in range(32, 64):
                im.putpixel((x, y), 255)  # 左黑右白，与纯白图明显不同
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _ev(ev_id, exp, obs, classification, url, severity=Severity.MINOR, replay=None, artifacts=None):
    return Evidence(
        id=ev_id,
        expectation=exp,
        observation_summary=obs,
        classification=classification,
        severity=severity,
        replay=replay or {"url": url},
        artifacts=artifacts or {},
    )


# ---- 硬聚类 ----

def test_hard_cluster_same_page_same_type():
    evs = [
        _ev("EV-1", "a", "a", "technical_bug", "http://x/orders", replay={"url": "http://x/orders", "console": ["e"]}),
        _ev("EV-2", "b", "b", "technical_bug", "http://x/orders", replay={"url": "http://x/orders", "console": ["e"]}),
    ]
    issues = Deduplicator().cluster(evs)
    assert len(issues) == 1  # 同页面+同异常桶，即使文本不同也归并
    assert set(issues[0].evidence_ids) == {"EV-1", "EV-2"}


# ---- 软聚类（验收：5 条白屏跨页面归并） ----

def test_soft_cluster_blank_screens_cross_page(tmp_path):
    blank = _png_bytes(blank=True)
    evs = []
    for i in range(5):
        p = tmp_path / f"after{i}.png"
        p.write_bytes(blank)
        evs.append(_ev(
            f"EV-{i:03d}", "页面白屏无内容", "白屏", "technical_bug",
            f"http://x/p{i}", artifacts={"after": str(p)},
        ))
    issues = Deduplicator().cluster(evs)
    assert len(issues) == 1
    assert len(issues[0].evidence_ids) == 5


def test_no_merge_different_root_cause(tmp_path):
    blank = tmp_path / "blank.png"
    blank.write_bytes(_png_bytes(blank=True))
    pattern = tmp_path / "pattern.png"
    pattern.write_bytes(_png_bytes(blank=False))
    evs = [
        _ev("EV-1", "页面白屏无内容", "白屏", "technical_bug", "http://x/p1", artifacts={"after": str(blank)}),
        _ev("EV-2", "保存后应有提示", "无反馈", "missing_feedback", "http://x/p2", artifacts={"after": str(pattern)}),
    ]
    issues = Deduplicator().cluster(evs)
    assert len(issues) == 2


# ---- embed 确定性 / LLM 模式 ----

def test_embed_deterministic(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(_png_bytes(True))
    e = _ev("EV-1", "白屏", "白屏", "technical_bug", "http://x", artifacts={"after": str(p)})
    d = Deduplicator()
    v1, v2 = d.embed(e), d.embed(e)
    assert v1.text_grams == v2.text_grams
    assert v1.screenshot_hash == v2.screenshot_hash
    assert v1.screenshot_hash is not None


def test_llm_mode_embedding():
    def embed_func(text):
        return [1.0, 0.0] if "白屏" in text else [0.0, 1.0]

    d = Deduplicator(mode="llm", embed_func=embed_func, text_threshold=0.9)
    evs = [
        _ev("EV-1", "页面白屏", "白屏", "technical_bug", "http://x/p1"),
        _ev("EV-2", "页面白屏", "白屏", "technical_bug", "http://x/p2"),
    ]
    issues = d.cluster(evs)
    assert len(issues) == 1


# ---- Issue 生成与回写 ----

def test_issue_severity_takes_max():
    evs = [
        _ev("EV-1", "a", "a", "technical_bug", "http://x", severity=Severity.MINOR,
            replay={"url": "http://x", "console": ["e"]}),
        _ev("EV-2", "b", "b", "technical_bug", "http://x", severity=Severity.CRITICAL,
            replay={"url": "http://x", "console": ["e"]}),
    ]
    issues = Deduplicator().cluster(evs)
    assert len(issues) == 1
    assert issues[0].severity == Severity.CRITICAL


def test_issue_id_written_back(tmp_path):
    blank = tmp_path / "b.png"
    blank.write_bytes(_png_bytes(True))
    evs = [
        _ev("EV-001", "页面白屏", "白屏", "technical_bug", "http://x/p1", artifacts={"after": str(blank)}),
        _ev("EV-002", "页面白屏", "白屏", "technical_bug", "http://x/p2", artifacts={"after": str(blank)}),
    ]
    issues = Deduplicator().cluster(evs)
    assert len(issues) == 1
    assert evs[0].issue_id == "ISSUE-001"
    assert evs[1].issue_id == "ISSUE-001"
