"""StateTracker：状态去重 + State Graph。"""
import dataclasses
import json
import time
from pathlib import Path

from .models import State, StateGraph
from .signature import normalize, signature


def _serialize_action(action):
    if action is None:
        return None
    if dataclasses.is_dataclass(action):
        return dataclasses.asdict(action)
    if isinstance(action, dict):
        return action
    return str(action)


class StateTracker:
    def __init__(self):
        self._states: dict = {}
        self._sequence: list = []
        self._edges: list = []
        self._current: State | None = None
        self._counter = 0
        self._trajectory: list = []
        self._attempts: list = []
        self._legacy_state_ids: set = set()

    def observe(self, route: str, snapshot: str, action=None, form_state=None, step_id=None) -> State:
        """返回新状态或合并到已有状态（签名去重）。"""
        sig = signature(route, snapshot, form_state)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        previous = self._current
        existing = self._states.get(sig)
        if existing is not None:
            existing.last_seen = now
            existing.visits += 1
            self._record_visit(existing, previous, action, step_id)
            return existing

        self._counter += 1
        state = State(
            id=f"S-{self._counter:03d}",
            route=route,
            signature=sig,
            snapshot=snapshot,
            normalized=normalize(snapshot),
            parent=self._current.id if self._current else None,
            action=_serialize_action(action),
            first_seen=now,
            last_seen=now,
        )
        self._states[sig] = state
        self._sequence.append(state)
        self._record_visit(state, previous, action, step_id)
        return state

    def _record_visit(self, state, previous, action, step_id=None) -> None:
        serialized = _serialize_action(action)
        if previous is not None and (action is not None or previous.id != state.id):
            self._edges.append({"from": previous.id, "action": serialized, "to": state.id})
            if step_id:
                self._edges[-1]["step_id"] = step_id
        self._trajectory.append({
            "state_id": state.id, "route": state.route,
            "action": serialized, "from": previous.id if previous else None,
        })
        self._current = state
        if step_id:
            self._trajectory[-1]["step_id"] = step_id

    def record_attempt(self, action, previous, state=None, *, step_id=None, status="completed", execution=None, error=""):
        self._attempts.append({"step_id": step_id, "from": previous.id if previous else None,
                               "to": state.id if state else None, "action": _serialize_action(action),
                               "status": status, "execution": execution or {}, "error": error})

    def attempts(self) -> list:
        return list(self._attempts)

    def capture(self, driver, action=None, timeout: int = 3000, step_id=None) -> State:
        """执行 action 后抓取 driver 当前状态并 observe（driver 需提供 execute/url/visible_text）。"""
        previous = self._current
        try:
            if action is not None:
                driver.execute(action, timeout=timeout)
            result = getattr(driver, "last_execution", {}) if action else {}
            success = result.get("status", "completed") == "completed"
            state = self.observe(driver.url(), driver.visible_text(), action if success else None,
                                 form_state=getattr(driver, "form_state", lambda: None)(), step_id=step_id)
            if action:
                self.record_attempt(action, previous, state, step_id=step_id,
                                    status="completed" if success else "failed", execution=result)
            return state
        except Exception as exc:
            if action:
                self.record_attempt(action, previous, step_id=step_id, status="failed",
                                    execution=getattr(driver, "last_execution", {}), error=str(exc))
            raise

    def is_new(self, route: str, snapshot: str, form_state=None) -> bool:
        return signature(route, snapshot, form_state) not in self._states

    def explored(self, state: State) -> bool:
        return state.signature in self._states

    def sequence(self) -> list:
        return list(self._sequence)

    def trajectory(self) -> list:
        """Chronological visits, including returns and actions that leave text unchanged."""
        return list(self._trajectory)

    def action_history(self) -> list:
        return [entry["action"] for entry in self._trajectory if entry["action"] is not None]

    def graph(self) -> StateGraph:
        return StateGraph(nodes=list(self._sequence), edges=list(self._edges))

    def save(self, path) -> None:
        path = Path(path)
        path.write_text(
            json.dumps({**self.graph().to_dict(), "signature_version": "visible-state-v2",
                        "legacy_state_ids": sorted(self._legacy_state_ids),
                        "trajectory": self.trajectory(), "attempts": self.attempts()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        t = cls()
        for node in data["nodes"]:
            st = State(**node)
            t._sequence.append(st)
            # Old digest schemes are readable, but cannot prove new coverage.
            legacy = data.get("signature_version") != "visible-state-v2" or st.id in data.get("legacy_state_ids", [])
            if legacy:
                t._legacy_state_ids.add(st.id)
            key = "legacy:" + st.signature if legacy else st.signature
            t._states[key] = st
        t._edges = list(data["edges"])
        t._counter = len(t._sequence)
        t._trajectory = list(data.get("trajectory", []))
        t._attempts = list(data.get("attempts", []))
        if t._trajectory:
            current_id = t._trajectory[-1]["state_id"]
            t._current = next(st for st in t._sequence if st.id == current_id)
        elif t._sequence:
            t._current = t._sequence[-1]
            t._trajectory = [{"state_id": st.id, "route": st.route, "action": st.action, "from": st.parent}
                             for st in t._sequence]
        return t
