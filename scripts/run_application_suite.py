"""Local upstream browser checks, then opt-in six-case real-model evaluation with one budget."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alienqa import evaluation
from alienqa.persistence import atomic_write_json
from alienqa.static_server import serve
from scripts.prepare_application_suite import WORKSPACE, PINS, prepare
from scripts.prepare_t09_todomvc import COMMIT, prepare as prepare_todomvc


def application_cases(todo, tools, memos, sessions):
    cases = []
    for name, base, revision in [("todomvc", todo, COMMIT), ("it-tools", tools, PINS["it-tools"][1]),
                                 ("memos", memos, PINS["memos"][1])]:
        for mode in ("autonomous", "directed"):
            row = {"id": f"{name}-{mode}", "application": name, "mode": mode,
                   "version": revision, "entry_url": base, "max_actions": 4,
                   "reset": "Fresh browser context with empty local storage"}
            if name == "todomvc" and mode == "directed":
                row.update(entry_url=base + "#/active",
                           reset="Fresh empty Active view; upstream todos live in memory, not storage_state")
            if name == "it-tools" and mode == "directed":
                row["entry_url"] = base + "json-to-yaml-converter"
            if name == "memos":
                row.update(storage_state=sessions[row["id"]],
                           reset="New isolated user, no memos; browser session contains sign-in only")
                if mode == "directed":
                    row["unit"] = "Memo editor"
            cases.append(row)
    return cases


def select_cases(cases, selected=None, action_overrides=None):
    known = {case["id"] for case in cases}
    if selected and not set(selected) <= known:
        raise ValueError("Unknown application case")
    if selected and len(selected) != len(set(selected)):
        raise ValueError("Application case selection must be unique")
    by_id = {case["id"]: case for case in cases}
    result = [dict(by_id[name]) for name in (selected or [case["id"] for case in cases])]
    overrides = {}
    for item in action_overrides or []:
        name, separator, value = item.partition("=")
        if not separator or name not in {case["id"] for case in result} or not value.isdigit() or int(value) < 1 or name in overrides:
            raise ValueError("Use a unique selected CASE=positive-actions override")
        overrides[name] = int(value)
    for case in result:
        case["max_actions"] = overrides.get(case["id"], case["max_actions"])
    return result


def browser_checks(todo, tools, memos, output):
    """Expected values stay in this mechanism checker, never in model inputs."""
    from playwright.sync_api import expect, sync_playwright
    sessions = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(todo)
            for text in ("Review report", "Keep all findings"):
                page.locator(".new-todo").fill(text)
                page.locator(".new-todo").press("Enter")
            expect(page.locator(".todo-list li")).to_have_count(2)
            page.locator(".todo-list .toggle").first.check()
            page.get_by_role("link", name="Active", exact=True).click()
            expect(page.locator(".todo-list li")).to_have_count(1)
            page.screenshot(path=str(output / "todomvc-browser.png"))
            context.close()
            context = browser.new_context()
            page = context.new_page()
            page.goto(todo + "#/active")
            expect(page.locator(".todo-list li")).to_have_count(0)
            context.close()

            context = browser.new_context()
            page = context.new_page()
            page.goto(tools + "json-to-yaml-converter")
            page.get_by_placeholder("Paste your JSON here...", exact=True).fill('{"name":"AlienQA","count":2}')
            expect(page.locator("body")).to_contain_text("name: AlienQA")
            page.get_by_placeholder("Paste your JSON here...", exact=True).fill("not valid JSON")
            expect(page.locator("body")).to_contain_text("Provided JSON is not valid.")
            page.screenshot(path=str(output / "it-tools-browser.png"))
            context.close()

            for name in ("smoke", "autonomous", "directed"):
                context = browser.new_context(locale="en-US")
                page = context.new_page()
                page.goto(memos + "auth/signup")
                page.get_by_placeholder("Username", exact=True).fill("alienqa-" + name)
                page.get_by_placeholder("Password", exact=True).fill("AlienQA123!")
                page.get_by_role("button", name="Sign up", exact=True).click()
                page.get_by_placeholder("Any thoughts...", exact=True).wait_for(timeout=20000)
                if name == "smoke":
                    text = "AlienQA browser persistence check #alienqa-smoke"
                    page.get_by_placeholder("Any thoughts...", exact=True).fill(text)
                    page.get_by_role("button", name="Save", exact=True).click()
                    expect(page.locator("body")).to_contain_text("AlienQA browser persistence check")
                    page.reload()
                    expect(page.locator("body")).to_contain_text("AlienQA browser persistence check")
                    page.screenshot(path=str(output / "memos-browser.png"))
                else:
                    sessions["memos-" + name] = str(output / ("memos-" + name + "-session.json"))
                    context.storage_state(path=sessions["memos-" + name])
                context.close()
        finally:
            browser.close()
    return sessions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--real-model", action="store_true", help="Explicit model calls; default only browser checks")
    parser.add_argument("--max-calls", type=int)
    parser.add_argument("--config", default="config/codex.yaml")
    parser.add_argument("--cases", nargs="+", help="Run a named subset, retaining each case's mode")
    parser.add_argument("--case-actions", nargs="+", metavar="CASE=COUNT", help="Explicit per-case action budgets")
    args = parser.parse_args(argv)
    if args.real_model and (args.max_calls is None or args.max_calls < 1):
        parser.error("Real-model execution requires explicit positive --max-calls")
    output = Path(args.output).resolve()
    if not output.is_relative_to(ROOT / "artifacts/evaluation") or output.exists():
        parser.error("Use a new project-local artifacts/evaluation directory")
    pins = prepare()
    app = prepare_todomvc()
    output.mkdir(parents=True)
    servers, process = [], None
    try:
        todo_server, todo = serve(app / "dist", port=5310)
        servers.append(todo_server)
        tools_server, tools = serve(WORKSPACE / "it-tools/dist", spa_fallback=True, port=5311)
        servers.append(tools_server)
        # Check the fixed replayable endpoint before starting an owned backend.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 5232))
        data = output / "memos-data"
        data.mkdir()
        memos = "http://127.0.0.1:5232/"
        with (output / "memos-server.log").open("w") as log:
            process = subprocess.Popen([str(WORKSPACE / "memos-server"), "--mode", "prod", "--addr", "127.0.0.1",
                                        "--port", "5232", "--data", str(data)], stdout=log, stderr=subprocess.STDOUT)
            for attempt in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Memos backend exited; inspect saved log")
                try:
                    with urllib.request.urlopen(memos, timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Memos backend did not become ready")
            sessions = browser_checks(todo, tools, memos, output)
            cases = select_cases(application_cases(todo, tools, memos, sessions), args.cases, args.case_actions)
            atomic_write_json(output / "applications.json", {"schema_version": 1, "version": "oss-applications-2026-10-02-v1", "cases": cases})
            atomic_write_json(output / "browser-checks.json", {"status": "passed", "real_model_calls": 0,
                "upstreams": {**pins, "todomvc": {"commit": COMMIT}}, "browser": "chromium",
                "todomvc": "add/toggle/filter; separate context correctly resets to empty", "it-tools": "convert valid JSON and show invalid input",
                "memos": "register/save/reload persistence; separate empty users prepared",
                "notice": "Mechanism checks do not decide which model findings are reasonable"})
            print(f"[applications] Three browser checks passed; {len(cases)} isolated cases prepared", flush=True)
            if args.real_model:
                return evaluation.main(["--applications-manifest", str(output / "applications.json"),
                    "--config", args.config, "--output", str(output / "model"), "--max-calls", str(args.max_calls),
                    "--samples", "2", "--max-seconds", "900"])
            return 0
    except Exception as exc:
        atomic_write_json(output / "setup-failure.json", {"status": "failed", "error": str(exc), "model_started": (output / "model").exists()})
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
