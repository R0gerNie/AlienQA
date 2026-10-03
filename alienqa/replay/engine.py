"""Restore prerequisites and compare only the recorded target observation window."""
from ..i18n import t
import json
import re
import threading
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from ..driver import Action
from ..driver.runtime import clean_message, sanitize_url
from ..persistence import atomic_write_json
from .models import ReplayResult
from .scorer import image_similarity
from .signals import signal_key


class ReplayEngine:
    def __init__(self, replay_dir="replay", driver_factory=None, on_progress=None):
        self.replay_dir = Path(replay_dir)
        self.driver_factory = driver_factory
        self.on_progress = on_progress

    def save(self, evidence) -> Path:
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        path = self._package_path(evidence.id)
        atomic_write_json(path, evidence.to_dict())
        path.chmod(0o600)
        return path

    def replay(self, evidence_id: str) -> ReplayResult:
        result = ReplayResult(evidence_id=evidence_id, status="running", limits=[
            t("画面接近与技术信号再次出现均不证明认知解释或根因；开发者决定不受回放影响"),
            t("仅恢复 cookies/localStorage；sessionStorage、IndexedDB、自动登录和外部业务数据不恢复"),
        ])
        driver = server = thread = None
        try:
            pkg = self._load(evidence_id)
            replay = result.replay = pkg.get("replay") or {}
            artifacts = pkg.get("artifacts") or {}
            modern = replay.get("package_version") == 2
            url = replay.get("url") or ""
            sequence = replay.get("action_sequence") or []
            target = replay.get("target_action")
            result.target_window = {key: (replay.get("target_window") or {}).get(key)
                                    for key in ("phase", "step_id", "action_id")}
            result.preconditions = {"url": sanitize_url(url), "browser_kind": replay.get("browser_kind"),
                                    "viewport": replay.get("viewport"), "prefix_count": len(sequence),
                                    "saved_session": "saved" if replay.get("storage_state") or replay.get("cookies") else "absent",
                                    "environment_applied": False}
            if not modern:
                result.limits.append(t("旧包没有独立目标窗口；按最后一个成功动作观察，来源完整性未知"))
            if replay.get("session_snapshot_origin") == "legacy_current_unknown":
                result.limits.append(t("旧 driver 会话快照时间未知，不能证明是原初始会话"))
            if not url:
                return self._finish(result, "failed", t("回放包缺少初始 URL"))
            if replay.get("prefix_complete") is False:
                return self._finish(result, "inconclusive", t("动作发出结果不确定，无法证明成功前缀恢复了原前置条件"))
            if modern and result.target_window["phase"] not in {"entry", "action", "background"}:
                return self._finish(result, "failed", t("回放包缺少可核对的目标阶段"))
            if modern and result.target_window["phase"] == "action" and not target:
                return self._finish(result, "failed", t("回放包缺少目标动作"))
            result.phase = "environment"
            self._progress(result)
            metadata = replay.get("static_server")
            if metadata:
                directory, port = Path(metadata.get("directory") or ""), metadata.get("port")
                if not directory.is_dir() or not isinstance(port, int) or not 1 <= port <= 65535:
                    raise ValueError(t("静态回放服务目录不存在或端口无效"))
                handler = partial(_ReplayHandler, directory=str(directory), spa_fallback=metadata.get("spa_fallback", False), base_path=metadata.get("base_path", "/"))
                server = ThreadingHTTPServer(("127.0.0.1", port), handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                result.preconditions["static_service"] = "restored_owned"
            driver = self._new_driver(replay)
            result.phase = "access"
            self._progress(result)
            storage = replay.get("storage_state")
            if storage is None and replay.get("cookies"):
                storage = {"cookies": replay["cookies"]}
            driver.launch(url, storage_state=storage)
            if modern and result.target_window["phase"] == "entry" and hasattr(driver, "wait_for_settle"):
                settling = driver.wait_for_settle()
                if settling.get("status") in {"failed", "timeout"}:
                    return self._finish(result, "inconclusive", t("入口观察窗口未稳定或读取失败"))
            result.preconditions["environment_applied"] = self.driver_factory is None
            if hasattr(driver, "replay_data"):
                actual_environment = driver.replay_data()
                result.preconditions["actual_browser_kind"] = actual_environment.get("browser_kind")
                result.preconditions["actual_browser_version"] = actual_environment.get("browser")
                result.preconditions["actual_viewport"] = actual_environment.get("viewport")
                if replay.get("browser_kind") and actual_environment.get("browser_kind") != replay["browser_kind"]:
                    result.phase = "environment"
                    return self._finish(result, "failed", t("实际浏览器与记录不同（可能触发默认浏览器回退），同环境前提未恢复"))
                if replay.get("viewport") and actual_environment.get("viewport") != replay["viewport"]:
                    result.phase = "environment"
                    return self._finish(result, "failed", t("实际视口与记录不同，同环境前提未恢复"))
                if replay.get("browser") and actual_environment.get("browser") != replay["browser"]:
                    result.limits.append(t("浏览器版本与记录不同；使用本机现有版本，未安装原版本"))
            if self.driver_factory is not None:
                result.limits.append(t("注入 driver 的浏览器/视口由调用者负责，未由 ReplayEngine 验证"))
            expected_entry = (replay.get("access_result") or {}).get("actual_url")
            actual_entry = driver.url() if hasattr(driver, "url") else ""
            if expected_entry and actual_entry and expected_entry != actual_entry:
                return self._finish(result, "failed", t("入口重定向与记录不同，认证可能过期或环境已改变"))
            baseline = {}
            steps = [(item, "prefix") for item in sequence]
            if modern:
                if target:
                    steps.append((target, "target"))
            elif steps:
                steps[-1] = (steps[-1][0], "target")
            for index, (item, role) in enumerate(steps):
                result.phase = role
                result.interrupted_step_id = item.get("step_id") or (result.target_window.get("step_id") if role == "target" else None)
                if role == "target":
                    baseline = _runtime_dict(driver.collect_runtime())
                self._progress(result)
                action = Action.from_dict(item)
                strategy = (item.get("locator") or {}).get("strategy")
                if strategy in {"label", "role_name", "role", "text", "coordinates"}:
                    action.target.selector = None
                if strategy in {"text", "coordinates"}:
                    action.target.label = action.target.role = None
                if strategy == "coordinates":
                    action.target.text = None
                driver.on_execution = lambda execution: self._progress(result, execution)
                execution = driver.execute(action, timeout=3000)
                result.executed_steps.append({"step_id": result.interrupted_step_id, "index": index, "role": role,
                                              "action_type": item.get("type"),
                                              "execution": _public_execution(execution)})
                self._progress(result)
                if isinstance(execution, dict):
                    if execution.get("status") != "completed":
                        raise RuntimeError("replay input was rejected or could not be verified")
                    if execution.get("wait", {}).get("status") in {"failed", "timeout"}:
                        return self._finish(result, "inconclusive", t("回放动作已发出，观察窗口未稳定或读取失败"))
            if modern and result.target_window["phase"] == "background":
                baseline = _runtime_dict(driver.collect_runtime())
                if hasattr(driver, "wait_for_settle"):
                    settling = driver.wait_for_settle()
                    if settling.get("status") in {"failed", "timeout"}:
                        return self._finish(result, "inconclusive", t("背景观察窗口未稳定或读取失败"))
                result.limits.append(t("背景窗口只观察重放后的短时事件，原后台计时和外部数据未恢复"))
            result.phase = "observation"
            self._progress(result)
            after_bytes = None
            try:
                after_bytes = driver.screenshot()
            except Exception as exc:
                result.limits.append(t("截图读取失败：") + clean_message(str(exc)))
            runtime = _runtime_dict(driver.collect_runtime())
            final_url = driver.url() if hasattr(driver, "url") else ""
            self._compare(result, pkg, artifacts, runtime, baseline, after_bytes, final_url, modern)
            result.phase = "comparison"
            self._progress(result)
            return result
        except Exception as exc:
            return self._finish(result, "failed", t("{phase} 阶段失败（步骤 {step}）：{error}", phase=result.phase, step=result.interrupted_step_id or t("入口 / 未记录"), error=clean_message(str(exc))))
        finally:
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass
            if server is not None:
                if thread is not None and thread.is_alive():
                    server.shutdown()
                server.server_close()
                if thread is not None:
                    thread.join(timeout=2)

    def _compare(self, result, pkg, artifacts, runtime, baseline, after_bytes, final_url, modern):
        replay = result.replay
        original = self._read(artifacts.get("after"))
        result.match_score = image_similarity(original, after_bytes)
        visual_comparable = bool(original and after_bytes and image_similarity(original, original) > 0)
        actual_records = [r for r in runtime["records"] if r.get("sequence", 0) > baseline.get("cursor", 0)]
        expected_records = replay.get("source_signals") or []
        specific = [(r, signal_key(r)) for r in expected_records]
        specific = [(r, key) for r, key in specific if key is not None]
        actual_keys = {signal_key(r) for r in actual_records}
        for record, key in specific:
            if key in actual_keys:
                result.matched_basis.append({"kind": key[0], "source_record_id": record.get("record_id"),
                                             "fact": list(key[1:]), "window": result.target_window})
        for key in ("console", "network", "js_exceptions", "http_errors"):
            actual = runtime[key][len(baseline.get(key, [])):]
            expected = replay.get(key) or []
            if key == "http_errors":
                expected = [f"{path} -> {status}" for path, status in (replay.get("http_status") or {}).items()]
            hits = [s for s in expected if _specific_signal(s, key) and
                    (any(s in r for r in actual) if key == "http_errors" else s in actual)]
            if hits:
                result.matched_signals[key] = hits
        technical = pkg.get("finding_kind") == "technical_anomaly"
        complete = not runtime["truncated"] and not (replay.get("observation_window") or {}).get("truncated")
        location_ok = not replay.get("final_url") or not final_url or replay["final_url"] == final_url
        if technical:
            comparable = modern and bool(specific) and len(specific) == len(expected_records) and complete
            reproduced = comparable and len(result.matched_basis) == len(specific) and location_ok
        else:
            comparable = visual_comparable and complete
            reproduced = location_ok and complete and (result.match_score >= .98 or
                                                       (not modern and (bool(result.matched_basis) or bool(result.matched_signals))))
            if result.match_score >= .98:
                result.matched_basis.append({"kind": "visual_similarity", "score": result.match_score,
                                             "meaning": t("只表示画面接近，原认知预期需人工复核")})
        result.reproduced = reproduced
        result.status = "reproduced" if reproduced else "not_reproduced" if comparable and location_ok else "inconclusive"
        result.note = (t("目标窗口的具体技术事实再次出现") if reproduced and technical else
                       t("画面/观察再次出现；原认知预期需人工复核") if reproduced else
                       t("观察窗口有缺失或截断，无法验证") if not complete else
                       t("回放终点与记录不同，前提可能已改变") if not location_ok else
                       t("目标窗口未再现原记录的具体事实/画面") if comparable else
                       t("缺少可比较截图或具体来源事实，无法验证"))

    def _finish(self, result, status, note):
        result.status, result.note = status, note
        self._progress(result)
        return result

    def _progress(self, result, execution=None):
        if self.on_progress:
            payload = result.to_dict()
            if execution is not None:
                payload["current_execution"] = _public_execution(execution)
            self.on_progress(deepcopy(payload))

    def _load(self, evidence_id):
        path = self._package_path(evidence_id)
        if not path.exists():
            raise FileNotFoundError(t("回放包不存在: {path}", path=path))
        pkg = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(pkg, dict):
            raise ValueError(t("回放包必须为对象"))
        for key in ("replay", "artifacts"):
            if key in pkg and not isinstance(pkg[key], dict):
                raise ValueError(t("回放包 {key} 必须为对象", key=key))
        replay = pkg.get("replay") or {}
        version = replay.get("package_version")
        if "package_version" in replay and (type(version) is not int or version != 2):
            raise ValueError(t("不支持的回放包版本：{version}", version=version))
        return pkg

    def _package_path(self, evidence_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", evidence_id or ""):
            raise ValueError(t("无效的证据 ID"))
        return self.replay_dir / f"{evidence_id}.json"

    def _new_driver(self, replay=None):
        if self.driver_factory is not None:
            return self.driver_factory()
        from ..driver import PlaywrightDriver
        replay = replay or {}
        if replay.get("browser_kind") not in {None, "chrome", "chromium"}:
            raise ValueError(t("回放浏览器类型不受支持"))
        return PlaywrightDriver(browser=replay.get("browser_kind") or "chrome", viewport=replay.get("viewport"))

    @staticmethod
    def _read(path):
        try:
            return Path(path).read_bytes() if path else None
        except OSError:
            return None


def _public_execution(execution):
    if not isinstance(execution, dict):
        return {"status": "unrecorded"}
    return {key: deepcopy(execution[key]) for key in ("status", "emitted", "step_id", "action_id", "elapsed_ms") if key in execution} | {
        "locator_strategy": (execution.get("locator") or {}).get("strategy"),
        "wait": {key: (execution.get("wait") or {}).get(key) for key in ("status", "elapsed_ms")}}


def _runtime_dict(runtime):
    return {key: list(getattr(runtime, attr, None) or []) for key, attr in
            (("console", "console_errors"), ("network", "network_failures"),
             ("js_exceptions", "page_errors"), ("http_errors", "http_errors"))} | {
                 "records": deepcopy(getattr(runtime, "records", []) or []),
                 "cursor": getattr(runtime, "cursor", 0),
                 "truncated": bool(getattr(runtime, "dropped_count", 0) or
                                   any(r.get("payload_truncated") for r in getattr(runtime, "records", [])))}


def _specific_signal(signal, kind):
    text = str(signal).strip()
    if kind in ("network", "http_errors"):
        return "http" in text and " -> " in text
    return len(text) >= 20 and ":" in text and not text.startswith("Failed to load resource")


# The producer and independent replay restore exactly the same deployment rules.
from ..static_server import StaticHandler


class _ReplayHandler(StaticHandler):
    pass
