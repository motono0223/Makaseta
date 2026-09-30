"""Business rules for getting work done: starting, pausing, answering, reviewing tasks.

Routers call these; the runner does the model calls. A task has at most one open run: queued, running,
waiting (on a question), or finished-and-awaiting-review (succeeded with a pending tool_use id).
"""

import shutil
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from . import library
from .config import get_settings
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
    return session.scalar(select(Run).where(Run.task_id == task.id, Run.kind == "task",
                                            Run.status.in_(OPEN_RUN_STATUSES)).order_by(Run.id.desc()))


def run_awaiting_review(session: Session, task: Task) -> Run | None:
    return session.scalar(select(Run).where(Run.task_id == task.id, Run.kind == "task", Run.status == "succeeded",
                                            Run.pending_tool_use_id.is_not(None))
                          .order_by(Run.id.desc()))


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
    if unfinished_subtasks(session, task):
        return None  # a parent waits in 作業中 until its subtasks are done, then its owner wraps up
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
    cancel_peer_review(session, task)
    if task.status != "done":
        place_task(session, task, "done")
    start_ready_dependents(session, task)
    _start_parent_if_ready(session, task)
    schedule(session, task.project_id)
    if task.assignee_id:
        saved = "、".join(f"{d.room}/{d.path}" for d in drafts)
        post(session, sender="manager", kind="review", agent_id=task.assignee_id, project_id=task.project_id,
             task_id=task.id, body=f"タスク「{task.title}」を承認しました。" + (f"成果物を保存しました: {saved}" if saved else ""))
        queue_reflection(session, task, "承認されました（このまま完了）", "")
    return drafts


def reject(session: Session, task: Task, comment: str) -> Run:
    review = run_awaiting_review(session, task)
    if review is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "差し戻せる報告がありません")
    cancel_peer_review(session, task)
    task.peer_rounds = 0
    for d in session.scalars(select(Deliverable).where(Deliverable.task_id == task.id,
                                                       Deliverable.status == "draft")):
        d.status = "rejected"
        d.decided_at = now()
    post(session, sender="manager", kind="review", agent_id=review.agent_id, project_id=task.project_id,
         task_id=task.id, run_id=review.id, body=f"タスク「{task.title}」を差し戻しました。{comment}")
    _resume(review, f"オフィス長から差し戻されました。コメント: {comment}\n"
                    "指摘に対応し、必要なら成果物を提出し直してから、もう一度 finish で報告してください。")
    place_task(session, task, "in_progress")
    queue_reflection(session, task, "差し戻されました（やり直し中）", comment)
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
    if old == "review" and new != "review":
        cancel_peer_review(session, task)


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
    parent = Task(project_id=project.id, title=short_title(body, 60), instructions=body,
                  expected_output="依頼への最終報告（サブタスクの結果の取りまとめ）", assignee_id=manager.id)
    place_task(session, parent, "backlog")
    session.add(parent)
    session.flush()
    plan = Plan(project_id=project.id, agent_id=manager.id, request=body, parent_task_id=parent.id, owns_parent=True)
    session.add(plan)
    session.flush()
    post(session, sender="manager", kind="request", agent_id=manager.id, project_id=project.id, task_id=parent.id,
         body=body)
    session.add(Run(kind="plan", agent_id=manager.id, project_id=project.id, plan_id=plan.id))
    return plan


def decompose(session: Session, task: Task) -> Plan:
    """Have the contact manager split a card into subtasks (the card becomes their parent)."""
    project = session.get(Project, task.project_id)
    manager = primary_manager(project)
    if manager is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "このプロジェクトには分解を任せられるマネージャーがいません")
    if task.status not in ("backlog", "in_progress") or open_run(session, task) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "作業中・レビュー中のタスクは分解できません")
    if planning(session, task):
        raise HTTPException(status.HTTP_409_CONFLICT, "このタスクはすでに分解中です")
    request = task.title + (f"\n\n{task.instructions}" if task.instructions else "")
    if task.expected_output:
        request += f"\n\n期待する成果物: {task.expected_output}"
    plan = Plan(project_id=project.id, agent_id=manager.id, request=request, parent_task_id=task.id)
    session.add(plan)
    session.flush()
    post(session, sender="manager", kind="request", agent_id=manager.id, project_id=project.id, task_id=task.id,
         body=f"タスク「{task.title}」をサブタスクに分けて、メンバーに割り振ってください。")
    session.add(Run(kind="plan", agent_id=manager.id, project_id=project.id, plan_id=plan.id))
    return plan


# Titles like 「〜のレビュー」 mark a review-only task; reviews belong on the producing task instead.
REVIEW_ONLY_WORDS = ("レビュー", "確認", "チェック", "校正", "査読")


def validate_plan(project: Project, args: dict) -> tuple[list[dict], list[str]]:
    """Turn propose_plan input into plan items, or explain what is wrong so the manager can fix it."""
    members = {m.agent.name: m.agent for m in project.members if m.agent.active}
    roles = {m.agent_id: m.role.key for m in project.members}
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
        reviewer_name = str(t.get("reviewer") or "").strip()
        reviewer = members.get(reviewer_name) if reviewer_name else None
        if reviewer_name and reviewer is None:
            errors.append(f"{number}番目: レビュー担当「{reviewer_name}」はメンバーにいません")
        if reviewer is not None and assignee is not None and reviewer.id == assignee.id:
            errors.append(f"{number}番目: 担当とレビュー担当は別の人にしてください")
        deps = t.get("depends_on") or []
        if title.rstrip("。 ").endswith(REVIEW_ONLY_WORDS) or (
                assignee is not None and roles.get(assignee.id) == "reviewer" and any(w in title for w in REVIEW_ONLY_WORDS)):
            errors.append(f"{number}番目: レビューや確認だけのタスクは作れません。確認する人は、成果物を作るタスクの reviewer に指定してください")
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
            "reviewer_id": reviewer.id if reviewer else None,
            "priority": priority,
            "depends_on": [d for d in deps if isinstance(d, int)],
        })
    return items, errors


def approve_plan(session: Session, plan: Plan) -> list[Task]:
    if plan.status != "proposed":
        raise HTTPException(status.HTTP_409_CONFLICT, "承認できるのは提案中の計画だけです")
    project = session.get(Project, plan.project_id)
    members = {m.agent_id for m in project.members}
    parent = session.get(Task, plan.parent_task_id) if plan.parent_task_id else None
    created: list[Task] = []
    for item in plan.items:
        if item["assignee_id"] not in members:
            raise HTTPException(status.HTTP_409_CONFLICT, "計画の担当者がプロジェクトのメンバーから外れています。差し戻してください")
        task = Task(project_id=project.id, plan_id=plan.id, title=item["title"], instructions=item["instructions"],
                    expected_output=item["expected_output"], priority=item["priority"],
                    assignee_id=item["assignee_id"], reviewer_id=item.get("reviewer_id"),
                    requested_by_agent_id=plan.agent_id, parent_id=parent.id if parent else None,
                    depends_on=[created[d - 1].id for d in item["depends_on"]])
        place_task(session, task, "backlog")
        session.add(task)
        session.flush()
        created.append(task)
    if parent is not None:
        # The manager who planned it wraps it up once every subtask is done.
        parent.assignee_id = plan.agent_id
        parent.plan_id = plan.id
        if parent.status == "backlog":
            place_task(session, parent, "in_progress")
    plan.status = "approved"
    plan.decided_at = now()
    run = session.scalar(select(Run).where(Run.plan_id == plan.id).order_by(Run.id.desc()))
    if run is not None:
        run.pending_tool_use_id = None
        run.pending_results = []
    post(session, sender="manager", kind="review", agent_id=plan.agent_id, project_id=project.id,
         body=f"計画を承認しました（タスク{len(created)}件）。")
    if project.auto_manage:
        schedule(session, project.id)
    else:
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
    parent = session.get(Task, plan.parent_task_id) if plan.parent_task_id else None
    if parent is not None and plan.owns_parent and not subtasks(session, parent):
        session.delete(parent)
    post(session, sender="manager", kind="review", agent_id=plan.agent_id, project_id=plan.project_id,
         body="依頼を取り消しました。")


def short_title(text: str, limit: int = 30) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first if len(first) <= limit else first[:limit] + "…"


# ---- growth ----

def queue_reflection(session: Session, task: Task, outcome: str, comment: str) -> None:
    """Have the assignee look back on a reviewed task and keep what it learned (runs in the background)."""
    if not get_settings().agent_reflection or task.assignee_id is None:
        return
    report = session.scalar(select(Message).where(Message.task_id == task.id, Message.sender == "agent",
                                                  Message.kind == "report").order_by(Message.id.desc()))
    earlier = session.scalars(select(Message.body).where(Message.task_id == task.id, Message.sender == "manager",
                                                         Message.kind == "review", Message.body.contains("差し戻"))
                              .order_by(Message.id)).all()
    parts = [
        "## 振り返る仕事",
        f"タスク: {task.title}",
        f"指示: {task.instructions or '（タイトルのとおり）'}",
        f"期待する成果物: {task.expected_output or '（指定なし）'}",
        "", "## あなたの報告", report.body if report else "（報告なし）",
        "", "## オフィス長の判断", outcome,
    ]
    if comment:
        parts.append(f"コメント: {comment}")
    if earlier:
        parts += ["", "## これまでの差し戻し", *[f"- {b}" for b in earlier]]
    parts += ["", "この仕事から、次の仕事に活かせる学びがあれば save_notes で業務メモに残してください。"]
    session.add(Run(kind="reflect", agent_id=task.assignee_id, project_id=task.project_id, task_id=task.id,
                    transcript=[{"role": "user", "content": [{"type": "text", "text": "\n".join(parts)}]}]))


# ---- peer review by a reviewer agent ----

MAX_PEER_ROUNDS = 2


def send_to_review(session: Session, task: Task) -> None:
    """After the assignee reports: the reviewer agent checks first, then the office head."""
    reviewer = session.get(Agent, task.reviewer_id) if task.reviewer_id else None
    if reviewer is None or not reviewer.active or reviewer.id == task.assignee_id:
        task.review_stage = "manager"
        return
    if task.peer_rounds >= MAX_PEER_ROUNDS:
        task.review_stage = "manager"
        post(session, sender="system", kind="report", agent_id=reviewer.id, project_id=task.project_id,
             task_id=task.id, body=f"「{task.title}」はレビューでの差し戻しが{MAX_PEER_ROUNDS}回に達したため、オフィス長の確認に回しました。")
        return
    task.review_stage = "peer"
    session.add(Run(kind="review", agent_id=reviewer.id, project_id=task.project_id, task_id=task.id))
    post(session, sender="system", kind="report", agent_id=task.assignee_id, project_id=task.project_id,
         task_id=task.id, body=f"「{task.title}」の確認を、レビュー担当の{reviewer.name}さんに依頼しました。")


def peer_approve(session: Session, task: Task, reviewer: Agent, comment: str) -> None:
    task.review_stage = "manager"
    post(session, sender="agent", kind="review", agent_id=reviewer.id, project_id=task.project_id,
         task_id=task.id, body=f"「{task.title}」をレビューしました。問題ありません。\n\n{comment}")


def peer_request_changes(session: Session, task: Task, reviewer: Agent, comment: str) -> None:
    task.peer_rounds += 1
    task.review_stage = None
    post(session, sender="agent", kind="review", agent_id=reviewer.id, project_id=task.project_id,
         task_id=task.id, body=f"「{task.title}」の修正をお願いしました。\n\n{comment}")
    run = run_awaiting_review(session, task)
    if run is not None:
        _resume(run, f"レビュー担当の{reviewer.name}さんから修正の依頼がありました:\n{comment}\n"
                     "指摘に対応し、必要なら成果物を提出し直してから、もう一度 finish で報告してください。")
    place_task(session, task, "in_progress")


def cancel_peer_review(session: Session, task: Task) -> None:
    for run in session.scalars(select(Run).where(Run.task_id == task.id, Run.kind == "review",
                                                 Run.status.in_(OPEN_RUN_STATUSES))):
        run.status, run.ended_at, run.error = "cancelled", now(), "オフィス長がレビューを進めました"
    task.review_stage = None


# ---- subtasks and a manager-run backlog ----

PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


def subtasks(session: Session, task: Task) -> list[Task]:
    return list(session.scalars(select(Task).where(Task.parent_id == task.id).order_by(Task.id)))


def unfinished_subtasks(session: Session, task: Task) -> int:
    return session.scalar(select(func.count()).select_from(Task).where(
        Task.parent_id == task.id, Task.status != "done")) or 0


def planning(session: Session, task: Task) -> bool:
    """True while a plan to split this task is being drafted or awaits approval."""
    return session.scalar(select(Plan.id).where(Plan.parent_task_id == task.id,
                                                Plan.status.in_(("drafting", "proposed"))).limit(1)) is not None


def _start_parent_if_ready(session: Session, done: Task) -> None:
    if done.parent_id is None:
        return
    session.flush()
    parent = session.get(Task, done.parent_id)
    if parent is None or parent.status == "done" or unfinished_subtasks(session, parent):
        return
    if parent.status != "in_progress":
        place_task(session, parent, "in_progress")
    start_task(session, parent)


def queue_triage(session: Session, task: Task) -> None:
    """In a manager-run backlog, the contact manager decides who takes a new unassigned card."""
    project = session.get(Project, task.project_id)
    manager = primary_manager(project) if project else None
    if project is None or not project.auto_manage or manager is None:
        return
    if task.assignee_id is not None or task.parent_id is not None:
        return
    session.add(Run(kind="triage", agent_id=manager.id, project_id=project.id, task_id=task.id))


def triaging(session: Session, task: Task) -> bool:
    return session.scalar(select(Run.id).where(Run.task_id == task.id, Run.kind == "triage",
                                               Run.status.in_(OPEN_RUN_STATUSES)).limit(1)) is not None


def schedule(session: Session, project_id: int) -> list[Task]:
    """Start backlog tasks whose assignees have room, highest priority first (manager-run backlogs only)."""
    project = session.get(Project, project_id)
    if project is None or not project.auto_manage or project.status in ("paused", "done", "archived"):
        return []
    session.flush()
    limit = max(get_settings().max_active_tasks_per_agent, 1)
    busy: dict[int, int] = dict(session.execute(
        select(Run.agent_id, func.count()).where(Run.kind == "task", Run.status.in_(("queued", "running")))
        .group_by(Run.agent_id)).all())
    backlog = sorted(session.scalars(select(Task).where(
        Task.project_id == project.id, Task.status == "backlog", Task.assignee_id.is_not(None))),
        key=lambda t: (PRIORITY_ORDER.get(t.priority, 1), t.rank, t.id))
    started = []
    for task in backlog:
        agent = session.get(Agent, task.assignee_id)
        if agent is None or not agent.active or busy.get(agent.id, 0) >= limit:
            continue
        if not ready(session, task) or unfinished_subtasks(session, task) or planning(session, task):
            continue
        place_task(session, task, "in_progress")
        if start_task(session, task) is not None:
            busy[agent.id] = busy.get(agent.id, 0) + 1
            started.append(task)
    return started
