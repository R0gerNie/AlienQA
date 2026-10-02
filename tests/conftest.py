"""共享测试夹具：本地 HTTP 服务（无数据库）。"""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser):
    parser.addoption("--run-baselines", action="store_true", default=False,
                     help="Include externally cloned application baseline/acceptance tests")
    parser.addoption("--run-applications", action="store_true", default=False, help="Include explicitly prepared pinned upstream small application")
    parser.addoption("--run-frameworks", action="store_true", default=False,
                     help="Include explicitly prepared local React/Vue/Next mechanism fixtures")


def pytest_ignore_collect(collection_path, config):
    # External repositories are an explicit integration suite, not a requirement
    # for running the self-contained tests from a clean checkout.
    external = {"test_baselines.py", "test_project_loader_acceptance.py"}
    if collection_path.name == "test_t09_real_application.py" and not config.getoption("--run-applications"):
        return True
    if collection_path.name in {"test_t02_frameworks.py", "test_t01_frameworks.py"} and not config.getoption("--run-frameworks"):
        return True
    return collection_path.name in external and not config.getoption("--run-baselines")


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
