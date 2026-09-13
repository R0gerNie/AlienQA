"""RuntimeObserver：确定性运行时观察（无 LLM）。"""
from urllib.parse import urlparse

from ..driver.runtime import RuntimeSignals
from .models import RuntimeObservation


class RuntimeObserver:
    def observe(self, page, before: RuntimeSignals | None = None) -> RuntimeObservation:
        """采集 page 当前运行时信号；before 给定时只取本次动作的增量。"""
        after = page.collect_runtime()
        sig = _diff(before, after) if before is not None else after
        return RuntimeObservation(
            console_errors=list(sig.console_errors),
            network_failures=list(sig.network_failures),
            http_status=_parse_http_status(sig.http_errors),
            js_exceptions=list(sig.page_errors),
            resource_failures=[],  # API/资源失败细分延后
            url=_page_url(page),
            storage={},  # localStorage/sessionStorage 纳入观察延后
        )


def _diff(before: RuntimeSignals, after: RuntimeSignals) -> RuntimeSignals:
    """取 after 相对 before 的增量（driver 是持续 append 的）。"""
    return RuntimeSignals(
        console_errors=after.console_errors[len(before.console_errors):],
        page_errors=after.page_errors[len(before.page_errors):],
        network_failures=after.network_failures[len(before.network_failures):],
        http_errors=after.http_errors[len(before.http_errors):],
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
