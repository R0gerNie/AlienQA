"""One atomic task slot backed by a cancellable, isolated process."""
from __future__ import annotations

import multiprocessing
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable


def _process_entry(ready, target, args) -> None:
    if os.name == "posix":
        os.setsid()
        # Give synchronous providers a chance to reap their separately isolated
        # subprocesses before the watchdog escalates to SIGKILL.
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
    ready.set()
    try:
        target(*args)
    except KeyboardInterrupt:
        pass


@dataclass
class _Job:
    token: str
    task_id: str = ""
    process: object | None = None
    ready: object | None = None
    cancel_requested: threading.Event | None = None
    cleanup_failed: bool = False


class JobController:
    """Reserve before any LLM work; release only after the worker has exited."""

    def __init__(self):
        self._lock = threading.Lock()
        self._active: _Job | None = None
        self._context = multiprocessing.get_context("spawn")

    def reserve(self) -> str | None:
        with self._lock:
            if self._active is not None:
                return None
            token = uuid.uuid4().hex
            self._active = _Job(token)
            return token

    def release(self, token: str) -> None:
        """Release an unused reservation (never a living worker)."""
        with self._lock:
            if self._active is None or self._active.token != token:
                return
            if self._active.cleanup_failed:
                return
            if self._active.process is not None and self._active.process.is_alive():
                return
            self._active = None

    def start(self, token: str, task_id: str, target: Callable, args: tuple,
              complete: Callable[[str | None], None], timeout: float) -> None:
        ready = self._context.Event()
        worker = self._context.Process(target=_process_entry, args=(ready, target, args))
        job = _Job(token, task_id, worker, ready, threading.Event())
        with self._lock:
            if self._active is None or self._active.token != token:
                raise RuntimeError("任务名额已失效")
            self._active = job
            try:
                worker.start()
            except BaseException:
                self._active = None
                raise
        threading.Thread(target=self._monitor, args=(job, complete, timeout), daemon=True).start()

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            job = self._active
            if job is None or job.task_id != task_id or job.cancel_requested is None:
                return False
            job.cancel_requested.set()
            return True

    @staticmethod
    def _group_alive(group: int) -> bool | None:
        """Distinguish living descendants from exited but unreaped processes."""
        try:
            listing = subprocess.run(["ps", "-eo", "pid=,pgid=,stat="], capture_output=True, text=True, check=True)
            for line in listing.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[1] == str(group) and not parts[2].startswith(("Z", "X")):
                    return True
            return False
        except (OSError, subprocess.SubprocessError):
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                pass
            return None

    @staticmethod
    def _terminate(job: _Job) -> bool:
        worker = job.process
        job.ready.wait(0.1)
        group = None
        if os.name == "posix" and job.ready.is_set():
            # The entry point establishes a dedicated session before opening
            # browsers or invoking the target. Its pid is its process group id.
            group = worker.pid
        if group is not None:
            try:
                os.killpg(group, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        elif os.name == "nt" and worker.is_alive():
            subprocess.run(["taskkill", "/PID", str(worker.pid), "/T", "/F"], capture_output=True, check=False)
        elif worker.is_alive():
            worker.terminate()
        worker.join(1)
        if group is not None:
            # The leader may have exited while browser descendants remain.
            try:
                os.killpg(group, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        elif worker.is_alive():
            worker.kill()
        worker.join(2)
        if worker.is_alive():
            return False
        if group is not None:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                alive = JobController._group_alive(group)
                if alive is False:
                    return True
                if alive is None:
                    return False
                time.sleep(0.05)
            return False
        return True

    def _monitor(self, job: _Job, complete: Callable, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        failure = None
        while job.process.is_alive():
            if job.cancel_requested.is_set():
                failure = "cancelled"
                break
            if time.monotonic() >= deadline:
                failure = "timeout"
                break
            job.process.join(0.1)
        if job.cancel_requested.is_set():
            failure = "cancelled"
        # Normal exit also owns descendants; completion requires cleanup proof.
        if not self._terminate(job):
            # Retain the slot if the OS has not confirmed process termination.
            job.cleanup_failed = True
            complete("cleanup_failed")
            return
        job.process.join()
        if failure is None and job.process.exitcode != 0:
            failure = "error"
        try:
            complete(failure)
        finally:
            self.release(job.token)
            job.process.close()
