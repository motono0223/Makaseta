from datetime import datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import library, work
from ..config import get_settings
from ..db import get_session
from ..library import LibraryError
from ..llm import month_spend
from ..models import Agent, Deliverable, Message, Plan, Project, Run, RunStep, Task, UsageRecord

router = APIRouter(prefix="/api", tags=["work"])
SessionDep = Annotated[Session, Depends(get_session)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


# ---- schemas ----

class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    name: str
    content: str
    created_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    agent_id: int
    status: str
    steps: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    error: str
    awaiting_review: bool = False
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    log: list[StepOut] = []


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int | None
    room: str
    path: str
    content: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    # Approving would replace a file that already exists in the room (the old one is kept as a version).
    overwrites: bool = False
    # Binary deliverable (e.g. .pptx): download it instead of reading content.
    file_size: int | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: int | None
    project_id: int | None
    task_id: int | None
    run_id: int | None
    sender: str
    kind: str
    body: str
    created_at: datetime
    # For questions: still waiting for the office head's answer.
    awaiting_answer: bool = False


class TaskWork(BaseModel):
    runs: list[RunOut]
    deliverables: list[DeliverableOut]
    question: MessageOut | None
    report: MessageOut | None
    # The reviewer agent's latest verdict, shown to the office head with the report.
    peer_review: MessageOut | None = None


class TextIn(BaseModel):
    body: Body


class AgentMessageIn(BaseModel):
    body: Body
    answer_run_id: int | None = None


class PlanItemOut(BaseModel):
    title: str
    instructions: str
    expected_output: str
    assignee_id: int | None
    assignee_name: str | None
    reviewer_id: int | None = None
    reviewer_name: str | None = None
    priority: str
    depends_on: list[int]


class PlanOut(BaseModel):
    id: int
    project_id: int
    parent_task_id: int | None = None
    agent_id: int | None
    request: str
    status: str
    summary: str
    items: list[PlanItemOut]
    run_status: str | None
    run_error: str
    task_ids: list[int]
    created_at: datetime
    decided_at: datetime | None


class InboxItem(BaseModel):
    kind: str  # question | review | failed | plan
    task_id: int | None
    plan_id: int | None = None
    task_title: str
    project_id: int
    project_name: str
    agent_id: int | None
    agent_name: str | None
    body: str
    created_at: datetime


class UsageSummary(BaseModel):
    month_spend_usd: Decimal
    monthly_budget_usd: float
    by_agent: list[dict]
    by_project: list[dict]


# ---- task work ----

@router.get("/tasks/{task_id}/work")
def task_work(task_id: int, session: SessionDep) -> TaskWork:
    task = _task(session, task_id)
    runs = list(session.scalars(select(Run).where(Run.task_id == task.id, Run.kind.in_(("task", "review")))
                                .order_by(Run.id.desc())))
    steps: dict[int, list[RunStep]] = {}
    if runs:
        for step in session.scalars(select(RunStep).where(RunStep.run_id.in_([r.id for r in runs]))
                                    .order_by(RunStep.id)):
            steps.setdefault(step.run_id, []).append(step)
    review = work.run_awaiting_review(session, task)
    run_out = [RunOut.model_validate(r).model_copy(update={
        "log": [StepOut.model_validate(s) for s in steps.get(r.id, [])],
        "awaiting_review": review is not None and r.id == review.id,
    }) for r in runs]
    deliverables = list(session.scalars(select(Deliverable).where(Deliverable.task_id == task.id,
                                                                  Deliverable.status != "superseded")
                                        .order_by(Deliverable.id.desc())))
    open_run = work.open_run(session, task)
    question = None
    if open_run is not None and open_run.status == "waiting":
        question = session.scalar(select(Message).where(Message.run_id == open_run.id, Message.kind == "question")
                                  .order_by(Message.id.desc()))
    report = None
    if review is not None:
        report = session.scalar(select(Message).where(Message.run_id == review.id, Message.kind == "report",
                                                      Message.sender == "agent").order_by(Message.id.desc()))
    peer_review = session.scalar(select(Message).where(Message.task_id == task.id, Message.sender == "agent",
                                                       Message.kind == "review").order_by(Message.id.desc()))
    return TaskWork(runs=run_out, deliverables=[_deliverable_out(d) for d in deliverables], question=question,
                    report=report, peer_review=peer_review)


@router.post("/tasks/{task_id}/answer")
def answer(task_id: int, body: TextIn, session: SessionDep, request: Request) -> MessageOut:
    message = work.answer_question(session, _task(session, task_id), body.body)
    session.commit()
    _wake(request)
    return message


@router.post("/tasks/{task_id}/approve")
def approve(task_id: int, session: SessionDep) -> list[DeliverableOut]:
    task = _task(session, task_id)
    if task.status != "review":
        raise HTTPException(status.HTTP_409_CONFLICT, "レビュー待ちのタスクだけ承認できます")
    drafts = work.approve(session, task)
    session.commit()
    return drafts


@router.post("/tasks/{task_id}/reject")
def reject(task_id: int, body: TextIn, session: SessionDep, request: Request) -> RunOut:
    run = work.reject(session, _task(session, task_id), body.body)
    session.commit()
    _wake(request)
    return run


@router.post("/tasks/{task_id}/retry")
def retry(task_id: int, session: SessionDep, request: Request) -> RunOut:
    """Run a failed or interrupted run again from where it stopped."""
    task = _task(session, task_id)
    if work.open_run(session, task) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "このタスクはすでに作業中です")
    run = session.scalar(select(Run).where(Run.task_id == task.id, Run.kind == "task").order_by(Run.id.desc()))
    if run is None or run.status not in ("failed", "interrupted", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "再実行できる作業がありません")
    if task.assignee_id != run.agent_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "担当者が変わったため再実行できません。作業中に移して新しく始めてください")
    run.status, run.error, run.ended_at = "queued", "", None
    if task.status != "in_progress":
        work.place_task(session, task, "in_progress")
    agent = session.get(Agent, run.agent_id)
    if agent is not None and agent.status == "error":
        agent.status = "idle"
    session.commit()
    _wake(request)
    return run


@router.post("/tasks/{task_id}/cancel")
def cancel(task_id: int, session: SessionDep) -> dict[str, str]:
    task = _task(session, task_id)
    if work.open_run(session, task) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "止める作業がありません")
    work.cancel_task(session, task, "オフィス長が止めました")
    work.place_task(session, task, "backlog")
    session.commit()
    return {"status": "cancelled"}


@router.get("/deliverables/{deliverable_id}/download")
def download_deliverable(deliverable_id: int, session: SessionDep) -> FileResponse:
    d = session.get(Deliverable, deliverable_id)
    if d is None or not d.file_path or not Path(d.file_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ファイルが見つかりません")
    return FileResponse(d.file_path, filename=PurePosixPath(d.path).name)


# ---- threads ----

@router.get("/agents/{agent_id}/thread")
def agent_thread(agent_id: int, session: SessionDep, limit: int = 100) -> list[MessageOut]:
    if session.get(Agent, agent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "社員が見つかりません")
    rows = session.scalars(select(Message).where(Message.agent_id == agent_id).order_by(Message.id.desc())
                           .limit(min(limit, 500)))
    return _with_open_questions(session, list(reversed(list(rows))))


@router.post("/agents/{agent_id}/messages", status_code=status.HTTP_201_CREATED)
def message_agent(agent_id: int, body: AgentMessageIn, session: SessionDep, request: Request) -> MessageOut:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "社員が見つかりません")
    if not agent.active:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{agent.name}さんは休暇中です")
    message = work.talk_to_agent(session, agent, body.body, body.answer_run_id)
    session.commit()
    _wake(request)
    return message


@router.get("/projects/{project_id}/thread")
def project_thread(project_id: int, session: SessionDep, limit: int = 200) -> list[MessageOut]:
    rows = session.scalars(select(Message).where(Message.project_id == project_id).order_by(Message.id.desc())
                           .limit(min(limit, 500)))
    return _with_open_questions(session, list(reversed(list(rows))))


@router.post("/runs/{run_id}/answer")
def answer_run(run_id: int, body: TextIn, session: SessionDep, request: Request) -> MessageOut:
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "質問が見つかりません")
    message = work.answer_run(session, run, body.body)
    session.commit()
    _wake(request)
    return message


# ---- manager plans ----

@router.post("/projects/{project_id}/requests", status_code=status.HTTP_201_CREATED)
def request_plan(project_id: int, body: TextIn, session: SessionDep, request: Request) -> PlanOut:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "プロジェクトが見つかりません")
    plan = work.request_plan(session, project, body.body)
    session.commit()
    _wake(request)
    return _plan_out(session, plan)


@router.get("/projects/{project_id}/plans")
def list_plans(project_id: int, session: SessionDep) -> list[PlanOut]:
    plans = session.scalars(select(Plan).where(Plan.project_id == project_id).order_by(Plan.id.desc()))
    return [_plan_out(session, p) for p in plans]


@router.post("/plans/{plan_id}/approve")
def approve_plan(plan_id: int, session: SessionDep, request: Request) -> PlanOut:
    plan = _plan(session, plan_id)
    work.approve_plan(session, plan)
    session.commit()
    _wake(request)
    return _plan_out(session, plan)


@router.post("/plans/{plan_id}/reject")
def reject_plan(plan_id: int, body: TextIn, session: SessionDep, request: Request) -> PlanOut:
    plan = _plan(session, plan_id)
    work.reject_plan(session, plan, body.body)
    session.commit()
    _wake(request)
    return _plan_out(session, plan)


@router.post("/plans/{plan_id}/cancel")
def cancel_plan(plan_id: int, session: SessionDep) -> PlanOut:
    plan = _plan(session, plan_id)
    work.cancel_plan(session, plan)
    session.commit()
    return _plan_out(session, plan)


@router.post("/plans/{plan_id}/retry")
def retry_plan(plan_id: int, session: SessionDep, request: Request) -> PlanOut:
    plan = _plan(session, plan_id)
    run = session.scalar(select(Run).where(Run.plan_id == plan.id).order_by(Run.id.desc()))
    if plan.status != "drafting" or run is None or run.status not in ("failed", "interrupted"):
        raise HTTPException(status.HTTP_409_CONFLICT, "再実行できる計画づくりがありません")
    run.status, run.error, run.ended_at = "queued", "", None
    session.commit()
    _wake(request)
    return _plan_out(session, plan)


# ---- inbox and usage ----

@router.get("/inbox")
def inbox(session: SessionDep) -> list[InboxItem]:
    items: list[InboxItem] = []
    agents = {a.id: a.name for a in session.scalars(select(Agent))}
    projects = {p.id: p.name for p in session.scalars(select(Project))}

    def item(kind: str, task: Task, body: str, at: datetime, agent_id: int | None) -> InboxItem:
        return InboxItem(kind=kind, task_id=task.id, task_title=task.title, project_id=task.project_id,
                         project_name=projects.get(task.project_id, ""), agent_id=agent_id,
                         agent_name=agents.get(agent_id) if agent_id else None, body=body, created_at=at)

    for task in session.scalars(select(Task).where(Task.status.in_(("waiting", "review", "in_progress")))):
        run = work.open_run(session, task)
        if task.status == "waiting" and run is not None and run.status == "waiting":
            q = session.scalar(select(Message).where(Message.run_id == run.id, Message.kind == "question")
                               .order_by(Message.id.desc()))
            items.append(item("question", task, q.body if q else "", q.created_at if q else task.updated_at,
                              run.agent_id))
        elif task.status == "review" and task.review_stage != "peer":
            review = work.run_awaiting_review(session, task)
            items.append(item("review", task, "成果物の確認をお願いします", review.ended_at if review and review.ended_at
                              else task.updated_at, task.assignee_id))
        elif task.status == "in_progress" and run is None:
            last = session.scalar(select(Run).where(Run.task_id == task.id, Run.kind == "task")
                                  .order_by(Run.id.desc()))
            if last is not None and last.status in ("failed", "interrupted"):
                items.append(item("failed", task, last.error, last.ended_at or task.updated_at, last.agent_id))
    for plan in session.scalars(select(Plan).where(Plan.status.in_(("drafting", "proposed")))):
        run = session.scalar(select(Run).where(Run.plan_id == plan.id).order_by(Run.id.desc()))
        base = dict(task_id=None, plan_id=plan.id, task_title=f"依頼: {work.short_title(plan.request)}",
                    project_id=plan.project_id, project_name=projects.get(plan.project_id, ""),
                    agent_id=plan.agent_id, agent_name=agents.get(plan.agent_id) if plan.agent_id else None)
        if plan.status == "proposed":
            items.append(InboxItem(kind="plan", body=plan.summary or "計画の確認をお願いします",
                                   created_at=run.ended_at if run and run.ended_at else plan.created_at, **base))
        elif run is not None and run.status == "waiting":
            q = session.scalar(select(Message).where(Message.run_id == run.id, Message.kind == "question")
                               .order_by(Message.id.desc()))
            items.append(InboxItem(kind="question", body=q.body if q else "",
                                   created_at=q.created_at if q else plan.created_at, **base))
        elif run is not None and run.status in ("failed", "interrupted"):
            items.append(InboxItem(kind="failed", body=run.error, created_at=run.ended_at or plan.created_at,
                                   **base))
    return sorted(items, key=lambda i: i.created_at, reverse=True)


@router.get("/usage/summary")
def usage_summary(session: SessionDep) -> UsageSummary:
    start = work.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def grouped(column, names: dict[int, str]) -> list[dict]:
        rows = session.execute(select(column, func.sum(UsageRecord.cost_usd), func.sum(UsageRecord.input_tokens),
                                      func.sum(UsageRecord.output_tokens))
                               .where(UsageRecord.created_at >= start).group_by(column)
                               .order_by(func.sum(UsageRecord.cost_usd).desc()))
        return [{"id": key, "name": names.get(key, "（なし）"), "cost_usd": float(cost or 0),
                 "input_tokens": int(tin or 0), "output_tokens": int(tout or 0)} for key, cost, tin, tout in rows]

    agents = {a.id: a.name for a in session.scalars(select(Agent))}
    projects = {p.id: p.name for p in session.scalars(select(Project))}
    return UsageSummary(month_spend_usd=month_spend(session), monthly_budget_usd=get_settings().monthly_budget_usd,
                        by_agent=grouped(UsageRecord.agent_id, agents),
                        by_project=grouped(UsageRecord.project_id, projects))


# ---- helpers ----

def _task(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "タスクが見つかりません")
    return task


def _wake(request: Request) -> None:
    request.app.state.worker.wake()


def _deliverable_out(d: Deliverable) -> DeliverableOut:
    out = DeliverableOut.model_validate(d)
    if d.file_path and Path(d.file_path).is_file():
        out.file_size = Path(d.file_path).stat().st_size
    if d.status == "draft":
        try:
            out.overwrites = library.resolve(d.room, d.path).is_file()
        except LibraryError:
            pass
    return out


def _plan(session: Session, plan_id: int) -> Plan:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "計画が見つかりません")
    return plan


def _plan_out(session: Session, plan: Plan) -> PlanOut:
    names = {a.id: a.name for a in session.scalars(select(Agent))}
    run = session.scalar(select(Run).where(Run.plan_id == plan.id).order_by(Run.id.desc()))
    task_ids = session.scalars(select(Task.id).where(Task.plan_id == plan.id).order_by(Task.id)).all()
    return PlanOut(
        id=plan.id, project_id=plan.project_id, parent_task_id=plan.parent_task_id, agent_id=plan.agent_id,
        request=plan.request, status=plan.status,
        summary=plan.summary,
        items=[PlanItemOut(**item, assignee_name=names.get(item.get("assignee_id")),
                           reviewer_name=names.get(item.get("reviewer_id"))) for item in plan.items],
        run_status=run.status if run else None, run_error=run.error if run else "", task_ids=list(task_ids),
        created_at=plan.created_at, decided_at=plan.decided_at,
    )


def _with_open_questions(session: Session, messages: list[Message]) -> list[MessageOut]:
    run_ids = {m.run_id for m in messages if m.kind == "question" and m.run_id}
    waiting = set(session.scalars(select(Run.id).where(Run.id.in_(run_ids), Run.status == "waiting"))) if run_ids else set()
    latest: dict[int, int] = {}
    for m in messages:
        if m.kind == "question" and m.run_id in waiting:
            latest[m.run_id] = m.id
    return [MessageOut.model_validate(m).model_copy(update={"awaiting_answer": latest.get(m.run_id) == m.id})
            for m in messages]
