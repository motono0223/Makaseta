"""Business rules for getting work done: starting, pausing, answering, reviewing tasks.

Routers call these; the runner does the model calls. A task has at most one open run: queued, running,
waiting (on a question), or finished-and-awaiting-review (succeeded with a pending tool_use id).
"""

import shutil
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import library
from .models import Agent, Deliverable, Message, Plan, Project, Run, Task

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
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "このタスクには回答待ちの質問がありません")
    return answer_run(session, run, body)


def answer_run(session: Session, run: Run, body: str) -> Message:
    """Answer the question a paused run (task or planning) is waiting on."""
    if run.status != "waiting" or run.pending_tool_use_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "回答待ちの質問がありません")
    message = post(session, sender="manager", kind="answer", agent_id=run.agent_id, project_id=run.project_id,
                   task_id=run.task_id, run_id=run.id, body=body)
    _resume(run, f"オフィス長の回答: {body}")
    if run.task_id is not None:
        place_task(session, session.get(Task, run.task_id), "in_progress")
    return message


def approve(session: Session, task: Task) -> list[Deliverable]:
    drafts = list(session.scalars(select(Deliverable).where(Deliverable.task_id == task.id,
                                                            Deliverable.status == "draft")))
    for d in drafts:
        target = library.resolve(d.room, d.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        library.keep_old_version(d.room, target)
        if d.file_path:
            shutil.copyfile(d.file_path, target)
        else:
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
    start_ready_dependents(session, task)
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


def talk_to_agent(session: Session, agent: Agent, body: str, answer_run_id: int | None = None) -> Message:
    """The office head writes in an agent's thread."""
    if answer_run_id is not None:
        run = session.get(Run, answer_run_id)
        if run is None or run.agent_id != agent.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "回答先の質問が見つかりません")
        return answer_run(session, run, body)

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
        assignee = session.get(Agent, task.assignee_id) if task.assignee_id else None
        if assignee is not None and not assignee.active:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"{assignee.name}さんは休暇中です。復帰させるか、担当者を変えてください")
        start_task(session, task)
    elif new == "done":
        approve(session, task)
    elif old in ("in_progress", "waiting") and new in ("backlog", "review"):
        cancel_task(session, task, "オフィス長がカードを移動しました")


# ---- dependencies ----

def ready(session: Session, task: Task) -> bool:
    """True when every task this one depends on is done."""
    if not task.depends_on:
        return True
    done = session.scalars(select(Task.id).where(Task.id.in_(task.depends_on), Task.status == "done")).all()
    return len(done) == len(set(task.depends_on))


def start_ready_dependents(session: Session, finished: Task) -> None:
    session.flush()
    for task in session.scalars(select(Task).where(Task.project_id == finished.project_id,
                                                   Task.status == "backlog", Task.assignee_id.is_not(None))):
        assignee = session.get(Agent, task.assignee_id)
        if assignee is None or not assignee.active:
            continue  # waits in the backlog until the assignee is back or someone else takes it
        if finished.id in (task.depends_on or []) and ready(session, task):
            place_task(session, task, "in_progress")
            start_task(session, task)


# ---- manager plans ----

MAX_PLAN_TASKS = 8


def primary_manager(project: Project) -> Agent | None:
    member = next((m for m in project.members if m.is_primary and m.agent.active), None)
    member = member or next((m for m in project.members if m.role.is_manager and m.agent.active), None)
    return member.agent if member else None


def request_plan(session: Session, project: Project, body: str) -> Plan:
    """The office head asks the project's contact manager to plan the work."""
    manager = primary_manager(project)
    if manager is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "このプロジェクトには依頼を受けられるマネージャーがいません")
    plan = Plan(project_id=project.id, agent_id=manager.id, request=body)
    session.add(plan)
    session.flush()
    post(session, sender="manager", kind="request", agent_id=manager.id, project_id=project.id, body=body)
    session.add(Run(kind="plan", agent_id=manager.id, project_id=project.id, plan_id=plan.id))
    return plan


def validate_plan(project: Project, args: dict) -> tuple[list[dict], list[str]]:
    """Turn propose_plan input into plan items, or explain what is wrong so the manager can fix it."""
    members = {m.agent.name: m.agent for m in project.members if m.agent.active}
    tasks = args.get("tasks") or []
    errors = []
    if not tasks:
        errors.append("tasks が空です")
    if len(tasks) > MAX_PLAN_TASKS:
        errors.append(f"タスクは{MAX_PLAN_TASKS}件以内にしてください")
    items = []
    for number, t in enumerate(tasks, start=1):
        title = str(t.get("title", "")).strip()
        assignee = members.get(str(t.get("assignee", "")).strip())
        deps = t.get("depends_on") or []
        if not title:
            errors.append(f"{number}番目: title が空です")
        if assignee is None:
            errors.append(f"{number}番目: 担当「{t.get('assignee')}」はメンバーにいません（{', '.join(members)}）")
        if any(not isinstance(d, int) or d < 1 or d >= number for d in deps):
            errors.append(f"{number}番目: depends_on には、それより前のタスクの番号だけを書けます")
        priority = t.get("priority") if t.get("priority") in ("high", "normal", "low") else "normal"
        items.append({
            "title": title[:200],
            "instructions": str(t.get("instructions", "")),
            "expected_output": str(t.get("expected_output", "")),
            "assignee_id": assignee.id if assignee else None,
            "priority": priority,
            "depends_on": [d for d in deps if isinstance(d, int)],
        })
    return items, errors


def approve_plan(session: Session, plan: Plan) -> list[Task]:
    if plan.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "承認できるのは提案中の計画だけです")
    project = session.get(Project, plan.project_id)
    members = {m.agent_id for m in project.members}
    created: list[Task] = []
    for item in plan.items:
        if item["assignee_id"] not in members:
            raise HTTPException(status.HTTP_409_CONFLICT, "計画の担当者がプロジェクトのメンバーから外れています。差し戻してください")
        task = Task(project_id=project.id, plan_id=plan.id, title=item["title"], instructions=item["instructions"],
                    expected_output=item["expected_output"], priority=item["priority"],
                    assignee_id=item["assignee_id"], requested_by_agent_id=plan.agent_id,
                    depends_on=[created[d - 1].id for d in item["depends_on"]])
        place_task(session, task, "backlog")
        session.add(task)
        session.flush()
        created.append(task)
    if plan.agent_id in members:
        wrap_up = Task(project_id=project.id, plan_id=plan.id, title=f"取りまとめ: {short_title(plan.request)}",
                       instructions="計画した各タスクの報告と成果物を確認し、オフィス長の依頼に対する最終報告をまとめてください。"
                                    f"\n\n依頼内容:\n{plan.request}",
                       expected_output="依頼への最終報告（必要なら成果物）", assignee_id=plan.agent_id,
                       requested_by_agent_id=plan.agent_id, depends_on=[t.id for t in created])
        place_task(session, wrap_up, "backlog")
        session.add(wrap_up)
        session.flush()
        created.append(wrap_up)
    plan.status = "approved"
    plan.decided_at = now()
    run = session.scalar(select(Run).where(Run.plan_id == plan.id).order_by(Run.id.desc()))
    if run is not None:
        run.pending_tool_use_id = None
        run.pending_results = []
    post(session, sender="manager", kind="review", agent_id=plan.agent_id, project_id=project.id,
         body=f"計画を承認しました（タスク{len(created)}件）。")
    for task in created:
        assignee = session.get(Agent, task.assignee_id)
        if not task.depends_on and assignee is not None and assignee.active:
            place_task(session, task, "in_progress")
            start_task(session, task)
    return created


def reject_plan(session: Session, plan: Plan, comment: str) -> Run:
    run = session.scalar(select(Run).where(Run.plan_id == plan.id).order_by(Run.id.desc()))
    if plan.status != "proposed" or run is None or run.pending_tool_use_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "差し戻せる計画がありません")
    post(session, sender="manager", kind="review", agent_id=plan.agent_id, project_id=plan.project_id,
         run_id=run.id, body=f"計画を差し戻しました。{comment}")
    plan.status = "drafting"
    _resume(run, f"オフィス長が計画を差し戻しました。コメント: {comment}\n指摘を踏まえて、もう一度 propose_plan で提案してください。")
    return run


def cancel_plan(session: Session, plan: Plan) -> None:
    if plan.status not in ("drafting", "proposed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "取り消せるのは作成中か提案中の計画だけです")
    for run in session.scalars(select(Run).where(Run.plan_id == plan.id, Run.status.in_(OPEN_RUN_STATUSES))):
        run.status, run.ended_at, run.error = "cancelled", now(), "オフィス長が依頼を取り消しました"
    plan.status = "cancelled"
    plan.decided_at = now()
    post(session, sender="manager", kind="review", agent_id=plan.agent_id, project_id=plan.project_id,
         body="依頼を取り消しました。")


def short_title(text: str, limit: int = 30) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first if len(first) <= limit else first[:limit] + "…"
