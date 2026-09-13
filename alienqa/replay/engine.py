"""ReplayEngine：保存回放包 + 一键回放（可复现性判定）。"""
import json
from pathlib import Path

from ..driver import Action
from .models import ReplayResult
from .scorer import image_similarity, signal_overlap

_REPRODUCE_THRESHOLD = 0.7


class ReplayEngine:
    def __init__(self, replay_dir="replay", driver_factory=None):
        self.replay_dir = Path(replay_dir)
        self.driver_factory = driver_factory  # 可注入，便于测试/隔离

    def save(self, evidence) -> None:
        """保存回放包到 replay/<evidence_id>.json。"""
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        path = self.replay_dir / f"{evidence.id}.json"
        path.write_text(
            json.dumps(evidence.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def replay(self, evidence_id: str) -> ReplayResult:
        """一键回放：读包 → launch(还原 cookies) → 重放 action_sequence → 对比。"""
        pkg = self._load(evidence_id)
        replay = pkg.get("replay") or {}
        artifacts = pkg.get("artifacts") or {}
        url = replay.get("url") or ""
        action_sequence = replay.get("action_sequence") or []
        cookies = replay.get("cookies") or []
        storage_state = {"cookies": cookies} if cookies else None

        driver = self._new_driver()
        try:
            driver.launch(url, storage_state=storage_state)
            for item in action_sequence:
                action = Action.from_dict(item) if isinstance(item, dict) else item
                driver.execute(action, timeout=3000)
            after_bytes = driver.screenshot()
            runtime = driver.collect_runtime()
        finally:
            driver.close()

        orig_after = self._read(artifacts.get("after"))
        score = image_similarity(orig_after, after_bytes)
        console_hit = signal_overlap(replay.get("console") or [], runtime.console_errors)
        net_hit = signal_overlap(replay.get("network") or [], runtime.network_failures)
        reproduced = score >= _REPRODUCE_THRESHOLD or console_hit or net_hit
        return ReplayResult(
            evidence_id=evidence_id,
            reproduced=reproduced,
            match_score=score,
            replay=replay,
            note="" if reproduced else "可能是环境相关/偶发问题",
        )

    # ---- 内部 ----

    def _load(self, evidence_id: str) -> dict:
        path = self.replay_dir / f"{evidence_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"回放包不存在: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _new_driver(self):
        if self.driver_factory is not None:
            return self.driver_factory()
        from ..driver import PlaywrightDriver

        return PlaywrightDriver()

    @staticmethod
    def _read(path) -> bytes | None:
        if not path:
            return None
        try:
            return Path(path).read_bytes()
        except OSError:
            return None
