"""queue/worker.py — worker 轮询 + 分发

读类并发、写类串行(claim SQL 保证)。LLM 任务用信号量限流。
"""
from __future__ import annotations

import signal
import threading
import time

from app.core.config import get_settings
from app.core.logging import get_logger
from app.queue import queue
from app.queue.handlers import JOB_HANDLERS

log = get_logger("queue.worker")

LLM_JOB_TYPES = frozenset({"commit_analyze", "wiki_gen"})
_stop = threading.Event()


def _llm_semaphore() -> threading.Semaphore:
    s = get_settings()
    return threading.Semaphore(s.queue.llm_workers)


_LLM_SEM = _llm_semaphore()


def _process(job: dict) -> None:
    handler = JOB_HANDLERS.get(job["type"])
    if not handler:
        queue.fail(job["id"], f"unknown job type: {job['type']}")
        return
    is_llm = job["type"] in LLM_JOB_TYPES
    try:
        if is_llm:
            _LLM_SEM.acquire()
        log.info("worker processing J-%d %s", job["id"], job["type"])
        handler(job)
        queue.complete(job["id"])
    except Exception as e:  # noqa: BLE001
        log.exception("job J-%d failed", job["id"])
        queue.fail(job["id"], str(e))
    finally:
        if is_llm:
            _LLM_SEM.release()


def _worker_loop(worker_id: str) -> None:
    s = get_settings()
    log.info("worker %s started", worker_id)
    while not _stop.is_set():
        try:
            job = queue.claim(worker_id)
        except Exception as e:  # noqa: BLE001
            log.error("claim error: %s", e)
            job = None
        if job:
            _process(job)
        else:
            time.sleep(s.queue.poll_interval_s)
    log.info("worker %s stopped", worker_id)


def run_workers() -> None:
    """启动 worker 池(独立进程入口)。"""
    from app.db.session import init_db
    init_db()
    s = get_settings()
    threads = []
    for i in range(s.queue.workers):
        t = threading.Thread(target=_worker_loop, args=(f"worker-{i+1}",), daemon=True)
        t.start()
        threads.append(t)

    def _handle_sig(*_):
        log.info("shutting down workers...")
        _stop.set()

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)
    while not _stop.is_set():
        time.sleep(1)
    for t in threads:
        t.join(timeout=5)


if __name__ == "__main__":
    run_workers()
