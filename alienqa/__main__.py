"""AlienQA 正式入口：`python -m alienqa` 跑全链路 01→12，产出 HTML 报告。

密钥一律从环境变量读取；未设置时回退到本机约定俗成的 key 文件
（D:\\dskey.txt → DEEPSEEK_API_KEY，D:\\alikey.txt → DASHSCOPE_API_KEY），
可用 ALIENQA_*_KEY_FILE 环境变量覆盖路径。
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .llm import load_config
from .loader import Project, VisibleFile
from .pipeline import AlienQAPipeline
from .review import HumanReview, ReportBuilder, ReviewState, create_app

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


def _serve(directory: str) -> tuple:
    """起一个本地静态服务器，返回 (server, base_url)。"""

    class _Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D401
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _build_project(root: Path, base_url: str, framework: str, routes: str, entry: str) -> Project:
    return Project(
        root=str(root),
        framework=framework,
        routes=[r.strip() for r in routes.split(",") if r.strip()],
        entry_points=[entry],
        visible_files=[VisibleFile(path=entry, role="page", lines=60)],
        base_url=base_url,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m alienqa", description="AlienQA 全链路测试（01→12）")
    parser.add_argument("--config", default=str(REPO / "config" / "config.yaml"), help="LLM 配置 yaml")
    parser.add_argument("--output", default=str(REPO / "report.html"), help="HTML 报告输出路径")
    parser.add_argument("--url", default=None, help="被测页面 URL；缺省时自动 serve 静态目录")
    parser.add_argument("--serve", default=str(REPO / "tests" / "fixtures"), help="--url 缺省时 serve 的静态目录")
    parser.add_argument("--project-root", default=str(REPO / "tests" / "fixtures"), help="项目根目录（供 02/11 读源码）")
    parser.add_argument("--framework", default="Static HTML")
    parser.add_argument("--routes", default="/demo-app", help="逗号分隔的页面路由")
    parser.add_argument("--entry", default="demo-app/index.html", help="入口文件（相对 project-root）")
    parser.add_argument("--samples", type=int, default=2, help="08 预期生成采样次数")
    parser.add_argument("--max-actions", type=int, default=10, help="探索动作上限")
    parser.add_argument("--headful", action="store_true", help="有头运行浏览器（默认无头）")
    parser.add_argument("--review", action="store_true", help="收集证据后启动人工审核 WebUI（逐条拨动采信开关，再生成终稿）")
    parser.add_argument("--ui", action="store_true", help="启动用户前端控制台（密钥 / 项目扫描 / 历史浏览）")
    parser.add_argument("--login", default=None, metavar="URL", help="起有头浏览器手动登录并保存 storage_state（配合 --session-out）")
    parser.add_argument("--session-out", default=str(REPO / "config" / "session.json"), help="登录态输出路径（默认 config/session.json）")
    parser.add_argument("--host", default="127.0.0.1", help="WebUI 监听地址")
    parser.add_argument("--port", type=int, default=5000, help="WebUI 端口")
    args = parser.parse_args(argv)

    _load_keys()

    if args.login:
        from .loader import capture_session

        out = capture_session(args.login, args.session_out)
        print(f"[login] 已保存登录态 → {out}", flush=True)
        return 0

    if args.ui:
        from .ui import create_ui_app

        ui = create_ui_app(
            args.config,
            settings_path=str(REPO / "config" / "config.local.yaml"),
            runs_dir=str(REPO / "runs"),
        )
        print(f"[ui] 控制台：http://{args.host}:{args.port}/", flush=True)
        ui.run(host=args.host, port=args.port, debug=False)
        return 0

    config = load_config(args.config)
    project_root = Path(args.project_root).resolve()

    srv = None
    if args.url:
        base_url = args.url
    else:
        srv, base = _serve(str(project_root))
        base_url = f"{base}/{args.entry.lstrip('/')}"
        print(f"[serve] {base_url}", flush=True)

    project = _build_project(project_root, base_url, args.framework, args.routes, args.entry)
    print("[01] Project 装载完成", flush=True)

    pipeline = AlienQAPipeline(
        config,
        samples=args.samples,
        headless=not args.headful,
        max_actions=args.max_actions,
        auto_confirm=not args.review,
    )
    try:
        if args.review:
            result = pipeline.collect(project)
            review = HumanReview(ReviewState())
            report_builder = ReportBuilder(pipeline.client)
            app = create_app(
                review,
                report_builder,
                investigations=result.investigations,
                report_path=args.output,
            )
            app.config["evidences"] = result.evidences
            print(
                f"[review] 打开 http://{args.host}:{args.port}/ 逐条拨动采信开关；"
                f"全部审核后点「查看报告」生成终稿 → 写入 {args.output}",
                flush=True,
            )
            app.run(host=args.host, port=args.port, debug=False)
        else:
            result = pipeline.run(project, output_path=args.output)
            print(
                f"[done] 全链路 01→12 跑通：证据 {len(result.evidences)} → Issue {len(result.issues)} "
                f"→ 报告 {args.output}（采信 {result.report.accepted_count}/{result.report.total_count}）",
                flush=True,
            )
    finally:
        if srv is not None:
            srv.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
