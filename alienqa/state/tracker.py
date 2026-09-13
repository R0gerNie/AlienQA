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

    def observe(self, route: str, snapshot: str, action=None) -> State:
        """返回新状态或合并到已有状态（签名去重）。"""
        sig = signature(route, snapshot)
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        existing = self._states.get(sig)
        if existing is not None:
            existing.last_seen = now
            existing.visits += 1
            self._current = existing
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
        if self._current is not None:
            self._edges.append({
                "from": self._current.id,
                "action": _serialize_action(action),
                "to": state.id,
            })
        self._states[sig] = state
        self._sequence.append(state)
        self._current = state
        return state

    def capture(self, driver, action=None, timeout: int = 3000) -> State:
        """执行 action 后抓取 driver 当前状态并 observe（driver 需提供 execute/url/visible_text）。"""
        if action is not None:
            driver.execute(action, timeout=timeout)
        return self.observe(driver.url(), driver.visible_text(), action)

    def is_new(self, route: str, snapshot: str) -> bool:
        return signature(route, snapshot) not in self._states

    def explored(self, state: State) -> bool:
        return state.signature in self._states

    def sequence(self) -> list:
        return list(self._sequence)

    def graph(self) -> StateGraph:
        return StateGraph(nodes=list(self._sequence), edges=list(self._edges))

    def save(self, path) -> None:
        path = Path(path)
        path.write_text(
            json.dumps(self.graph().to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        t = cls()
        for node in data["nodes"]:
            st = State(**node)
            t._sequence.append(st)
            t._states[st.signature] = st
        t._edges = list(data["edges"])
        t._counter = len(t._sequence)
        if t._sequence:
            t._current = t._sequence[-1]
        return t
