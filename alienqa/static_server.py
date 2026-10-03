"""Owned local static service; deployment mount and navigation-only SPA fallback."""
from .i18n import t
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import unquote, urlsplit


def normalize_base_path(value='/'):
    if not isinstance(value, str):
        raise ValueError(t('部署子路径必须是字符串'))
    path = unquote(value)
    if (not path.startswith('/') or path.startswith('//') or any(c in path for c in ('?', '#', '\\', '%'))
            or any(p in ('.', '..') for p in path.split('/')) or any(c.isspace() for c in path)):
        raise ValueError(t('部署子路径必须是站内绝对路径，例如 /tool/'))
    return path.rstrip('/') + '/' if path != '/' else '/'


class StaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, spa_fallback=False, base_path='/', **kwargs):
        self.spa_fallback = spa_fallback
        self.base_path = normalize_base_path(base_path)
        super().__init__(*args, **kwargs)

    def send_head(self):
        self._relative_location = False
        requested = urlsplit(self.path).path
        if self.base_path != '/':
            if requested == self.base_path.rstrip('/'):
                self.send_response(301)
                self.send_header('Location', self.base_path)
                self.end_headers()
                return None
            if not requested.startswith(self.base_path):
                self.send_error(404)
                return None
            requested = '/' + requested[len(self.base_path):]
            query = urlsplit(self.path).query
            self.path = requested + ('?' + query if query else '')
            self._relative_location = True
        destination = Path(self.translate_path(self.path))
        root = Path(self.directory).resolve()
        if not destination.resolve().is_relative_to(root):
            self.send_error(404)
            return None
        entry = 'index.html' if self.spa_fallback is True else str(self.spa_fallback or '')
        index = (root / entry).resolve()
        navigation = self.headers.get('Sec-Fetch-Dest') == 'document'
        relative = destination.resolve().relative_to(root).as_posix()
        if (entry and navigation and not destination.exists() and relative != 'api' and
                not relative.startswith('api/') and not Path(relative).suffix and
                index.is_relative_to(root) and index.is_file()):
            self.path = '/' + entry
        return super().send_head()

    def send_header(self, keyword, value):
        if keyword.lower() == 'location' and getattr(self, '_relative_location', False) and value.startswith('/'):
            value = self.base_path + value.lstrip('/')
        super().send_header(keyword, value)

    def log_message(self, format, *args):
        pass


def serve(directory, *, base_path='/', spa_fallback=False, port=0):
    base_path = normalize_base_path(base_path)
    server = ThreadingHTTPServer(('127.0.0.1', port), partial(StaticHandler,
        directory=str(directory), base_path=base_path, spa_fallback=spa_fallback))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_port}{base_path}'
