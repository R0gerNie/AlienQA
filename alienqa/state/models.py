"""State Tracker 数据模型。"""
from dataclasses import asdict, dataclass, field


@dataclass
class State:
    id: str
    route: str
    signature: str
    snapshot: str = ""
    normalized: str = ""
    parent: str | None = None
    action: dict | None = None
    first_seen: str = ""
    last_seen: str = ""
    visits: int = 1


@dataclass
class StateGraph:
    nodes: list = field(default_factory=list)  # list[State]
    edges: list = field(default_factory=list)  # list[{from, action, to}]

    def to_dict(self) -> dict:
        return {"nodes": [asdict(n) for n in self.nodes], "edges": list(self.edges)}
