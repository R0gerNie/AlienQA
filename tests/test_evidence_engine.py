"""Evidence Engine 测试：4 级严重度、全量枚举、分类、置信度、落盘。"""
from alienqa.driver import Action, Target
from alienqa.evidence import EvidenceEngine, EvidenceStore, Severity, assess_severity, classify, confidence
from alienqa.expectation import ExpectationMismatch, MismatchLevel
from alienqa.observation import Observation, RuntimeObservation, VisualObservation


def _mismatch(level=MismatchLevel.HIGH, exp="点保存应有提示", obs="无反应", reason="r"):
    return ExpectationMismatch(expectation=exp, observation=obs, level=level, reasoning=reason)


def _observation(blank=0.0, console=None, js=None, http=None, net=None):
    return Observation(
        before_image=b"a",
        after_image=b"b",
        visual=VisualObservation(blank_screen_score=blank),
        runtime=RuntimeObservation(
            console_errors=console or [],
            js_exceptions=js or [],
            http_status=http or {},
            network_failures=net or [],
        ),
    )


class _FakeDriver:
    def replay_data(self):
        return {
            "browser": "chromium",
            "viewport": {"width": 1280, "height": 800},
            "url": "http://x/orders",
            "action_sequence": [],
        }

    def storage_state(self):
        return {"cookies": [{"name": "session"}]}


# ---- 4 级严重度 ----

def test_severity_critical_blank_screen():
    assert assess_severity(_mismatch(), _observation(blank=0.9)) == Severity.CRITICAL


def test_severity_major_on_console_error():
    assert assess_severity(_mismatch(level=MismatchLevel.LOW), _observation(console=["err"])) == Severity.MAJOR


def test_severity_minor_on_medium_mismatch():
    assert assess_severity(_mismatch(level=MismatchLevel.MEDIUM), _observation()) == Severity.MINOR


def test_severity_trivial_on_low_mismatch():
    assert assess_severity(_mismatch(level=MismatchLevel.LOW), _observation()) == Severity.TRIVIAL


def test_confidence_increases_with_signals():
    base = confidence(_mismatch(), _observation())
    strong = confidence(_mismatch(), _observation(console=["e"], net=["n"], blank=0.9))
    assert strong > base
    assert 0.1 <= strong <= 0.95


# ---- 分类 ----

def test_classify_technical_bug():
    c = classify(_mismatch(), _observation(js=["TypeError"], http={"/api": 500}), None)
    assert c == "technical_bug"


def test_classify_false_affordance():
    """长得像按钮、点了没反应、可能不是按钮 → 也应进 evidence（ux_ambiguity）。"""
    m = _mismatch(
        level=MismatchLevel.MEDIUM,
        exp="点击那个像按钮的卡片应有反应",
        obs="点击后无任何反应",
        reason="它看起来可点击",
    )
    c = classify(m, _observation(), Action("click", Target(text="卡片")))
    assert c == "ux_ambiguity"


# ---- 全量枚举 ----

def test_build_enumerates_all_mismatches(tmp_path):
    store = EvidenceStore(db_path=str(tmp_path / "evidence.db"))
    engine = EvidenceEngine(artifacts_dir=str(tmp_path / "artifacts"), store=store)
    mismatches = [
        _mismatch(),
        _mismatch(level=MismatchLevel.LOW, exp="x"),
        _mismatch(level=MismatchLevel.MEDIUM, exp="y"),
    ]
    evs = engine.build(mismatches, _observation(), Action("click", Target(text="保存")), None, _FakeDriver())
    assert len(evs) == 3  # 一条不漏
    assert [e.id for e in evs] == ["EV-00001", "EV-00002", "EV-00003"]
    assert all(e.is_complete() for e in evs)
    assert (tmp_path / "artifacts" / "EV-00001" / "before.png").exists()
    assert (tmp_path / "artifacts" / "EV-00001" / "technical.json").exists()


def test_evidence_action_and_replay(tmp_path):
    store = EvidenceStore(db_path=str(tmp_path / "evidence.db"))
    engine = EvidenceEngine(artifacts_dir=str(tmp_path / "artifacts"), store=store)
    evs = engine.build([_mismatch()], _observation(), Action("click", Target(text="保存")), None, _FakeDriver())
    ev = evs[0]
    assert ev.action == {"type": "click", "target": {"text": "保存", "selector": ""}}
    assert ev.replay["url"] == "http://x/orders"
    assert ev.replay["cookies"] == [{"name": "session"}]
    assert "console" in ev.replay


# ---- 落盘 ----

def test_persist_writes_db(tmp_path):
    store = EvidenceStore(db_path=str(tmp_path / "evidence.db"))
    engine = EvidenceEngine(artifacts_dir=str(tmp_path / "artifacts"), store=store)
    evs = engine.build([_mismatch()], _observation(), None, None, None)
    engine.persist(evs[0])
    assert store.all_ids() == ["EV-00001"]
