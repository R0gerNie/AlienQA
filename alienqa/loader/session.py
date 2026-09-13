"""黑盒模式的登录态采集：起有头浏览器让用户手动登录，保存 Playwright storage_state。

场景：私有化部署时，用户自己的浏览器里已有登录态；黑盒 QA 需要一个能访问业务内容的会话。
用户跑 `python -m alienqa --login <url>`，在弹出的真实浏览器里登录一次，会话（cookies + localStorage）
保存为 JSON 文件；之后扫描时经 `Project.storage_state` 复用。
"""
from __future__ import annotations

from pathlib import Path


def capture_session(url: str, out_path: str | Path) -> Path:
    """起有头 Chromium，用户手动登录后按回车，把 storage_state 保存到 out_path。"""
    from playwright.sync_api import sync_playwright

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)
        input(f"请在浏览器里完成登录，然后回到终端按回车保存会话 → {out}\n")
        context.storage_state(path=str(out))
        browser.close()
    return out
