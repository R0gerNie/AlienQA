"""An English report stays usable offline and exports English report chrome."""
import json
from types import SimpleNamespace

import pytest
from playwright.sync_api import expect

from alienqa.evidence import Evidence
from alienqa.review import ReportBuilder, ReviewState
from test_ui_browser_flow import page


@pytest.fixture
def english_report(tmp_path):
    builder = ReportBuilder(SimpleNamespace())
    builder.roles.compose_report = lambda *args, **kwargs: ""
    report = builder.build([Evidence(id="EV-A", expectation="中文证据"), Evidence(id="EV-B")], ReviewState(),
                           mode="analysis", language="en", scan_context={"run_id": "english-offline", "status": "partial"})
    path = tmp_path / "english.html"
    path.write_text(report.html)
    return path


def test_english_offline_save_restore_and_final_export(page, english_report, tmp_path):
    tab, errors = page
    tab.context.set_offline(True)
    tab.goto(english_report.as_uri())
    rows = tab.locator('[data-offline-review]')
    rows.nth(1).get_by_role("combobox", name="Accept this finding").select_option("rejected")
    note = '<img src=x onerror="window.PWN=1">中文备注'
    rows.nth(0).get_by_role("textbox", name="Note", exact=True).fill(note)
    tab.get_by_role("button", name="Save all choices", exact=True).click()
    expect(tab.locator('[data-review-status]')).to_have_text("All choices and notes have been saved in this browser.")
    tab.reload()
    expect(tab.locator('[data-review-status]')).to_have_text("Choices and notes saved in this browser have been restored.")
    with tab.expect_download() as download:
        tab.get_by_role("button", name="Export decisions and notes", exact=True).click()
    decisions = tmp_path / "decisions.json"
    download.value.save_as(str(decisions))
    assert json.loads(decisions.read_text())["decisions"][0]["note"] == note
    with tab.expect_download() as download:
        tab.get_by_role("button", name="Generate final report", exact=True).click()
    final = tmp_path / "final.html"
    download.value.save_as(str(final))
    expect(tab.locator('[data-review-status]')).to_have_text("Final report exported with 1 accepted finding. The original report was not modified.")
    tab.goto(final.as_uri())
    expect(tab.locator("html")).to_have_attribute("lang", "en")
    expect(tab.locator(".hero h1")).to_have_text("Accepted Findings Report")
    expect(tab.locator(".finding")).to_have_count(1)
    expect(tab.locator(".review-result")).to_contain_text(note)
    expect(tab.locator('[data-findings-count]')).to_have_text("1 accepted finding")
    expect(tab.locator('.hero-copy')).to_contain_text("Displays 1 accepted finding based")
    expect(tab.locator("body")).to_contain_text("Scan incomplete")
    assert tab.locator("script").count() == 0
    assert tab.evaluate("window.PWN") is None
    assert errors == []


def test_english_offline_storage_failure_and_empty_export(page, english_report, tmp_path):
    tab, errors = page
    tab.add_init_script("Storage.prototype.setItem = function () { throw new Error('blocked'); };")
    tab.goto(english_report.as_uri())
    tab.get_by_role("button", name="Save all choices", exact=True).click()
    expect(tab.locator('[data-review-status]')).to_contain_text("Save failed")
    for row in tab.locator('[data-offline-review]').all():
        row.get_by_role("combobox").select_option("rejected")
    with tab.expect_download() as download:
        tab.get_by_role("button", name="Generate final report", exact=True).click()
    final = tmp_path / "empty.html"
    download.value.save_as(str(final))
    tab.goto(final.as_uri())
    expect(tab.locator("body")).to_contain_text("No findings were accepted")
    expect(tab.locator('[data-findings-count]')).to_have_text("0 accepted findings")
    assert errors == []
