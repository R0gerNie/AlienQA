"""Selected-app artifact facts; directory names do not prove runnable HTML."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ..static_server import normalize_base_path


class _Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.resources = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.resources.append(attrs['src'])
        if tag == 'link' and 'stylesheet' in attrs.get('rel', '').split() and attrs.get('href'):
            self.resources.append(attrs['href'])


def validate_html(directory, entry, base_path='/'):
    directory = Path(directory).resolve()
    path = (directory / entry).resolve()
    if not path.is_relative_to(directory) or path.suffix.lower() != '.html' or not path.is_file():
        raise ValueError('未找到可运行的 HTML 入口，请提供项目运行 URL')
    text = path.read_text(encoding='utf-8', errors='replace')
    if '%PUBLIC_URL%' in text:
        raise ValueError('HTML 引用未构建源码，请先启动项目并填写运行 URL')
    resources = _Resources()
    resources.feed(text)
    for reference in resources.resources:
        url = urlsplit(reference)
        if url.scheme in ('http', 'https', 'data') or url.netloc:
            continue  # external resources are observed by the browser, never fetched here
        resource = unquote(url.path)
        if not resource:
            continue
        if Path(resource).suffix.lower() in ('.tsx', '.jsx', '.vue', '.ts') or '/src/' in resource:
            raise ValueError('HTML 引用未构建源码，请先启动项目并填写运行 URL')
        if resource.startswith('/'):
            if base_path != '/' and resource.startswith(base_path):
                resource = resource[len(base_path):]
            elif base_path != '/':
                raise ValueError(f'静态资源不在部署前缀 {base_path} 内：{url.path}')
            else:
                resource = resource.lstrip('/')
            candidate = (directory / resource).resolve()
        else:
            candidate = (path.parent / resource).resolve()
        if not candidate.is_relative_to(directory) or not candidate.is_file():
            raise ValueError(f'静态 HTML 所需资源缺失：{url.path}；请提供完整产物或运行 URL')
    return path


def artifact_facts(project, base_path='/'):
    base_path = normalize_base_path(base_path)
    root = Path(project.app_dir or project.root).resolve()
    candidates = []
    for name in ('dist', 'build', 'out'):
        directory = root / name
        if not directory.is_dir() or not directory.resolve().is_relative_to(root):
            continue
        entries = sorted(path.name for path in directory.glob('*.html') if path.is_file())
        server = (directory / 'server').is_dir() or (directory / 'server.js').is_file()
        candidates.append({'kind': 'static' if entries and not server else 'service', 'directory': str(directory), 'entries': entries})
    if (root / '.next').is_dir():
        candidates.append({'kind': 'service', 'directory': str(root / '.next'), 'entries': []})
    return {'candidates': candidates, 'source_directory': str(root), 'base_path': base_path,
            'limitations': ['local HTML script/styles checked; external and transitive resources require browser observation']}


def static_entry(project, entry='', base_path='/'):
    base_path = normalize_base_path(base_path)
    facts = artifact_facts(project, base_path)
    candidates = [c for c in facts['candidates'] if c['kind'] == 'static']
    root = Path(project.app_dir or project.root).resolve()
    if candidates:
        directory = Path(candidates[0]['directory'])
        default = 'index.html' if (directory / 'index.html').is_file() else candidates[0]['entries'][0]
    else:
        if (root / 'package.json').is_file() or project.framework not in ('Unknown', 'Static HTML') or facts['candidates']:
            raise ValueError('框架源码/服务型产物需要先启动项目并填写运行 URL，或提供完整 dist/build/out 静态产物')
        directory = root
        entries = sorted(path.name for path in root.glob('*.html') if path.is_file())
        if not entries and not entry:
            raise ValueError('没有可直接运行的静态 HTML；请填写项目运行 URL')
        default = 'index.html' if 'index.html' in entries else entries[0] if entries else entry
    selected = entry or default
    validate_html(directory, selected, base_path)
    return directory, selected
