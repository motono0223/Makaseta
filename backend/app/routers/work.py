from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import work
from ..config import get_settings
from ..db import get_session
from ..llm import month_spend
from ..models import Agent, Deliverable, Message, Project, Run, RunStep, Task, UsageRecord

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


class TaskWork(BaseModel):
    runs: list[RunOut]
    deliverables: list[DeliverableOut]
    question: MessageOut | None
    report: MessageOut | None


class TextIn(BaseModel):
    body: Body


class AgentMessageIn(BaseModel):
    body: Body
    answer_task_id: int | None = None


class InboxItem(BaseModel):
    kind: str  # question | review | failed
    task_id: int
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
    runs = list(session.scalars(select(Run).where(Run.task_id == task.id).order_by(Run.id.desc())))
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
    return TaskWork(runs=run_out, deliverables=deliverables, question=question, report=report)


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
    run = session.scalar(select(Run).where(Run.task_id == task.id).order_by(Run.id.desc()))
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


# ---- threads ----

@router.get("/agents/{agent_id}/thread")
def agent_thread(agent_id: int, session: SessionDep, limit: int = 100) -> list[MessageOut]:
    if session.get(Agent, agent_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "社員が見つかりません")
    rows = session.scalars(select(Message).where(Message.agent_id == agent_id).order_by(Message.id.desc())
                           .limit(min(limit, 500)))
    return list(reversed(list(rows)))


@router.post("/agents/{agent_id}/messages", status_code=status.HTTP_201_CREATED)
def message_agent(agent_id: int, body: AgentMessageIn, session: SessionDep, request: Request) -> MessageOut:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "社員が見つかりません")
    if not agent.active:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{agent.name}さんは退職しています")
    message = work.talk_to_agent(session, agent, body.body, body.answer_task_id)
    session.commit()
    _wake(request)
    return message


@router.get("/projects/{project_id}/thread")
def project_thread(project_id: int, session: SessionDep, limit: int = 200) -> list[MessageOut]:
    rows = session.scalars(select(Message).where(Message.project_id == project_id).order_by(Message.id.desc())
                           .limit(min(limit, 500)))
    return list(reversed(list(rows)))


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
        elif task.status == "review":
            review = work.run_awaiting_review(session, task)
            items.append(item("review", task, "成果物の確認をお願いします", review.ended_at if review and review.ended_at
                              else task.updated_at, task.assignee_id))
        elif task.status == "in_progress" and run is None:
            last = session.scalar(select(Run).where(Run.task_id == task.id).order_by(Run.id.desc()))
            if last is not None and last.status in ("failed", "interrupted"):
                items.append(item("failed", task, last.error, last.ended_at or task.updated_at, last.agent_id))
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
