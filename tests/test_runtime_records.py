from copy import deepcopy
from types import SimpleNamespace

from alienqa.driver.runtime import RuntimeSignals
from alienqa.observation import RuntimeObserver


def test_repeated_http_requests_keep_identity_url_and_window():
    signals = RuntimeSignals(run_id="run-1")
    signals.record("http_response", {"url": "https://app.test/api?q=1&token=private", "status": 500,
                                      "method": "POST", "resource_type": "fetch"})
    before = deepcopy(signals)
    signals.record("http_response", {"url": "https://app.test/api?q=2", "status": 502,
                                      "method": "POST", "resource_type": "fetch"})
    page = SimpleNamespace(collect_runtime=lambda: signals, url=lambda: "https://app.test/")
    observer = RuntimeObserver()
    first = observer.observe(page)
    second = observer.observe(page, before)
    assert len(first.records) == 2
    assert [r["record_id"] for r in second.records] == [first.records[1]["record_id"]]
    assert second.window["cursor_start"] == 1 and second.window["cursor_end"] == 2
    assert "private" not in str(first.records)
    assert "q=1" in first.records[0]["payload"]["url"]
    assert "q=2" in first.records[1]["payload"]["url"]


def test_runtime_limits_keep_cursor_and_dropped_count():
    signals = RuntimeSignals(run_id="run-1", max_records=2, max_text_bytes=16)
    for _ in range(2):
        signals.record("page_error", {"message": "错误" * 20})
    before = deepcopy(signals)
    for _ in range(5):
        signals.record("page_error", {"message": "overflow"})
    page = SimpleNamespace(collect_runtime=lambda: signals, url=lambda: "/")
    window = RuntimeObserver().observe(page, before)
    assert window.records == []
    assert window.window["dropped_count"] == 5
    assert window.window["cursor_end"] == 7
    assert len(signals.records) == 2 and len(signals.page_errors) == 2
    assert len(signals.records[0]["payload"]["message"].encode()) <= 16
    assert signals.records[0]["payload_truncated"] is True


def test_signal_clear_does_not_reuse_record_ids():
    from alienqa.driver import PlaywrightDriver
    driver = PlaywrightDriver()
    driver._signals.record("page_error", {"message": "first"})
    first = driver.snapshot_runtime()
    driver.clear_runtime()
    driver._signals.record("page_error", {"message": "second"})
    assert driver._signals.records[0]["record_id"] != first.records[0]["record_id"]
