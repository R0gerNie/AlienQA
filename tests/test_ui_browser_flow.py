"""Real browser wiring for scan inputs, cancellation and replay controls."""
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from alienqa.evidence import Evidence
from alienqa.llm import LLMClient
from alienqa.ui import create_ui_app
from alienqa.ui.jobs import JobController


class _FakeJobController(JobController):
    """Exercise real HTTP handlers while substituting model/browser workers."""

    def __init__(self, runs):
        super().__init__()
        self.runs = runs
        self.pending = None
        self.timers = []

    def start(self, token, task_id, target, args, complete, timeout):
        self.pending = (token, task_id, complete)
        if target.__name__ == "_replay_worker":
            evidence_id = args[-1]

            def finish_replay():
                self.runs.save_replay_result(task_id, evidence_id, {
                    "evidence_id": evidence_id, "status": "reproduced", "reproduced": True,
                    "match_score": 1.0, "note": "已确认重放结果", "matched_signals": {},
                })
                complete(None)
                self.release(token)
                self.pending = None

            timer = threading.Timer(0.15, finish_replay)
            self.timers.append(timer)
            timer.start()

    def cancel(self, task_id):
        if self.pending is None or self.pending[1] != task_id:
            return False
        token, _, complete = self.pending
        complete("cancelled")
        self.release(token)
        self.pending = None
        return True


@pytest.fixture
def console(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    import yaml
    config.write_text(yaml.safe_dump({"llm": {"roles": {role: {"model": "openai/test"} for role in
        ("gist", "expectation", "visual", "judge", "reporter")}}}), encoding="utf-8")

    def forbidden_model_call(*args, **kwargs):
        raise AssertionError("UI browser tests must not invoke a model")

    monkeypatch.setattr(LLMClient, "complete", forbidden_model_call)
    app = create_ui_app(str(config), str(tmp_path / "settings.yaml"), str(tmp_path / "runs"))
    controller = _FakeJobController(app.config["runs"])
    app.config["job_controller"] = controller
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, f"http://127.0.0.1:{server.server_port}"
    finally:
        for timer in controller.timers:
            timer.join(1)
        server.shutdown()
        server.server_close()
        thread.join(1)


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(__file__).resolve().parents[1] / ".venv" / "browsers"))
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        context = browser.new_context()
        tab = context.new_page()
        errors = []
        tab.on("pageerror", lambda error: errors.append(str(error)))
        try:
            yield tab, errors
        finally:
            context.close()
            browser.close()


def test_url_login_state_submit_then_open_and_stop_scan(console, page, tmp_path):
    app, base_url = console
    tab, errors = page
    state = tmp_path / "session.json"
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    tab.goto(base_url)
    tab.locator("#mode").select_option("browser")
    tab.locator("#base_url").fill("http://localhost:3000/login")
    tab.locator("#storage_state").fill(str(state))
    tab.locator("#unit").fill("登录表单")
    tab.locator("#instructions").fill("错误密码应显示反馈")
    with tab.expect_response(lambda response: response.url == base_url + "/api/run" and response.request.method == "POST") as started:
        tab.get_by_role("button", name="开始扫描").click()
    response = started.value
    assert response.status == 200
    assert response.request.post_data_json == {
        "mode": "browser", "project_path": "", "base_url": "http://localhost:3000/login",
        "app_path": "", "max_actions": 10, "max_seconds": 300, "samples": 2, "browser": "chrome",
        "static_entry": "", "base_path": "/", "spa_fallback": False,
        "storage_state": str(state), "unit": "登录表单", "instructions": "错误密码应显示反馈",
    }
    run_id = response.json()["run_id"]
    expect(tab.locator("#status")).to_contain_text("扫描中")
    tab.get_by_role("link", name="历史项目", exact=True).click()
    tab.get_by_role("row").filter(has_text=run_id).get_by_role("link", name="打开").click()
    expect(tab).to_have_url(base_url + f"/runs/{run_id}")
    with tab.expect_response(lambda result: result.url.endswith(f"/api/run/{run_id}/stop") and result.request.method == "POST") as stopped:
        tab.locator("#stop-run").click()
    assert stopped.value.status == 202
    expect(tab.locator("#stop-status")).to_have_text("正在停止任务与浏览器…")
    assert app.config["runs"].get(run_id).status == "cancelled"
    assert errors == []


def test_review_replay_button_posts_and_displays_polled_result(console, page):
    app, base_url = console
    tab, errors = page
    runs = app.config["runs"]
    rec = runs.create("http://localhost:3000", mode="browser", base_url="http://localhost:3000")
    runs.save_results(rec.id, [Evidence(id="EV-001", expectation="保存后显示反馈")], [])
    runs.finish(rec.id, "done", evidence_count=1)
    replay_dir = rec.dir / "artifacts" / "replay"
    replay_dir.mkdir(parents=True)
    (replay_dir / "EV-001.json").write_text("{}", encoding="utf-8")
    tab.goto(base_url + f"/runs/{rec.id}/review")
    with tab.expect_response(lambda result: result.url.endswith(f"/api/run/{rec.id}/replay/EV-001") and result.request.method == "POST") as requested:
        tab.get_by_role("button", name="重放", exact=True).click()
    assert requested.value.status == 202
    expect(tab.locator('[data-replay="EV-001"]')).to_have_text("reproduced：已确认重放结果", timeout=5000)
    expect(tab.get_by_role("button", name="重放", exact=True)).to_be_enabled()
    assert runs.load_replay_results(rec.id)["EV-001"]["reproduced"] is True
    assert errors == []


def test_t05_failed_replay_details_do_not_block_review(console, page):
    app, base_url = console
    tab, errors = page
    runs = app.config['runs']
    rec = runs.create('test')
    runs.save_results(rec.id, [Evidence(id='EV-1')], [])
    runs.finish(rec.id, 'partial', evidence_count=1)
    runs.save_replay_result(rec.id, 'EV-1', {'status': 'failed', 'phase': 'target',
        'note': '目标不可执行', 'interrupted_step_id': 'ST-3', 'executed_steps': [{'step_id': 'ST-2'}],
        'preconditions': {'saved_session': 'saved'}, 'target_window': {'phase': 'action'},
        'matched_basis': [], 'limits': ['未支持作用域']})
    tab.goto(base_url + f'/runs/{rec.id}/review')
    expect(tab.locator('[data-replay="EV-1"]')).to_have_text('failed：目标不可执行')
    tab.get_by_text('回放前提、步骤与匹配依据', exact=True).click()
    expect(tab.locator('[data-replay-details="EV-1"]')).to_contain_text('ST-3')
    expect(tab.locator('[data-replay-details="EV-1"]')).to_contain_text('未支持作用域')
    tab.get_by_label('开发者决定').select_option('rejected')
    tab.get_by_role('button', name='保存决定').click()
    expect(tab.locator('.save-status')).to_contain_text('已保存')
    assert runs.get(rec.id).status == 'partial' and errors == []
