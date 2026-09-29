"""Background worker: takes queued runs from the database and executes them, a few at a time."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, update

from . import runner, work
from .models import Agent, Run, Task
from .work import post

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0


class Worker:
    def __init__(self, session_factory, max_concurrent: int):
        self._session_factory = session_factory
        self._slots = threading.Semaphore(max_concurrent)
        self._pool = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="run")
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="run-dispatcher", daemon=True)

    def start(self) -> None:
        self._recover()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=5)
        self._pool.shutdown(wait=False, cancel_futures=True)

    def wake(self) -> None:
        """Look for queued runs now instead of at the next poll."""
        self._wake.set()

    def _recover(self) -> None:
        """Runs that were executing when the app stopped cannot continue mid-call: mark them interrupted."""
        with self._session_factory()() as session:
            for run in session.scalars(select(Run).where(Run.status == "running")):
                run.status = "interrupted"
                run.error = "アプリが停止したため中断しました。再実行できます"
                run.ended_at = work.now()
                task = session.get(Task, run.task_id) if run.task_id else None
                post(session, sender="system", kind="report", agent_id=run.agent_id, project_id=run.project_id,
                     task_id=run.task_id, run_id=run.id,
                     body=f"タスク「{task.title}」の作業は、アプリの停止で中断しました。" if task
                     else "返信の途中でアプリが停止しました。")
            session.execute(update(Agent).where(Agent.status == "working").values(status="idle"))
            session.commit()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._dispatch()
            except Exception:  # noqa: BLE001 - keep dispatching
                log.exception("dispatch failed")
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()

    def _dispatch(self) -> None:
        while self._slots.acquire(blocking=False):
            run_id = self._claim()
            if run_id is None:
                self._slots.release()
                return
            self._pool.submit(self._execute, run_id)

    def _claim(self) -> int | None:
        with self._session_factory()() as session:
            run = session.scalar(select(Run).where(Run.status == "queued").order_by(Run.id)
                                 .with_for_update(skip_locked=True).limit(1))
            if run is None:
                return None
            run.status = "running"
            session.commit()
            return run.id

    def _execute(self, run_id: int) -> None:
        try:
            with self._session_factory()() as session:
                runner.execute(session, run_id)
        finally:
            self._slots.release()
            self._wake.set()
