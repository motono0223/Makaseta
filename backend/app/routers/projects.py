from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import library, work
from ..db import get_session
from ..library import LibraryError
from ..models import Agent, Project, ProjectMember, ProjectRole, ProjectRoom, Task

router = APIRouter(prefix="/api", tags=["projects"])
SessionDep = Annotated[Session, Depends(get_session)]

ProjectStatus = Literal["planning", "active", "paused", "done", "archived"]
TaskStatus = Literal["backlog", "in_progress", "waiting", "review", "done"]
Priority = Literal["high", "normal", "low"]
Access = Literal["read", "write"]
ProjectName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]

# Statuses in which the assignee is (or is about to be) working on the task.
ACTIVE_TASK_STATUSES = {"in_progress", "waiting"}


# ---- schemas ----

class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str | None
    name: str
    description: str
    is_manager: bool


class AgentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str
    avatar_color: str
    status: str
    active: bool


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent: AgentBrief
    role: RoleOut
    is_primary: bool


class RoomLinkOut(BaseModel):
    room: str
    access: Access
    exists: bool


class ProjectOut(BaseModel):
    id: int
    name: str
    goal: str
    done_criteria: str
    due_date: date | None
    status: ProjectStatus
    require_plan_approval: bool
    members: list[MemberOut]
    rooms: list[RoomLinkOut]
    task_counts: dict[str, int]
    created_at: datetime
    updated_at: datetime


class MemberIn(BaseModel):
    agent_id: int
    role_id: int
    is_primary: bool = False


class RoomLinkIn(BaseModel):
    room: str
    access: Access = "read"


class ProjectCreate(BaseModel):
    name: ProjectName
    goal: str = Field(default="", max_length=4000)
    done_criteria: str = Field(default="", max_length=4000)
    due_date: date | None = None
    status: ProjectStatus = "active"
    require_plan_approval: bool = True
    members: list[MemberIn]
    rooms: list[RoomLinkIn] = []


class ProjectUpdate(BaseModel):
    name: ProjectName | None = None
    goal: str | None = Field(default=None, max_length=4000)
    done_criteria: str | None = Field(default=None, max_length=4000)
    due_date: date | None = None
    status: ProjectStatus | None = None
    require_plan_approval: bool | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    instructions: str
    expected_output: str
    status: TaskStatus
    priority: Priority
    due_date: date | None
    assignee_id: int | None
    reviewer_id: int | None
    requested_by_agent_id: int | None
    rank: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskCreate(BaseModel):
    title: TaskTitle
    instructions: str = Field(default="", max_length=20000)
    expected_output: str = Field(default="", max_length=4000)
    priority: Priority = "normal"
    due_date: date | None = None
    assignee_id: int | None = None
    reviewer_id: int | None = None


class TaskUpdate(BaseModel):
    title: TaskTitle | None = None
    instructions: str | None = Field(default=None, max_length=20000)
    expected_output: str | None = Field(default=None, max_length=4000)
    priority: Priority | None = None
    due_date: date | None = None
    assignee_id: int | None = None
    reviewer_id: int | None = None
    status: TaskStatus | None = None


class TaskMove(BaseModel):
    status: TaskStatus
    position: int = Field(ge=0)


class AssignmentOut(BaseModel):
    project_id: int
    project_name: str
    project_status: ProjectStatus
    role: RoleOut
    is_primary: bool
    tasks: list[TaskOut]


# ---- roles ----

@router.get("/project-roles")
def list_roles(session: SessionDep) -> list[RoleOut]:
    return list(session.scalars(select(ProjectRole).order_by(ProjectRole.is_manager.desc(), ProjectRole.id)))


# ---- projects ----

@router.get("/projects")
def list_projects(session: SessionDep, include_archived: bool = False) -> list[ProjectOut]:
    query = select(Project).order_by(Project.updated_at.desc())
    if not include_archived:
        query = query.where(Project.status != "archived")
    projects = list(session.scalars(query))
    counts = _task_counts(session, [p.id for p in projects])
    return [_project_out(p, counts.get(p.id, {})) for p in projects]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, session: SessionDep) -> ProjectOut:
    project = Project(
        name=body.name,
        goal=body.goal,
        done_criteria=body.done_criteria,
        due_date=body.due_date,
        status=body.status,
        require_plan_approval=body.require_plan_approval,
    )
    session.add(project)
    _set_members(session, project, body.members)
    _set_rooms(project, body.rooms)
    session.commit()
    return _project_out(project, {})


@router.get("/projects/{project_id}")
def get_project(project_id: int, session: SessionDep) -> ProjectOut:
    project = _get_project(session, project_id)
    return _project_out(project, _task_counts(session, [project.id]).get(project.id, {}))


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate, session: SessionDep) -> ProjectOut:
    project = _get_project(session, project_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        if value is None and field != "due_date":
            continue
        setattr(project, field, value)
    session.commit()
    return get_project(project_id, session)


@router.put("/projects/{project_id}/members")
def replace_members(project_id: int, members: list[MemberIn], session: SessionDep) -> ProjectOut:
    project = _get_project(session, project_id)
    _set_members(session, project, members)
    session.commit()
    return get_project(project_id, session)


@router.put("/projects/{project_id}/rooms")
def replace_rooms(project_id: int, rooms: list[RoomLinkIn], session: SessionDep) -> ProjectOut:
    project = _get_project(session, project_id)
    _set_rooms(project, rooms)
    session.commit()
    return get_project(project_id, session)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, session: SessionDep) -> None:
    project = _get_project(session, project_id)
    if project.status != "archived":
        raise HTTPException(status.HTTP_409_CONFLICT, "削除できるのはアーカイブ済みのプロジェクトだけです")
    session.delete(project)
    session.commit()


# ---- tasks ----

@router.get("/projects/{project_id}/tasks")
def list_tasks(project_id: int, session: SessionDep) -> list[TaskOut]:
    _get_project(session, project_id)
    return list(session.scalars(select(Task).where(Task.project_id == project_id).order_by(Task.status, Task.rank,
                                                                                           Task.id)))


@router.post("/projects/{project_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_task(project_id: int, body: TaskCreate, session: SessionDep) -> TaskOut:
    project = _get_project(session, project_id)
    _check_member(project, body.assignee_id, "担当者")
    _check_member(project, body.reviewer_id, "レビュー担当")
    task = Task(project_id=project.id, rank=_next_rank(session, project.id, "backlog"), **body.model_dump())
    session.add(task)
    session.commit()
    return task


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate, session: SessionDep) -> TaskOut:
    task = _get_task(session, task_id)
    project = _get_project(session, task.project_id)
    changes = body.model_dump(exclude_unset=True)
    if "assignee_id" in changes:
        _check_member(project, changes["assignee_id"], "担当者")
    if "reviewer_id" in changes:
        _check_member(project, changes["reviewer_id"], "レビュー担当")
    new_status = changes.pop("status", None)
    if changes.get("assignee_id", task.assignee_id) != task.assignee_id and work.open_run(session, task):
        raise HTTPException(status.HTTP_409_CONFLICT, "作業中のタスクは担当者を変えられません。先にバックログに戻してください")
    for field, value in changes.items():
        if value is None and field in {"title", "instructions", "expected_output", "priority"}:
            continue
        setattr(task, field, value)
    old_status = task.status
    if new_status and new_status != old_status:
        work.place_task(session, task, new_status)
    _check_assignable(task)
    work.on_status_change(session, task, old_status, task.status)
    session.commit()
    return task


@router.post("/tasks/{task_id}/move")
def move_task(task_id: int, body: TaskMove, session: SessionDep) -> TaskOut:
    task = _get_task(session, task_id)
    old_status = task.status
    work.place_task(session, task, body.status, position=body.position)
    _check_assignable(task)
    work.on_status_change(session, task, old_status, task.status)
    session.commit()
    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, session: SessionDep) -> None:
    task = _get_task(session, task_id)
    if task.status in ACTIVE_TASK_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "作業中のタスクは削除できません。先にバックログに戻してください")
    session.delete(task)
    session.commit()


@router.get("/agents/{agent_id}/assignments")
def agent_assignments(agent_id: int, session: SessionDep) -> list[AssignmentOut]:
    memberships = session.scalars(
        select(ProjectMember).join(Project).where(ProjectMember.agent_id == agent_id)
        .order_by(Project.updated_at.desc())
    )
    result = []
    for m in memberships:
        tasks = session.scalars(
            select(Task).where(Task.project_id == m.project_id, Task.assignee_id == agent_id)
            .order_by(Task.status, Task.rank)
        )
        result.append(AssignmentOut(project_id=m.project_id, project_name=m.project.name,
                                    project_status=m.project.status, role=RoleOut.model_validate(m.role),
                                    is_primary=m.is_primary, tasks=[TaskOut.model_validate(t) for t in tasks]))
    return result


# ---- helpers ----

def _get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "プロジェクトが見つかりません")
    return project


def _get_task(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "タスクが見つかりません")
    return task


def _project_out(project: Project, counts: dict[str, int]) -> ProjectOut:
    existing_rooms = set(library.list_room_names())
    return ProjectOut(
        id=project.id,
        name=project.name,
        goal=project.goal,
        done_criteria=project.done_criteria,
        due_date=project.due_date,
        status=project.status,
        require_plan_approval=project.require_plan_approval,
        members=[MemberOut.model_validate(m) for m in project.members],
        rooms=[RoomLinkOut(room=r.room, access=r.access, exists=r.room in existing_rooms) for r in project.rooms],
        task_counts=counts,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _task_counts(session: Session, project_ids: list[int]) -> dict[int, dict[str, int]]:
    counts: dict[int, dict[str, int]] = {}
    if not project_ids:
        return counts
    rows = session.execute(
        select(Task.project_id, Task.status, func.count()).where(Task.project_id.in_(project_ids))
        .group_by(Task.project_id, Task.status)
    )
    for project_id, task_status, count in rows:
        counts.setdefault(project_id, {})[task_status] = count
    return counts


def _set_members(session: Session, project: Project, members: list[MemberIn]) -> None:
    agent_ids = [m.agent_id for m in members]
    if len(set(agent_ids)) != len(agent_ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "同じ社員が2回指定されています")
    roles = {r.id: r for r in session.scalars(select(ProjectRole))}
    agents = {a.id: a for a in session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))} if agent_ids else {}
    current = {m.agent_id for m in project.members}

    for m in members:
        agent = agents.get(m.agent_id)
        if agent is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"社員（ID {m.agent_id}）が見つかりません")
        if not agent.active and m.agent_id not in current:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{agent.name}さんは退職しています")
        if m.role_id not in roles:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"ロール（ID {m.role_id}）が見つかりません")

    managers = [m for m in members if roles[m.role_id].is_manager]
    if not managers:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "マネージャーを1人以上アサインしてください")
    if any(m.is_primary and not roles[m.role_id].is_manager for m in members):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "窓口（主担当）にできるのはマネージャーだけです")
    primaries = [m for m in managers if m.is_primary]
    if len(primaries) > 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "窓口（主担当）は1人だけにしてください")
    primary_id = primaries[0].agent_id if primaries else managers[0].agent_id

    removed = current - set(agent_ids)
    if removed and project.id is not None:
        busy = session.scalars(
            select(Task).where(Task.project_id == project.id, Task.assignee_id.in_(removed),
                               Task.status.in_(ACTIVE_TASK_STATUSES))
        ).first()
        if busy is not None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"作業中のタスク「{busy.title}」の担当者はメンバーから外せません")
        for task in session.scalars(select(Task).where(Task.project_id == project.id)):
            if task.assignee_id in removed:
                task.assignee_id = None
            if task.reviewer_id in removed:
                task.reviewer_id = None

    project.members = [
        ProjectMember(agent=agents[m.agent_id], role=roles[m.role_id], is_primary=m.agent_id == primary_id)
        for m in members
    ]


def _set_rooms(project: Project, rooms: list[RoomLinkIn]) -> None:
    names = [r.room for r in rooms]
    if len(set(names)) != len(names):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "同じ資料室が2回指定されています")
    for name in names:
        try:
            library.room_dir(name)
        except LibraryError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    project.rooms = [ProjectRoom(room=r.room, access=r.access) for r in rooms]


def _check_member(project: Project, agent_id: int | None, what: str) -> None:
    if agent_id is None:
        return
    if agent_id not in {m.agent_id for m in project.members}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{what}はプロジェクトのメンバーから選んでください")


def _check_assignable(task: Task) -> None:
    if task.status in ACTIVE_TASK_STATUSES | {"review"} and task.assignee_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "担当者が決まっていないタスクは進められません")


def _next_rank(session: Session, project_id: int, task_status: str) -> int:
    top = session.scalar(select(func.max(Task.rank)).where(Task.project_id == project_id, Task.status == task_status))
    return (top or 0) + 1
