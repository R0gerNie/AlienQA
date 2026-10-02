"""RuntimeObserver：确定性运行时观察（无 LLM）。"""
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..driver.runtime import RuntimeSignals
from .models import RuntimeObservation


class RuntimeObserver:
    def observe(self, page, before: RuntimeSignals | None = None) -> RuntimeObservation:
        """采集 page 当前运行时信号；before 给定时只取本次动作的增量。"""
        after = page.collect_runtime()
        sig = _diff(before, after) if before is not None else after
        records = deepcopy(sig.records)
        modern = bool(after.cursor or after.records)
        if not modern:
            # Legacy drivers retain their string API. IDs are tied to absolute
            # positions, so rereading a window never manufactures new events.
            for field, kind in (("console_errors", "console_error"), ("page_errors", "page_error"),
                                ("network_failures", "request_failed"), ("http_errors", "http_response")):
                offset = len(getattr(before, field)) if before else 0
                for index, value in enumerate(getattr(sig, field), offset):
                    payload = {"message": value}
                    if kind == "http_response":
                        left, _, status = value.rpartition("->")
                        tokens = left.split()
                        if len(tokens) >= 2 and status.strip().isdigit():
                            payload.update(method=tokens[0], url=tokens[-1], status=int(status))
                    records.append({"record_id": f"{after.run_id}:{field}:{index}", "run_id": after.run_id,
                                    "step_id": None, "action_id": None, "phase": "legacy",
                                    "timestamp": datetime.now(timezone.utc).isoformat(), "kind": kind, "payload": payload})
        if modern:
            sig = RuntimeSignals()
            for record in records:
                kind, payload = record["kind"], record["payload"]
                if kind == "page_error":
                    sig.page_errors.append(payload.get("message", ""))
                elif kind == "console_error":
                    sig.console_errors.append(payload.get("message", ""))
                elif kind == "request_failed":
                    sig.network_failures.append(f"{payload.get('method', '')} {payload.get('url', '')} -> {payload.get('message', '')}")
                elif kind == "http_response" and payload.get("status", 0) >= 400:
                    sig.http_errors.append(f"{payload.get('method', '')} {payload.get('url', '')} -> {payload['status']}")
        return RuntimeObservation(
            console_errors=list(sig.console_errors),
            network_failures=list(sig.network_failures),
            http_status=_parse_http_status(sig.http_errors),
            js_exceptions=list(sig.page_errors),
            resource_failures=[],  # API/资源失败细分延后
            url=_page_url(page),
            storage={},  # localStorage/sessionStorage 纳入观察延后
            records=records,
            window={"cursor_start": before.cursor if before else 0, "cursor_end": after.cursor,
                    "dropped_count": after.dropped_count - (before.dropped_count if before else 0),
                    "truncated": bool(after.dropped_count or any(r.get("payload_truncated") for r in records))},
        )


def _diff(before: RuntimeSignals, after: RuntimeSignals) -> RuntimeSignals:
    """取 after 相对 before 的增量（driver 是持续 append 的）。"""
    return RuntimeSignals(
        console_errors=after.console_errors[len(before.console_errors):],
        page_errors=after.page_errors[len(before.page_errors):],
        network_failures=after.network_failures[len(before.network_failures):],
        http_errors=after.http_errors[len(before.http_errors):],
        records=[r for r in after.records if r["sequence"] > before.cursor],
    )


def _parse_http_status(http_errors) -> dict:
    """把 "GET http://host/api/refund -> 500" 解析成 {path: status}。"""
    out = {}
    for e in http_errors:
        left, sep, right = e.rpartition("->")
        if not sep:
            continue
        status = right.strip()
        if not status.isdigit():
            continue
        tokens = left.split()
        if len(tokens) < 2:
            continue
        out[urlparse(tokens[-1]).path] = int(status)
    return out


def _page_url(page) -> str:
    attr = getattr(page, "url", "")
    if callable(attr):
        return attr() or ""
    return attr or ""
