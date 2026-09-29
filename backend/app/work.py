"""Business rules for getting work done: starting, pausing, answering, reviewing tasks.

Routers call these; the runner does the model calls. A task has at most one open run: queued, running,
waiting (on a question), or finished-and-awaiting-review (succeeded with a pending tool_use id).
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import library
from .models import Agent, Deliverable, Message, Run, Task

OPEN_RUN_STATUSES = ("queued", "running", "waiting")
# pending_tool_use_id when a run ended with plain text instead of a tool call: resume with a text message.
TEXT_REPLY = "text"


def now() -> datetime:
    return datetime.now(timezone.utc)


def place_task(session: Session, task: Task, new_status: str, position: int | None = None) -> None:
    """Move a task into a kanban column, at a position (0 = top) or at the bottom."""
    column = list(session.scalars(
        select(Task).where(Task.project_id == task.project_id, Task.status == new_status, Task.id != task.id)
        .order_by(Task.rank, Task.id)
    ))
    column.insert(len(column) if position is None else min(position, len(column)), task)
    for rank, t in enumerate(column, start=1):
        t.rank = rank
    if new_status == "done" and task.status != "done":
        task.completed_at = now()
    elif new_status != "done":
        task.completed_at = None
    task.status = new_status


def open_run(session: Session, task: Task) -> Run | None:
    return session.scalar(select(Run).where(Run.task_id == task.id, Run.status.in_(OPEN_RUN_STATUSES))
                          .order_by(Run.id.desc()))


def run_awaiting_review(session: Session, task: Task) -> Run | None:
    return session.scalar(select(Run).where(Run.task_id == task.id, Run.status == "succeeded",
                                            Run.pending_tool_use_id.is_not(None)).order_by(Run.id.desc()))


def post(session: Session, *, sender: str, body: str, kind: str = "chat", agent_id: int | None = None,
         project_id: int | None = None, task_id: int | None = None, run_id: int | None = None) -> Message:
    message = Message(sender=sender, body=body, kind=kind, agent_id=agent_id, project_id=project_id,
                      task_id=task_id, run_id=run_id)
    session.add(message)
    return message


def start_task(session: Session, task: Task) -> Run | None:
    """Queue the assignee's work on a task that just moved to 作業中."""
    if open_run(session, task) is not None or task.assignee_id is None:
        return None
    review = run_awaiting_review(session, task)
    if review is not None:
        _resume(review, "オフィス長がこのタスクを作業中に戻しました。これまでの成果物を見直し、必要なら直してから、もう一度 finish で報告してください。")
        return review
    run = Run(kind="task", agent_id=task.assignee_id, project_id=task.project_id, task_id=task.id)
    session.add(run)
    session.flush()
    post(session, sender="manager", kind="instruction", agent_id=task.assignee_id, project_id=task.project_id,
         task_id=task.id, run_id=run.id, body=f"タスク「{task.title}」をお願いします。")
    return run


def cancel_task(session: Session, task: Task, reason: str) -> None:
    run = open_run(session, task)
    if run is None:
        return
    run.status = "cancelled"
    run.ended_at = now()
    run.error = reason
    if run.agent_id:
        post(session, sender="system", kind="report", agent_id=run.agent_id, project_id=task.project_id,
             task_id=task.id, run_id=run.id, body=f"タスク「{task.title}」の作業を止めました（{reason}）。")


def answer_question(session: Session, task: Task, body: str) -> Message:
    run = open_run(session, task)
    if run is None or run.status != "waiting" or run.pending_tool_use_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "このタスクには回答待ちの質問がありません")
    message = post(session, sender="manager", kind="answer", agent_id=run.agent_id, project_id=task.project_id,
                   task_id=task.id, run_id=run.id, body=body)
    _resume(run, f"オフィス長の回答: {body}")
    place_task(session, task, "in_progress")
    return message


def approve(session: Session, task: Task) -> list[Deliverable]:
    drafts = list(session.scalars(select(Deliverable).where(Deliverable.task_id == task.id,
                                                            Deliverable.status == "draft")))
    for d in drafts:
        target = library.resolve(d.room, d.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(d.content, encoding="utf-8")
        library.index_file(session, d.room, target, created_by_kind="agent", agent_id=d.agent_id,
                           task_id=task.id, force=True)
        d.status = "approved"
        d.decided_at = now()
    review = run_awaiting_review(session, task)
    if review is not None:
        review.pending_tool_use_id = None
        review.pending_results = []
    if task.status != "done":
        place_task(session, task, "done")
    if task.assignee_id:
        saved = "、".join(f"{d.room}/{d.path}" for d in drafts)
        post(session, sender="manager", kind="review", agent_id=task.assignee_id, project_id=task.project_id,
             task_id=task.id, body=f"タスク「{task.title}」を承認しました。" + (f"成果物を保存しました: {saved}" if saved else ""))
    return drafts


def reject(session: Session, task: Task, comment: str) -> Run:
    review = run_awaiting_review(session, task)
    if review is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "差し戻せる報告がありません")
    for d in session.scalars(select(Deliverable).where(Deliverable.task_id == task.id,
                                                       Deliverable.status == "draft")):
        d.status = "rejected"
        d.decided_at = now()
    post(session, sender="manager", kind="review", agent_id=review.agent_id, project_id=task.project_id,
         task_id=task.id, run_id=review.id, body=f"タスク「{task.title}」を差し戻しました。{comment}")
    _resume(review, f"オフィス長から差し戻されました。コメント: {comment}\n"
                    "指摘に対応し、必要なら成果物を提出し直してから、もう一度 finish で報告してください。")
    place_task(session, task, "in_progress")
    return review


def _resume(run: Run, reply: str) -> None:
    """Answer the tool call the run paused on and put it back in the queue."""
    if run.pending_tool_use_id == TEXT_REPLY:
        content = [{"type": "text", "text": reply}]
    else:
        content = list(run.pending_results) + [
            {"type": "tool_result", "tool_use_id": run.pending_tool_use_id, "content": reply}
        ]
    run.transcript = list(run.transcript) + [{"role": "user", "content": content}]
    flag_modified(run, "transcript")
    run.pending_tool_use_id = None
    run.pending_results = []
    run.status = "queued"
    run.ended_at = None
    run.error = ""


def talk_to_agent(session: Session, agent: Agent, body: str, answer_task_id: int | None = None) -> Message:
    """The office head writes in an agent's thread."""
    if answer_task_id is not None:
        task = session.get(Task, answer_task_id)
        if task is None or task.assignee_id != agent.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "回答先のタスクが見つかりません")
        return answer_question(session, task, body)

    running = session.scalar(select(Run).where(Run.agent_id == agent.id, Run.kind == "task",
                                               Run.status.in_(("queued", "running"))).order_by(Run.id))
    if running is not None:
        # A task is in progress: the runner picks this up as an extra instruction at its next step.
        return post(session, sender="manager", kind="instruction", agent_id=agent.id, project_id=running.project_id,
                    task_id=running.task_id, body=body)

    message = post(session, sender="manager", kind="chat", agent_id=agent.id, body=body)
    session.flush()
    session.add(Run(kind="chat", agent_id=agent.id))
    return message


def on_status_change(session: Session, task: Task, old: str, new: str) -> None:
    """Side effects of moving a task on the kanban by hand."""
    if old == new:
        return
    if new == "in_progress":
        start_task(session, task)
    elif new == "done":
        approve(session, task)
    elif old in ("in_progress", "waiting") and new in ("backlog", "review"):
        cancel_task(session, task, "オフィス長がカードを移動しました")
