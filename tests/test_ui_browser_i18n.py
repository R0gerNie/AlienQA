"""English language switching and asynchronous console controls in Chromium."""
import re

from playwright.sync_api import expect

from alienqa.evidence import Evidence
from test_ui_browser_flow import console, page  # noqa: F401 - shared fixtures


def test_english_switch_persists_for_scan_navigation_and_cancellation(console, page):
    app, base_url = console
    tab, errors = page
    tab.goto(base_url + "/?lang=zh")
    tab.get_by_role("link", name="English", exact=True).click()
    expect(tab.locator("html")).to_have_attribute("lang", "en")
    expect(tab.get_by_role("button", name="Start scan", exact=True)).to_be_visible()
    tab.get_by_role("button", name="Browse…", exact=True).click()
    expect(tab.locator("#browse-path")).to_have_text("(disk root)")
    tab.locator("#browse-close").click()
    tab.locator("#mode").select_option("browser")
    tab.locator("#base_url").fill("http://localhost:3000/login")
    tab.locator("#unit").fill("User-provided scope")
    with tab.expect_response(lambda result: result.url == base_url + "/api/run" and result.request.method == "POST") as started:
        tab.get_by_role("button", name="Start scan", exact=True).click()
    assert started.value.status == 200
    run_id = started.value.json()["run_id"]
    assert app.config["runs"].get(run_id).language == "en"
    expect(tab.locator("#status")).to_contain_text("Scanning…")
    tab.get_by_role("link", name="History", exact=True).click()
    tab.get_by_role("row").filter(has_text=run_id).get_by_role("link", name="Open", exact=True).click()
    expect(tab.locator("html")).to_have_attribute("lang", "en")
    tab.locator("#stop-run").click()
    expect(tab.locator("#stop-status")).to_have_text("Stopping the task and browser…")
    assert app.config["runs"].get(run_id).status == "cancelled"
    assert "user stopped" in app.config["runs"].get(run_id).error.lower()
    assert errors == []


def test_english_errors_review_notes_and_report_links(console, page):
    app, base_url = console
    tab, errors = page
    tab.goto(base_url + "/?lang=en")
    tab.locator("#mode").select_option("browser")
    tab.locator("#base_url").fill("file:///tmp/index.html")
    tab.get_by_role("button", name="Start scan", exact=True).click()
    expect(tab.locator("#status")).to_contain_text("URL")
    assert "网址" not in tab.locator("#status").inner_text()
    runs = app.config["runs"]
    rec = runs.create("example", language="en")
    runs.save_results(rec.id, [Evidence(id="EV-EN", expectation="原始证据保留")], [])
    runs.finish(rec.id, "done", evidence_count=1)
    tab.goto(base_url + f"/runs/{rec.id}/review")
    tab.get_by_label("Developer decision").select_option("rejected")
    tab.get_by_label("Note", exact=True).fill("Reviewed in English")
    tab.get_by_role("button", name="Save decision", exact=True).click()
    expect(tab.locator(".save-status")).to_contain_text("Saved:")
    assert runs.load_review(rec.id).note("EV-EN") == "Reviewed in English"
    tab.get_by_role("link", name=re.compile(r"^QA and user cognition analysis$", re.I)).click()
    expect(tab.locator("html")).to_have_attribute("lang", "en")
    expect(tab.locator("body")).to_contain_text("原始证据保留")
    assert errors == []
