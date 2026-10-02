"""EvidenceEngine：把每条 mismatch 枚举成一条 Evidence，并落盘（可复现）。"""
import time
from copy import deepcopy
from pathlib import Path

from .models import Evidence, Severity, valid_basis
from ..observation.models import Observation
from ..persistence import atomic_write_bytes, atomic_write_json
from .severity import assess_severity, classify, confidence
from .storage import EvidenceStore


class EvidenceEngine:
    def __init__(self, artifacts_dir="artifacts", store: EvidenceStore | None = None):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.store = store or EvidenceStore(self.artifacts_dir / "evidence.db")
        self._counter = 0

    def build(self, mismatches, observation, action, state, driver=None, before_state=None,
              *, run_id="", step_id=None, action_id=None, expectations=None) -> list:
        """全量枚举：每个 mismatch 一条 Evidence，一条不漏。"""
        out = []
        for m in mismatches:
            self._counter += 1
            ev_id = f"EV-{self._counter:05d}"
            expected = next((e for e in expectations or []
                             if getattr(e, "text", None) == m.expectation
                             and (not getattr(m, "expectation_id", "") or getattr(e, "id", "") == m.expectation_id)), None)
            if any(getattr(e, "id", "") for e in expectations or []) and not getattr(m, "expectation_id", ""):
                raise ValueError("新认知 Evidence 必须引用事前 expectation_id")
            if getattr(m, "expectation_id", "") and (expected is None or any(
                    getattr(expected, key, None) != value for key, value in
                    (("run_id", run_id), ("step_id", step_id), ("action_id", action_id)))):
                raise ValueError("认知 Evidence 的事前预期身份不匹配")
            basis = getattr(expected, "expectation_basis", None)
            out.append(Evidence(
                id=ev_id,
                action=_serialize_action(action),
                expectation=m.expectation,
                observation_summary=m.observation,
                reasoning=m.reasoning,
                severity=assess_severity(m, observation),
                classification=classify(m, observation, action),
                confidence=confidence(m, observation),
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                artifacts=self._write_artifacts(ev_id, observation, before_state, state),
                replay=_build_replay(driver, observation, state, action=action, step_id=step_id, action_id=action_id),
                before_state_id=getattr(before_state, "id", "") or "",
                after_state_id=getattr(state, "id", "") or "",
                schema_version=2,
                finding_kind="cognitive_mismatch" if valid_basis(basis) else None,
                expectation_basis=basis if valid_basis(basis) else None,
                run_id=run_id, step_id=step_id, action_id=action_id,
                source_record_ids=[r["record_id"] for r in observation.runtime.records] if observation else [],
                expectation_id=getattr(expected, "id", "") or None,
            ))
        return out

    def build_technical(self, runtime_window, action=None, state=None, driver=None, before_state=None,
                        *, run_id="", step_id=None, action_id=None) -> list:
        """Raw JS exceptions and HTTP 5xx are candidates, never auto-confirmed."""
        groups = {"js_exception": [], "http_5xx": []}
        for record in runtime_window.records:
            if record["kind"] == "page_error":
                groups["js_exception"].append(record)
            elif record["kind"] == "http_response" and 500 <= record["payload"].get("status", 0) <= 599:
                groups["http_5xx"].append(record)
        observation = Observation(runtime=runtime_window)
        out = []
        for kind, records in groups.items():
            if not records:
                continue
            self._counter += 1
            ev_id = f"EV-{self._counter:05d}"
            summary = "; ".join(r["payload"].get("message", "") if kind == "js_exception" else
                                f"{r['payload'].get('method', '')} {r['payload'].get('url', '')} → {r['payload']['status']}"
                                for r in records)
            out.append(Evidence(id=ev_id, schema_version=2, finding_kind="technical_anomaly",
                                expectation_basis=None, expectation="", observation_summary=summary,
                                reasoning="浏览器原始异常候选；影响和可接受性需人工核对", severity=Severity.MAJOR,
                                classification="technical_bug", confidence=None,
                                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"), action=_serialize_action(action),
                                artifacts=self._write_artifacts(ev_id, observation, before_state, state),
                                replay=_build_replay(driver, observation, state, action=action, step_id=step_id,
                                                     action_id=action_id, records=records),
                                before_state_id=getattr(before_state, "id", "") or "",
                                after_state_id=getattr(state, "id", "") or "", run_id=run_id,
                                step_id=step_id, action_id=action_id,
                                source_record_ids=[r["record_id"] for r in records]))
        return out

    def attach_observation(self, evidence, observation, before_state=None, after_state=None):
        evidence.artifacts = self._write_artifacts(evidence.id, observation, before_state, after_state)
        evidence.after_state_id = getattr(after_state, "id", "") or ""

    def persist(self, evidence: Evidence) -> None:
        from ..replay import ReplayEngine

        ReplayEngine(self.artifacts_dir / "replay").save(evidence)
        self.store.insert(evidence)

    def _write_artifacts(self, ev_id: str, observation, before_state=None, after_state=None) -> dict:
        ev_dir = self.artifacts_dir / ev_id
        ev_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        paths["snapshot_kind"] = "visible_text"  # State.snapshot is not a DOM tree.
        for name, state in (("dom_before", before_state), ("dom_after", after_state)):
            snapshot = getattr(state, "snapshot", "") or ""
            if snapshot:
                path = ev_dir / f"{name}.html"
                atomic_write_bytes(path, snapshot.encode("utf-8"))
                paths[name] = str(path.resolve())
        if observation is None:
            return paths
        if observation.before_image:
            atomic_write_bytes(ev_dir / "before.png", observation.before_image)
            paths["before"] = str((ev_dir / "before.png").resolve())
        if observation.after_image:
            atomic_write_bytes(ev_dir / "after.png", observation.after_image)
            paths["after"] = str((ev_dir / "after.png").resolve())
        if observation.technical:
            atomic_write_json(ev_dir / "technical.json", observation.technical)
            paths["technical"] = str((ev_dir / "technical.json").resolve())
        paths["missing"] = [name for name in ("before", "after", "technical") if name not in paths]
        return paths


def _serialize_action(action) -> dict:
    if action is None:
        return {}
    if hasattr(action, "type"):
        result = {"type": action.type, "target": _serialize_target(getattr(action, "target", None))}
        if getattr(action, "text", ""):
            result["text"] = action.text
        return result
    if isinstance(action, dict):
        return action
    return str(action)


def _serialize_target(target) -> dict:
    if target is None:
        return {}
    if hasattr(target, "text"):
        result = {"text": getattr(target, "text", "") or "", "selector": getattr(target, "selector", "") or ""}
        for name in ("role", "x", "y", "name", "label", "scope", "viewport"):
            value = getattr(target, name, None)
            if value is not None:
                result[name] = value
        return result
    if isinstance(target, dict):
        return target
    return str(target)


def _build_replay(driver, observation, state, *, action=None, step_id=None, action_id=None, records=None) -> dict:
    replay = {}
    if driver is not None:
        if hasattr(driver, "replay_data"):
            replay = deepcopy(driver.replay_data() or {})
        if "storage_state" not in replay and hasattr(driver, "storage_state"):
            try:
                replay["storage_state"] = driver.storage_state() or {}
                replay["cookies"] = replay["storage_state"].get("cookies", [])
                replay["session_snapshot_origin"] = "legacy_current_unknown"
            except Exception:  # noqa: BLE001
                replay["cookies"] = []
    # A post-action state.route cannot establish an initial URL.
    sequence = replay.get("action_sequence") or []
    target = _serialize_action(action) if action is not None else None
    if target and sequence:
        last = sequence[-1]
        same_ref = bool(action_id and last.get("action_id") == action_id)
        same_action = {k: last.get(k) for k in ("type", "target", "text") if last.get(k)} == target
        if same_ref or (not last.get("action_id") and same_action):
            target = sequence.pop()
    replay.update(package_version=2, action_sequence=sequence, target_action=target,
                  target_window={"phase": "action" if target else "entry" if not sequence else "background",
                                 "step_id": step_id, "action_id": action_id})
    if observation is not None and observation.runtime is not None:
        replay["console"] = list(observation.runtime.console_errors)
        replay["network"] = list(observation.runtime.network_failures)
        replay["js_exceptions"] = list(observation.runtime.js_exceptions)
        replay["http_status"] = dict(observation.runtime.http_status)
        replay["source_signals"] = deepcopy(records if records is not None else observation.runtime.records)
        replay["observation_window"] = dict(observation.runtime.window)
        if not target and records and records[0].get("phase") in {"entry", "background"}:
            replay["target_window"]["phase"] = records[0]["phase"]
    return replay
