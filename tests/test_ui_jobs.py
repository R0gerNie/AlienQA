"""后台任务取消必须终止资源后才释放并发名额。"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from alienqa.ui.jobs import JobController


def _long_worker(marker):
    subprocess.Popen([sys.executable, "-c", "import pathlib,sys,time; time.sleep(3); pathlib.Path(sys.argv[1]).write_text('alive')", marker])
    Path(marker + ".started").write_text("started")
    time.sleep(20)


def _quick_worker():
    return None


def test_slot_reservation_is_atomic():
    jobs = JobController()
    barrier = threading.Barrier(5)
    results = []
    def claim():
        barrier.wait()
        results.append(jobs.reserve())
    threads = [threading.Thread(target=claim) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(token is not None for token in results) == 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group regression")
def test_timeout_kills_worker_and_descendants_before_releasing_slot(tmp_path):
    jobs = JobController()
    token = jobs.reserve()
    finished = threading.Event()
    outcome = []
    marker = tmp_path / "descendant.txt"
    jobs.start(token, "scan", _long_worker, (str(marker),), lambda status: (outcome.append(status), finished.set()), timeout=2)
    assert jobs.reserve() is None
    deadline = time.monotonic() + 1.8
    while not Path(str(marker) + ".started").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert Path(str(marker) + ".started").exists()
    assert finished.wait(5)
    assert outcome == ["timeout"]
    time.sleep(1.5)
    assert not marker.exists()
    assert jobs.reserve() is not None


def test_stop_releases_slot_after_process_exit(tmp_path):
    jobs = JobController()
    token = jobs.reserve()
    finished = threading.Event()
    outcome = []
    jobs.start(token, "scan", _long_worker, (str(tmp_path / "cancelled.txt"),), lambda status: (outcome.append(status), finished.set()), timeout=30)
    assert jobs.cancel("scan")
    assert finished.wait(5)
    assert outcome == ["cancelled"]
    assert jobs.reserve() is not None


def test_success_releases_slot():
    jobs = JobController()
    token = jobs.reserve()
    finished = threading.Event()
    outcome = []
    jobs.start(token, "scan", _quick_worker, (), lambda status: (outcome.append(status), finished.set()), timeout=5)
    assert finished.wait(10)
    assert outcome == [None]
    assert jobs.reserve() is not None


@pytest.mark.parametrize("group_alive, expected", [(False, True), (True, False), (None, False)])
def test_signal_permission_error_requires_proof_of_descendant_exit(monkeypatch, group_alive, expected):
    from types import SimpleNamespace

    class Worker:
        pid = 424242
        def is_alive(self):
            return False
        def join(self, timeout=None):
            pass
    ready = threading.Event()
    ready.set()
    def forbidden(*args):
        raise PermissionError("signal denied")
    monkeypatch.setattr(os, "killpg", forbidden)
    monkeypatch.setattr(JobController, "_group_alive", staticmethod(lambda group: group_alive))
    assert JobController._terminate(SimpleNamespace(process=Worker(), ready=ready)) is expected


def _leaving_child(marker):
    subprocess.Popen([sys.executable, '-c',
        "import pathlib,sys,time,signal; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(2); pathlib.Path(sys.argv[1]).write_text('orphan')", marker])


@pytest.mark.skipif(os.name != 'posix', reason='POSIX descendant ownership')
def test_success_cleans_descendants_before_releasing_slot(tmp_path):
    jobs = JobController()
    done = threading.Event()
    marker = tmp_path / 'orphan.txt'
    jobs.start(jobs.reserve(), 'scan', _leaving_child, (str(marker),), lambda _: done.set(), timeout=10)
    assert done.wait(10)
    time.sleep(2.2)
    assert not marker.exists()
    assert jobs.reserve() is not None


def test_cleanup_failed_slot_cannot_be_released_manually(monkeypatch):
    jobs = JobController()
    token = jobs.reserve()
    done = threading.Event()
    monkeypatch.setattr(jobs, '_terminate', lambda job: False)
    jobs.start(token, 'scan', _quick_worker, (), lambda status: done.set() if status == 'cleanup_failed' else None, timeout=10)
    assert done.wait(10)
    jobs.release(token)
    assert jobs.reserve() is None
