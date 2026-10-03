"""Shared, local-only scan input and preparation checks for CLI and console."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

from .i18n import get_language, normalize_language, t


def valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return (parsed.scheme in {'http', 'https'} and bool(parsed.hostname)
                and parsed.port != 0 and parsed.username is None and parsed.password is None
                and not any(c.isspace() for c in value))
    except (ValueError, TypeError):
        return False


def validate_session(filename: str) -> None:
    if not filename:
        return
    try:
        state = json.loads(Path(filename).read_text(encoding='utf-8'))
        if not isinstance(state, dict) or not all(isinstance(state.get(key, []), list) for key in ('cookies', 'origins')):
            raise ValueError(t('需要 cookies/origins 列表'))
        for cookie in state.get('cookies', []):
            if not isinstance(cookie, dict) or not all(isinstance(cookie.get(k), str) for k in ('name', 'value')):
                raise ValueError(t('cookie 缺少字符串 name/value'))
            if not (valid_url(cookie.get('url', '')) or
                    (isinstance(cookie.get('domain'), str) and cookie['domain'] and isinstance(cookie.get('path'), str))):
                raise ValueError(t('cookie 需要有效 url 或 domain/path'))
            for key in ('httpOnly', 'secure'):
                if key in cookie and type(cookie[key]) is not bool:
                    raise ValueError(t('cookie {key} 需要布尔值', key=key))
            if 'expires' in cookie and (type(cookie['expires']) not in (int, float) or not math.isfinite(cookie['expires'])):
                raise ValueError(t('cookie expires 需要有限数值'))
            if 'sameSite' in cookie and cookie['sameSite'] not in ('Strict', 'Lax', 'None'):
                raise ValueError(t('cookie sameSite 无效'))
        for origin in state.get('origins', []):
            if not isinstance(origin, dict) or not valid_url(origin.get('origin', '')) or not isinstance(origin.get('localStorage', []), list):
                raise ValueError(t('origin/localStorage 结构无效'))
            for row in origin.get('localStorage', []):
                if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ('name', 'value')):
                    raise ValueError(t('localStorage 需要字符串 name/value'))
    except (OSError, ValueError, UnicodeError) as exc:
        # JSON decoder excerpts and cookie contents can include private values.
        reason = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else t('文件缺失、不可读取或 JSON 无效')
        raise ValueError(t('登录态文件无法读取：{reason}', reason=reason)) from None


@dataclass(frozen=True)
class ScanInput:
    mode: str = 'browser'
    project_path: str = ''
    base_url: str = ''
    storage_state: str = ''
    unit: str = ''
    instructions: str = ''
    app_path: str = ''
    samples: int = 2
    max_actions: int = 10
    max_seconds: float = 300
    startup_timeout: float = 30
    browser: str = 'chrome'
    static_entry: str = ''
    base_path: str = '/'
    spa_fallback: bool = False
    language: str = 'zh'

    @classmethod
    def from_dict(cls, data: dict):
        strings = ('mode', 'project_path', 'url', 'base_url', 'storage_state', 'unit', 'instructions', 'app_path', 'browser', 'static_entry', 'base_path')
        if any(data.get(k) is not None and not isinstance(data[k], str) for k in strings):
            raise ValueError(t('扫描参数必须是字符串'))
        values = {k: (data.get(k) or '').strip() for k in strings}
        values['base_url'] = values.pop('url') or values['base_url']
        values['mode'] = values['mode'] or ('browser' if values['base_url'] and not values['project_path'] else 'source')
        values['browser'] = values['browser'] or 'chrome'
        if values['mode'] not in ('browser', 'source'):
            raise ValueError(t('扫描模式只允许 source/browser'))
        if values['browser'] not in ('chrome', 'chromium'):
            raise ValueError(t('浏览器只允许 chrome/chromium'))
        if values['mode'] == 'source' and (not values['project_path'] or not Path(values['project_path']).is_dir()):
            raise ValueError(t('缺少项目路径或目录不存在'))
        if (values['mode'] == 'browser' or values['base_url']) and not valid_url(values['base_url']):
            raise ValueError(t('需要有效的 HTTP/HTTPS URL（不含账号密码）'))
        if values['mode'] == 'browser' and values['app_path']:
            raise ValueError(t('应用选择需要源码目录'))
        for key, default in (('samples', 2), ('max_actions', 10), ('max_seconds', 300), ('startup_timeout', 30)):
            number = data.get(key, default)
            if type(number) not in (int, float) or not math.isfinite(number) or number <= 0:
                raise ValueError(t('动作数、采样次数及时间预算必须是有限正数'))
            if key in ('samples', 'max_actions') and type(number) is not int:
                raise ValueError(t('动作数和采样次数必须为正整数'))
            values[key] = number
        from .static_server import normalize_base_path
        values['base_path'] = normalize_base_path(values['base_path'] or '/')
        values['spa_fallback'] = data.get('spa_fallback', False)
        if type(values['spa_fallback']) is not bool:
            raise ValueError(t('history 回退必须是布尔值'))
        if (values['mode'] == 'browser' or values['base_url']) and (values['spa_fallback'] or values['base_path'] != '/' or values['static_entry']):
            raise ValueError(t('静态页面、部署前缀和 history 回退仅适用于本机静态服务；实际 URL 已包含部署条件'))
        values['language'] = normalize_language(data.get('language', get_language()))
        validate_session(values['storage_state'])
        return cls(**values)

    def budget(self):
        return {key: getattr(self, key) for key in ('samples', 'max_actions', 'max_seconds')}


def select_project(loader, directory: str, app_path: str = ''):
    project = loader.load(directory)
    root = Path(project.root).resolve()
    if app_path:
        selected = (root / app_path).resolve()
        if not selected.is_relative_to(root) or not selected.is_dir():
            raise ValueError(t('应用路径必须是项目内部的目录'))
        if (selected / "package.json").is_file():
            return loader.load(directory, app_manifest=(selected / "package.json").relative_to(root).as_posix())
        if project.frontend_apps:
            raise ValueError(t("所选应用目录缺少 package.json"))
        return loader.load(str(selected))
    if len(project.frontend_apps) > 1:
        choices = ', '.join(app.base_dir or '.' for app in project.frontend_apps)
        raise ValueError(t('检测到多个前端应用，请显式选择应用目录：{choices}', choices=choices))
    return project


def static_directory(project, base_path='/') -> Path:
    from .loader.artifacts import static_entry
    return static_entry(project, base_path=base_path)[0]


def validate_config(config) -> None:
    if not math.isfinite(config.request_timeout) or config.request_timeout <= 0:
        raise ValueError(t('模型请求超时必须是有限正数'))
    missing = [role for role in ('gist', 'expectation', 'visual', 'judge')
               if not config.role(role) or not isinstance(config.role(role).model, str) or not config.role(role).model.strip()]
    if missing:
        raise ValueError(t('扫描模型配置缺少：{roles}', roles=', '.join(missing)))


def check_output(directory) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory):
        pass


def check_url(url: str, timeout: float = 3) -> str:
    try:
        with urlopen(url, timeout=timeout) as response:
            return response.geturl()
    except HTTPError as response:
        # HTTP error pages are reachable targets and may contain QA evidence.
        return response.geturl()
    except OSError as exc:
        raise ValueError(t('运行 URL 不可达：{error}', error=type(exc).__name__)) from None


def check_browser(browser: str) -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as runtime:
        if browser == 'chromium':
            installed = Path(runtime.chromium.executable_path).is_file()
        else:
            import os
            import shutil
            import sys
            paths = {'darwin': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                     'win32': str(Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe')}
            installed = Path(paths.get(sys.platform, '/opt/google/chrome/chrome')).is_file() or bool(shutil.which('google-chrome'))
        if not installed:
            raise ValueError(t('本地浏览器未安装；请安装所选 Chrome 或 Playwright Chromium'))


def source_context(project):
    """Persist loader facts for humans/investigation, never expectation prompts."""
    return {key: getattr(project, key) for key in ('root', 'app_dir', 'selected_manifest',
            'framework', 'routes', 'route_hints', 'entry_points', 'environment', 'loader_audit', 'artifacts')}


def serve_project(project, entry='', base_path='/', spa_fallback=False):
    from .loader.artifacts import static_entry
    from .static_server import serve
    directory, entry = static_entry(project, entry, base_path)
    server, base = serve(directory, base_path=base_path, spa_fallback=entry if spa_fallback else False)
    project.base_url = base + entry
    project.environment['base_url_status'] = 'actual_static_service'
    project.entry_points = [(directory / entry).relative_to(Path(project.root)).as_posix()]
    project.artifacts['static_server'] = {'directory': str(directory), 'port': server.server_port,
        'base_path': base_path, 'spa_fallback': entry if spa_fallback else False, 'entry': entry}
    if project.framework == 'Unknown':
        project.framework = 'Static HTML'
    return server, entry
