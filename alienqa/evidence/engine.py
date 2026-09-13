"""EvidenceEngine：把每条 mismatch 枚举成一条 Evidence，并落盘（可复现）。"""
import json
import time
from pathlib import Path

from .models import Evidence
from .severity import assess_severity, classify, confidence
from .storage import EvidenceStore


class EvidenceEngine:
    def __init__(self, artifacts_dir="artifacts", store: EvidenceStore | None = None):
        self.artifacts_dir = Path(artifacts_dir)
        self.store = store or EvidenceStore()
        self._counter = 0

    def build(self, mismatches, observation, action, state, driver=None) -> list:
        """全量枚举：每个 mismatch 一条 Evidence，一条不漏。"""
        out = []
        for m in mismatches:
            self._counter += 1
            ev_id = f"EV-{self._counter:05d}"
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
                artifacts=self._write_artifacts(ev_id, observation),
                replay=_build_replay(driver, observation, state),
            ))
        return out

    def persist(self, evidence: Evidence) -> None:
        self.store.insert(evidence)

    def _write_artifacts(self, ev_id: str, observation) -> dict:
        ev_dir = self.artifacts_dir / ev_id
        ev_dir.mkdir(parents=True, exist_ok=True)
        paths = {}
        if observation is None:
            return paths
        if observation.before_image:
            (ev_dir / "before.png").write_bytes(observation.before_image)
            paths["before"] = str(ev_dir / "before.png")
        if observation.after_image:
            (ev_dir / "after.png").write_bytes(observation.after_image)
            paths["after"] = str(ev_dir / "after.png")
        if observation.technical:
            (ev_dir / "technical.json").write_text(
                json.dumps(observation.technical, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            paths["technical"] = str(ev_dir / "technical.json")
        return paths


def _serialize_action(action) -> dict:
    if action is None:
        return {}
    if hasattr(action, "type"):
        return {"type": action.type, "target": _serialize_target(getattr(action, "target", None))}
    if isinstance(action, dict):
        return action
    return str(action)


def _serialize_target(target) -> dict:
    if target is None:
        return {}
    if hasattr(target, "text"):
        return {"text": getattr(target, "text", "") or "", "selector": getattr(target, "selector", "") or ""}
    if isinstance(target, dict):
        return target
    return str(target)


def _build_replay(driver, observation, state) -> dict:
    replay = {}
    if driver is not None:
        if hasattr(driver, "replay_data"):
            replay = driver.replay_data() or {}
        if hasattr(driver, "storage_state"):
            try:
                replay["cookies"] = (driver.storage_state() or {}).get("cookies", [])
            except Exception:  # noqa: BLE001
                replay["cookies"] = []
    if not replay.get("url") and state is not None:
        replay["url"] = getattr(state, "route", "") or ""
    if observation is not None and observation.runtime is not None:
        replay["console"] = list(observation.runtime.console_errors)
        replay["network"] = list(observation.runtime.network_failures)
    return replay
