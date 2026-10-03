"""AlienQA 正式入口：`python -m alienqa` 跑全链路 01→12，产出 HTML 报告。

密钥一律从环境变量读取；未设置时回退到本机约定俗成的 key 文件
（D:\\dskey.txt → DEEPSEEK_API_KEY，D:\\alikey.txt → DASHSCOPE_API_KEY），
可用 ALIENQA_*_KEY_FILE 环境变量覆盖路径。
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

from .llm import LLMClient, load_config
from .local_run import ScanInput, select_project, static_directory, serve_project, source_context, validate_config, check_output, check_url, check_browser
from .ui.runs import RunManager, RunRecord
from .run_writer import RunWriter, StorageError, read_json
from .persistence import atomic_write_json
from .loader import Project, ProjectLoader, VisibleFile
from .pipeline import AlienQAPipeline
from .persistence import atomic_write_bytes
from .run_writer import load_snapshot
from .llm.metering import close_unfinished, load_summary, public_text
from .review.service import REPORT_FILES, invalidate_report_paths
from .review import Decision, HumanReview, ReportBuilder, ReviewState, create_app
from .i18n import language_context, normalize_language, t, translate_text

REPO = Path(__file__).resolve().parent.parent

# (环境变量名, 覆盖路径的环境变量, 默认 key 文件)
_KEY_FILES = (
    ("DEEPSEEK_API_KEY", "ALIENQA_DEEPSEEK_KEY_FILE", r"D:\dskey.txt"),
    ("DASHSCOPE_API_KEY", "ALIENQA_DASHSCOPE_KEY_FILE", r"D:\alikey.txt"),
)


def _load_keys() -> None:
    for env_name, file_env, default_file in _KEY_FILES:
        if os.environ.get(env_name):
            continue
        path = Path(os.environ.get(file_env) or default_file)
        if path.exists():
            os.environ[env_name] = path.read_text(encoding="utf-8").strip()


def _serve(directory: str, **deployment) -> tuple:
    from .static_server import serve
    server, base = serve(directory, **deployment)
    return server, base.rstrip('/')


def _build_project(root: Path, base_url: str, framework: str, routes: str, entry: str) -> Project:
    return Project(
        root=str(root),
        framework=framework,
        routes=[r.strip() for r in routes.split(",") if r.strip()],
        entry_points=[entry],
        visible_files=[VisibleFile(path=entry, role="page", lines=60)],
        base_url=base_url,
    )


def _finish_usage(directory, run_id, termination):
    try:
        close_unfinished(directory, run_id, termination)
    except (OSError, ValueError, TypeError) as exc:
        print(t("[usage] 计量不完整：{error}", error=translate_text(public_text(exc))), file=sys.stderr)


def _default_config() -> Path:
    default_config = REPO / "config" / "config.yaml"
    if not default_config.exists():
        default_config = Path(sys.prefix) / "share" / "alienqa" / "config.yaml"
    return default_config


def _resolve_language(argv, default_config: Path) -> tuple[str, bool]:
    """Resolve the locale before constructing localized help and errors."""
    import yaml

    preliminary = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    preliminary.add_argument("--config", default=str(default_config))
    preliminary.add_argument("--language")
    known, _ = preliminary.parse_known_args(argv)
    configured = None
    try:
        with open(known.config, encoding="utf-8") as file:
            data = yaml.safe_load(file)
        if isinstance(data, dict):
            llm = data.get("llm") or {}
            configured = data.get("language") or (llm.get("language") if isinstance(llm, dict) else None)
    except (OSError, yaml.YAMLError):
        # Help remains available even when the scan configuration is unavailable.
        pass
    selected = known.language or configured or os.environ.get("ALIENQA_LANGUAGE") or "zh"
    overridden = bool(known.language or configured or os.environ.get("ALIENQA_LANGUAGE"))
    try:
        return normalize_language(selected), overridden
    except ValueError:
        # The final parser/config loader provides the actionable validation error.
        return "zh", overridden


class _LocalizedParser(argparse.ArgumentParser):
    def error(self, message):
        super().error(translate_text(message))


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    default_config = _default_config()
    language, language_override = _resolve_language(arguments, default_config)
    with language_context(language):
        return _main(arguments, default_config, language, language_override)


def _main(argv, default_config, language, language_override) -> int:
    parser = _LocalizedParser(prog="python -m alienqa", description=t("AlienQA 全链路测试（01→12）"))
    parser.add_argument("--language", choices=("zh", "en"), default=language,
                        help=t("界面、模型输出和报告语言（默认中文；优先于配置和 ALIENQA_LANGUAGE）"))
    parser.add_argument("--config", default=str(default_config), help=t("LLM 配置 yaml"))
    parser.add_argument("--output", default=None, help=t("HTML 报告输出路径（优先于模式默认路径）"))
    parser.add_argument("--report-mode", choices=("analysis", "confirmed"), default="analysis", help=t("报告模式；默认保留所有发现的 analysis"))
    parser.add_argument("--url", default=None, help=t("被测 URL；仅 URL 为黑盒，配合 project-root 为源码模式"))
    parser.add_argument("--serve", default=str(REPO / "tests" / "fixtures"), help=t("--url 缺省时 serve 的静态目录"))
    parser.add_argument("--project-root", default=None, help=t("源码根目录；使用 Loader 识别框架和路由"))
    parser.add_argument("--app", default="", help=t("源码模式：相对项目根目录的应用目录；多个应用时必须选择"))
    parser.add_argument("--unit", default="", help=t("可选页面或功能范围，仅用于定位"))
    parser.add_argument("--instructions", default="", help=t("可选范围定位说明；不作为正确答案"))
    parser.add_argument("--review-run", default=None, metavar="DIR", help=t("重开已有终态扫描的独立审核，不重新扫描"))
    parser.add_argument("--framework", default=None, help=t("可选框架覆盖"))
    parser.add_argument("--routes", default=None, help=t("可选逗号分隔的页面路由"))
    parser.add_argument("--entry", default=None, help=t("静态 HTML 页面（相对所选静态产物目录）"))
    parser.add_argument("--base-path", default="/", help=t("本机静态服务的部署路径，例如 /tool/"))
    parser.add_argument("--spa-fallback", action="store_true", help=t("仅对 HTML 页面导航启用所选页面的 history 回退"))
    parser.add_argument("--samples", type=int, default=2, help=t("08 预期生成采样次数"))
    parser.add_argument("--max-actions", type=int, default=10, help=t("探索动作上限"))
    parser.add_argument("--max-seconds", type=float, default=300, help=t("探索时间预算"))
    parser.add_argument("--artifacts-dir", default=None, help=t("截图、重放包、运行诊断目录"))
    parser.add_argument("--storage-state", default=None, help=t("扫描使用的登录态 JSON（由 --login 保存）"))
    parser.add_argument("--start-command", default=None, help=t("源码应用启动命令，如 npm run dev；退出时回收进程"))
    parser.add_argument("--startup-timeout", type=float, default=30, help=t("启动命令等待 URL 可达的秒数"))
    parser.add_argument("--browser", choices=("chrome", "chromium"), default="chrome")
    parser.add_argument("--auto-confirm", action="store_true", help=t("显式自动采信演示模式；正式结果须人工审核"))
    parser.add_argument("--replay", default=None, metavar="PACKAGE", help=t("重放 artifacts/replay/<id>.json"))
    parser.add_argument("--headful", action="store_true", help=t("有头运行浏览器（默认无头）"))
    parser.add_argument("--review", action="store_true", help=t("收集证据后启动人工审核 WebUI（保存决定和备注，生成分析或确认问题报告）"))
    parser.add_argument("--ui", action="store_true", help=t("启动用户前端控制台（密钥 / 项目扫描 / 历史浏览）"))
    parser.add_argument("--login", default=None, metavar="URL", help=t("起有头浏览器手动登录并保存 storage_state（配合 --session-out）"))
    parser.add_argument("--session-out", default=str(REPO / "config" / "session.json"), help=t("登录态输出路径（默认 config/session.json）"))
    parser.add_argument("--host", default="127.0.0.1", help=t("WebUI 监听地址"))
    parser.add_argument("--port", type=int, default=5000, help=t("WebUI 端口"))
    args = parser.parse_args(argv)
    args.language_override = language_override

    if args.auto_confirm and args.review:
        parser.error(t("--auto-confirm 与 --review 不能同时使用"))
    if args.replay:
        from .replay import ReplayEngine

        package = Path(args.replay).resolve()
        try:
            result = ReplayEngine(replay_dir=package.parent).replay(package.stem)
        except (OSError, ValueError) as exc:
            print(t("[replay] 失败：{error}", error=translate_text(str(exc))), file=sys.stderr)
            return 1
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status == "reproduced" else 2

    _load_keys()

    if args.login:
        from .loader import capture_session

        out = capture_session(args.login, args.session_out)
        print(t("[login] 已保存登录态 → {path}", path=out), flush=True)
        return 0

    if args.ui:
        from .ui import create_ui_app

        ui = create_ui_app(
            args.config,
            settings_path=str(Path.cwd() / "config.local.yaml"),
            runs_dir=str(Path.cwd() / "runs"),
            language=args.language if args.language_override else None,
        )
        print(t("[ui] 控制台：http://{host}:{port}/", host=args.host, port=args.port), flush=True)
        ui.run(host=args.host, port=args.port, debug=False)
        return 0

    if args.review_run:
        return _review_saved(args)
    if args.start_command and (not args.project_root or not args.url):
        parser.error(t("--start-command 需要 --project-root 和实际 --url"))
    try:
        inputs = ScanInput.from_dict({"project_path": args.project_root or (args.serve if not args.url else ""),
            "url": args.url, "storage_state": args.storage_state, "app_path": args.app,
            "unit": args.unit, "instructions": args.instructions, "samples": args.samples,
            "max_actions": args.max_actions, "max_seconds": args.max_seconds,
            "startup_timeout": args.startup_timeout, "browser": args.browser,
            "static_entry": args.entry, "base_path": args.base_path, "spa_fallback": args.spa_fallback,
            "language": args.language})
    except ValueError as exc:
        parser.error(str(exc))
    args.storage_state, args.unit, args.instructions, args.app = inputs.storage_state, inputs.unit, inputs.instructions, inputs.app_path
    if args.url:
        args.url = inputs.base_url
    if args.project_root:
        args.project_root = inputs.project_path
    artifact_dir = Path(args.artifacts_dir or (Path("artifacts") / time.strftime("%Y%m%d-%H%M%S"))).resolve()
    if (artifact_dir / "scan.json").exists() or (artifact_dir / "run.json").exists():
        print(t("[error] 运行目录已有扫描，请选择新目录或使用 --review-run"), file=sys.stderr)
        return 1
    srv = None
    started_process = None
    runs = RunManager(artifact_dir.parent)
    record = RunRecord(id=artifact_dir.name, dir=artifact_dir, project_path=inputs.project_path,
        mode=inputs.mode, base_url=inputs.base_url, unit=inputs.unit, instructions=inputs.instructions,
        storage_state=inputs.storage_state, app_path=inputs.app_path, budget=inputs.budget(), browser=inputs.browser,
        base_path=inputs.base_path, spa_fallback=inputs.spa_fallback, language=args.language,
        started_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        config = load_config(args.config)
        config.language = args.language
        validate_config(config)
        check_output(artifact_dir)
        if args.output:
            check_output(Path(args.output).parent)
        check_browser(args.browser)
        loader = ProjectLoader()
        if args.url and not args.project_root:
            if args.start_command:
                parser.error(t("--start-command 需要 --project-root"))
            project = loader.load_browser(args.url, storage_state=args.storage_state)
        elif args.project_root:
            try:
                project = select_project(loader, args.project_root, args.app)
            except (OSError, NotImplementedError, ValueError) as exc:
                parser.error(str(exc))
            project.storage_state = args.storage_state or ""
            if args.url:
                project.base_url = args.url
                project.environment["base_url_status"] = "explicit_url"
            elif not args.start_command:
                srv, entry = serve_project(project, inputs.static_entry, inputs.base_path, inputs.spa_fallback)
                record.entry = entry
            if args.framework:
                project.framework = args.framework
        else:
            project_root = Path(args.serve).resolve()
            entry = args.entry or "demo-app/index.html"
            project = _build_project(project_root, "", "Static HTML", "/demo-app", entry)
            srv, entry = serve_project(project, entry, inputs.base_path, inputs.spa_fallback)
            record.entry = entry
            project.storage_state = args.storage_state or ""

        if args.routes:
            project.routes = [route.strip() for route in args.routes.split(",") if route.strip()]
        print(t("[01] Project 装载完成"), flush=True)

        pipeline = AlienQAPipeline(
            config,
            samples=args.samples,
            headless=not args.headful,
            max_actions=args.max_actions,
            auto_confirm=args.auto_confirm,
            artifacts_dir=artifact_dir,
            max_seconds=args.max_seconds,
            browser=args.browser,
            unit=args.unit, instructions=args.instructions, run_dir=artifact_dir, run_id=artifact_dir.name,
        )
        record.source_context = source_context(project)
        runs._write(record)
        if args.start_command:
            started_process = subprocess.Popen(
                shlex.split(args.start_command), cwd=project.app_dir or project.root,
                start_new_session=(os.name != "nt"),
            )
            _wait_for_app(project.base_url, started_process, args.startup_timeout)
        check_url(project.base_url)
        runs.update_target(record.id, record.entry if srv else "", project.base_url, source_context(project))
        result = pipeline.collect(project)
        if load_snapshot(artifact_dir) is None:
            result.run_id = record.id
            result.save(artifact_dir)
        saved = load_snapshot(artifact_dir)
        if saved["run_id"] != record.id or saved["phase"] != "terminal":
            raise StorageError(t("扫描未提交匹配的终态快照"))
        # All consumers use the committed rows, not a potentially stale return value.
        from .evidence import Evidence
        from .investigation import Investigation
        result.evidences = [Evidence.from_dict(row) for row in saved["evidences"]]
        result.investigations = [Investigation.from_dict(row, issue_id=row.get("issue_id", "")) for row in saved["investigations"]]
        result.steps, result.diagnostics = saved["steps"], saved["diagnostics"]
        result.run_id = saved["run_id"]
        runs.finish(record.id, "partial" if saved["incomplete"] else "done",
                    evidence_count=len(saved["evidences"]), issue_count=len(saved.get("issues", [])))
        _finish_usage(artifact_dir, result.run_id, "partial" if result.incomplete else "done")
        review = HumanReview.load(artifact_dir / "review.json") if (artifact_dir / "review.json").exists() else HumanReview(ReviewState())
        if args.auto_confirm:
            for ev in result.evidences:
                review.decide(ev.id, Decision.CONFIRMED, t("显式自动采信（未经人工审核）"))
        review.save(artifact_dir / "review.json")
        saved = load_snapshot(artifact_dir)
        context = {key: saved[key] for key in ("run_id", "checkpoint_seq", "phase", "stop_reason", "incomplete", "steps", "scope")}
        context.update(status="partial" if result.incomplete else "done", run_dir=str(artifact_dir.resolve()),
                       input_type=project.input_type, base_url=project.base_url, source_context=source_context(project),
                       budget=inputs.budget(), access_result=saved.get("access_result"), language=args.language)
        paths = {mode: artifact_dir / name for mode, name in REPORT_FILES.items()}
        if args.output:
            paths[args.report_mode] = Path(args.output)
        if len({path.resolve() for path in paths.values()}) != 2:
            raise ValueError(t("--output 与另一个模式的默认路径重合，请指定不同路径"))
        invalidate_report_paths({*paths.values(), *(artifact_dir / name for name in REPORT_FILES.values())})
        output = paths[args.report_mode]
        report_builder = ReportBuilder(pipeline.client)
        if args.review:
            app = create_app(review, report_builder, investigations=result.investigations,
                             review_path=str(artifact_dir / "review.json"), scan_context=context, report_paths=paths,
                             language=args.language)
            app.config["evidences"] = result.evidences
            app.config["diagnostics"] = result.review_diagnostics
            print(t("[review] 打开 http://{host}:{port}/ 保存决定与备注；analysis → {analysis}；confirmed → {confirmed}",
                    host=args.host, port=args.port, analysis=paths["analysis"], confirmed=paths["confirmed"]), flush=True)
            app.run(host=args.host, port=args.port, debug=False)
        else:
            report = report_builder.build(result.evidences, review.state, result.investigations,
                                          diagnostics=result.review_diagnostics, mode=args.report_mode, scan_context=context,
                                          language=args.language)
            atomic_write_bytes(output, report.html.encode("utf-8"))
            suffix = t("；显式自动采信（未经人工审核）") if args.auto_confirm else ""
            print(t("[report] {mode} → {path}；证据 {count}{suffix}",
                    mode=args.report_mode, path=output, count=len(result.evidences), suffix=suffix), flush=True)
        usage = load_summary(artifact_dir, result.run_id)
        print(t("[usage] {calls} 次调用 / {attempts} 次实际请求；未知费用请求 {unknown}；{path}",
                calls=usage.get("logical_calls", t("未知")), attempts=usage.get("attempts", t("未知")),
                unknown=usage.get("unknown_cost_attempts", t("未知")), path=artifact_dir / "usage-summary.json"), flush=True)
        if result.incomplete:
            print(t("[partial] 扫描存在失败或无法判断项，详见 {path}", path=artifact_dir / "scan.json"), file=sys.stderr)
        return 2 if result.incomplete else 0
    except KeyboardInterrupt:
        try:
            writer = RunWriter(artifact_dir)
            writer.append_terminal_diagnostic("cancelled", t("用户中断了扫描"), "cli")
            _finish_usage(artifact_dir, writer.run_id, "cancelled")
            if runs.get(record.id):
                runs.finish(record.id, "cancelled", error=t("用户中断了扫描"))
        except StorageError:
            pass
        print(t("[cancelled] 已保存的扫描前缀保留在 {path}", path=artifact_dir), file=sys.stderr)
        return 130
    except Exception as exc:
        # A report gate/write error leaves a successfully committed scan intact.
        try:
            saved = load_snapshot(artifact_dir)
            if saved is None or saved["phase"] != "terminal":
                writer = RunWriter(artifact_dir, record.id)
                saved = writer.append_terminal_diagnostic("error", translate_text(str(exc)), "cli")
                if not runs.get(record.id):
                    runs._write(record)
                runs.finish(record.id, "error", evidence_count=len(saved["evidences"]), error=translate_text(str(exc)))
                _finish_usage(artifact_dir, writer.run_id, "error")
        except OSError:
            pass
        print(f"[error] {translate_text(str(exc))}", file=sys.stderr)
        return 1
    finally:
        if started_process is not None:
            _stop_app(started_process)
        if srv is not None:
            srv.shutdown()
            srv.server_close()


def _review_saved(args) -> int:
    """Respect a saved run's language unless the caller selected another one."""
    if not args.language_override:
        directory = Path(args.review_run).resolve()
        try:
            metadata = read_json(directory / "run.json") if (directory / "run.json").exists() else {}
            args.language = normalize_language(metadata.get("language") or args.language)
        except (OSError, ValueError):
            # The review loader below reports invalid run metadata as usual.
            pass
    with language_context(args.language):
        return _review_saved_with_language(args)


def _review_saved_with_language(args) -> int:
    """Open terminal facts and saved decisions without browser or scan calls."""
    from .evidence import Evidence
    from .investigation import Investigation
    directory = Path(args.review_run).resolve()
    try:
        saved = load_snapshot(directory)
        if saved is None or saved["phase"] != "terminal":
            raise ValueError(t("需要有效的终态 scan.json"))
        metadata = read_json(directory / "run.json") if (directory / "run.json").exists() else {}
        if metadata.get("status") in {"running", "unknown", "cleanup_failed"}:
            raise ValueError(t("该运行尚未确认结束"))
        review = HumanReview.load(directory / "review.json") if (directory / "review.json").exists() else HumanReview(ReviewState())
        evidences = [Evidence.from_dict(row) for row in saved["evidences"]]
        investigations = [Investigation.from_dict(row, issue_id=row.get("issue_id", "")) for row in saved["investigations"]]
        context = {key: saved[key] for key in ("run_id", "checkpoint_seq", "phase", "stop_reason", "incomplete", "scope", "steps")}
        context.update(status=metadata.get("status", "partial" if saved["incomplete"] else "done"),
                       base_url=metadata.get("base_url"), budget=metadata.get("budget"), source_context=metadata.get("source_context"),
                       access_result=saved.get("access_result"), run_dir=str(directory), language=args.language)
        paths = {mode: directory / name for mode, name in REPORT_FILES.items()}
        if args.output:
            paths[args.report_mode] = Path(args.output)
        if len({path.resolve() for path in paths.values()}) != 2:
            raise ValueError(t("--output 与另一个模式的默认路径重合"))
        config = load_config(args.config)
        config.language = args.language
        app = create_app(review, ReportBuilder(LLMClient(config)), investigations=investigations,
                         review_path=str(directory / "review.json"), scan_context=context, report_paths=paths,
                         language=args.language)
        app.config["evidences"] = evidences
        app.config["diagnostics"] = saved["diagnostics"] + [step for step in saved["steps"]
            if step.get("cognitive_status") in {"failed", "inconclusive"}]
        print(t("[review] http://{host}:{port}/；读取 {path}（不重新扫描）",
                host=args.host, port=args.port, path=directory), flush=True)
        app.run(host=args.host, port=args.port, debug=False)
        return 0
    except (OSError, ValueError) as exc:
        print(f"[error] {translate_text(str(exc))}", file=sys.stderr)
        return 1


def _wait_for_app(url: str, process, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(t("启动命令提前退出（{code}）", code=process.returncode))
        try:
            with urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(t("应用启动后 {timeout}s 内 URL 不可达：{url}", timeout=timeout, url=url))


def _stop_app(process) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        process.wait(timeout=3)
        return
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    # A wrapper can exit before a browser/dev-server descendant that ignores
    # SIGTERM. Always kill the dedicated group, even after its leader exits.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        from .ui.jobs import JobController

        if JobController._group_alive(process.pid) is not False:
            raise RuntimeError(t("无法确认应用子进程已回收"))
    process.wait(timeout=3)


if __name__ == "__main__":
    sys.exit(main())
