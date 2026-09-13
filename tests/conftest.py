"""共享测试夹具：本地 HTTP 服务（无数据库）。"""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # 静默请求日志
        pass


@pytest.fixture(scope="module")
def http_base_url():
    handler = partial(_QuietHandler, directory=str(FIXTURES))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
