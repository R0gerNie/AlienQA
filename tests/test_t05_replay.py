"""T05: prerequisites, target-window facts and conservative result states."""
import json

import pytest

from alienqa.driver import RuntimeSignals
from alienqa.evidence import Evidence
from alienqa.replay import ReplayEngine
from test_replay_engine import _FakeDriver, _png


def package(tmp_path, fake, **replay):
    engine = ReplayEngine(tmp_path / "replay", driver_factory=lambda: fake)
    engine.save(Evidence(id="EV-1", finding_kind="technical_anomaly", replay={
        "url": "http://x/entry?q=1#tab", "package_version": 2,
        "target_window": {"phase": "entry", "step_id": None}, **replay,
    }))
    return engine


def fact(kind="page_error", **payload):
    return {"record_id": "original:R-1", "kind": kind, "payload": payload}


@pytest.mark.parametrize("content", [None, "{bad", "[]", '{"replay": []}'])
def test_bad_package_has_result(tmp_path, content):
    engine = ReplayEngine(tmp_path)
    if content is not None:
        (tmp_path / "EV-1.json").write_text(content)
    result = engine.replay("EV-1")
    assert result.status == "failed"
    assert result.phase == "package"


def test_missing_start_never_uses_final_url(tmp_path):
    engine = package(tmp_path, _FakeDriver(_png()), url="", final_url="http://x/final")
    assert engine.replay("EV-1").status == "failed"


def test_entry_specific_signal_without_image(tmp_path):
    signal = "TypeError: startup settings widget unavailable"
    runtime = RuntimeSignals()
    runtime.record("page_error", {"message": signal})
    fake = _FakeDriver(_png(), runtime)
    result = package(tmp_path, fake, source_signals=[fact(message=signal)]).replay("EV-1")
    assert result.status == "reproduced"
    assert result.matched_basis[0]["kind"] == "page_error"
    assert fake.actions == []


def test_same_picture_without_original_technical_fact_is_not_recurrence(tmp_path):
    fake = _FakeDriver(_png())
    engine = package(tmp_path, fake, source_signals=[fact(message="TypeError: original handler unavailable")])
    image = tmp_path / "after.png"
    image.write_bytes(_png())
    data = json.loads((tmp_path / "replay/EV-1.json").read_text())
    data["artifacts"] = {"after": str(image)}
    (tmp_path / "replay/EV-1.json").write_text(json.dumps(data))
    result = engine.replay("EV-1")
    assert result.status == "not_reproduced"
    assert result.match_score > .98
    assert not result.reproduced


def test_prefix_error_does_not_count_as_target_signal(tmp_path):
    signal = "TypeError: shared save handler unavailable"
    class Driver(_FakeDriver):
        def execute(self, action, timeout=3000):
            super().execute(action, timeout)
            if len(self.actions) == 1:
                self.signals.record("page_error", {"message": signal})
            return {"status": "completed"}
    fake = Driver(_png())
    result = package(tmp_path, fake, source_signals=[fact(message=signal)],
        action_sequence=[{"type": "click", "target": {"selector": "#open"}}],
        target_action={"type": "click", "target": {"selector": "#save"}},
        target_window={"phase": "action", "step_id": "ST-2"}).replay("EV-1")
    assert len(fake.actions) == 2
    assert result.status == "not_reproduced"
    assert result.matched_basis == []


def test_http_match_requires_method_url_status(tmp_path):
    runtime = RuntimeSignals()
    runtime.record("http_response", {"method": "GET", "url": "http://x/api/save", "status": 500})
    result = package(tmp_path, _FakeDriver(_png(), runtime), source_signals=[
        fact("http_response", method="POST", url="http://x/api/save", status=500)]).replay("EV-1")
    assert result.status == "not_reproduced"


def test_truncated_observation_is_unknown(tmp_path):
    runtime = RuntimeSignals(dropped_count=1)
    result = package(tmp_path, _FakeDriver(_png(), runtime), source_signals=[
        fact(message="TypeError: target handler unavailable")]).replay("EV-1")
    assert result.status == "inconclusive"


def test_progress_keeps_current_step_and_excludes_session(tmp_path):
    updates = []
    engine = package(tmp_path, _FakeDriver(_png()), storage_state={"cookies": [{"value": "PRIVATE"}]},
        target_action={"type": "click", "target": {"selector": "#save"}},
        target_window={"phase": "action", "step_id": "ST-2"})
    engine.on_progress = updates.append
    engine.replay("EV-1")
    assert any(row["interrupted_step_id"] == "ST-2" for row in updates)
    assert "PRIVATE" not in str(updates)


def test_changed_entry_redirect_is_environment_failure(tmp_path):
    class Driver(_FakeDriver):
        def url(self):
            return "http://x/login"
    result = package(tmp_path, Driver(_png()), access_result={"actual_url": "http://x/home"}).replay("EV-1")
    assert result.status == "failed"
    assert result.phase == "access"
    assert "认证" in result.note


def test_evidence_package_separates_target_and_source_groups(tmp_path):
    from alienqa.driver import Action, Target
    from alienqa.evidence import EvidenceEngine
    from alienqa.observation.models import RuntimeObservation
    signal = fact(message="TypeError: target handler unavailable")
    signal.update(record_id="RUN:R-1", phase="action")
    http = fact("http_response", method="POST", url="http://x/api/save", status=500)
    http.update(record_id="RUN:R-2", phase="action")
    class Driver:
        def replay_data(self):
            return {"url": "http://x/start", "action_sequence": [
                {"type": "click", "target": {"selector": "#open"}, "step_id": "ST-1"},
                {"type": "click", "target": {"selector": "#save"}, "step_id": "ST-2", "action_id": "A-2"}],
                    "attempts": [{"step_id": "ST-2", "emitted": True, "status": "completed"}]}
    runtime = RuntimeObservation(records=[signal, http], window={"cursor_start": 0, "cursor_end": 2})
    evs = EvidenceEngine(tmp_path).build_technical(runtime, Action("click", Target(selector="#save")),
                                                 driver=Driver(), step_id="ST-2", action_id="A-2")
    assert len(evs) == 2
    for ev in evs:
        replay = ev.replay
        assert len(replay["action_sequence"]) == 1
        assert replay["target_action"]["step_id"] == "ST-2"
        assert [record["record_id"] for record in replay["source_signals"]] == ev.source_record_ids


def test_entry_package_has_no_fake_target_or_final_url_fallback(tmp_path):
    from types import SimpleNamespace
    from alienqa.evidence import EvidenceEngine
    from alienqa.observation.models import RuntimeObservation
    signal = fact(message="TypeError: entry component unavailable")
    signal.update(record_id="RUN:R-1", phase="entry")
    ev = EvidenceEngine(tmp_path).build_technical(RuntimeObservation(records=[signal]),
        state=SimpleNamespace(id="S", route="http://x/final", snapshot="Home"))[0]
    assert not ev.replay.get("url")
    assert ev.replay["target_action"] is None
    assert ev.replay["target_window"]["phase"] == "entry"


def test_browser_fallback_cannot_claim_original_environment(tmp_path):
    class Driver(_FakeDriver):
        def replay_data(self):
            return {'browser_kind': 'chromium', 'viewport': {'width': 800, 'height': 600}}
    result = package(tmp_path, Driver(_png()), browser_kind='chrome').replay('EV-1')
    assert result.status == 'failed' and result.phase == 'environment'


@pytest.mark.parametrize('version', [3, True, '2'])
def test_unsupported_package_version_is_not_legacy(tmp_path, version):
    result = package(tmp_path, _FakeDriver(_png()), package_version=version).replay('EV-1')
    assert result.status == 'failed' and result.phase == 'package'


def test_matching_technical_fact_cannot_replace_cognitive_picture(tmp_path):
    signal = 'TypeError: target handler unavailable'
    runtime = RuntimeSignals()
    runtime.record('page_error', {'message': signal})
    engine = package(tmp_path, _FakeDriver(_png(), runtime), source_signals=[fact(message=signal)])
    path = tmp_path / 'replay/EV-1.json'
    data = json.loads(path.read_text())
    data['finding_kind'] = 'cognitive_mismatch'
    path.write_text(json.dumps(data))
    assert engine.replay('EV-1').status == 'inconclusive'


def test_legacy_known_technical_candidate_cannot_reproduce_from_picture(tmp_path):
    image = tmp_path / 'after.png'
    image.write_bytes(_png())
    engine = ReplayEngine(tmp_path / 'replay', driver_factory=lambda: _FakeDriver(_png()))
    engine.save(Evidence(id='EV-1', finding_kind='technical_anomaly', replay={'url': 'http://x'},
                         artifacts={'after': str(image)}))
    result = engine.replay('EV-1')
    assert not result.reproduced and result.status == 'inconclusive'
