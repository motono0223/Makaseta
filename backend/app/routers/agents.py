from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..catalog import AGENT_TEMPLATES, AVATAR_COLORS
from ..config import get_settings
from ..db import get_session
from ..llm import LLMError, check_budget, open_model, record_usage
from ..llm_profiles import load_profiles
from ..models import Agent, AgentNote, Message, Project, ProjectMember, ProjectRole, Skill, Task, UsageRecord
from ..schemas import AgentCreate, AgentOut, AgentTemplateOut, AgentUpdate, SkillOut

router = APIRouter(prefix="/api", tags=["agents"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/agent-templates")
def list_templates() -> list[AgentTemplateOut]:
    return [AgentTemplateOut(**t) for t in AGENT_TEMPLATES]


@router.get("/skills")
def list_skills(session: SessionDep) -> list[SkillOut]:
    return list(session.scalars(select(Skill).order_by(Skill.builtin.desc(), Skill.id)))


class NameRequest(BaseModel):
    theme: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    title: str = ""
    count: int = 6


class NameIdea(BaseModel):
    name: str
    note: str = ""


SUGGEST_NAMES = {
    "name": "suggest_names",
    "description": "社員の名前の候補を返す。",
    "input_schema": {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "名前（40文字以内）"},
                        "note": {"type": "string", "description": "由来やイメージを一言"},
                    },
                    "required": ["name"],
                },
            },
        },
        "required": ["names"],
    },
}


@router.post("/agents/suggest-names")
def suggest_names(body: NameRequest, session: SessionDep) -> list[NameIdea]:
    """Name ideas for a new agent from a theme such as a family or a story's characters."""
    taken = [a.name for a in session.scalars(select(Agent).where(Agent.active.is_(True)))]
    count = min(max(body.count, 1), 12)
    try:
        check_budget(session)
        model = open_model(get_settings().default_model_profile)
        response = model.create(
            system="あなたは仮想オフィスの社員（AIエージェント）に名前を付ける手伝いをします。"
                   "テーマに沿った、呼びやすい名前を考え、suggest_names で返します。",
            tools=[SUGGEST_NAMES],
            messages=[{"role": "user", "content": (
                f"テーマ: {body.theme}\n"
                f"役職: {body.title or '（未定）'}\n"
                f"すでにいる社員（重ならないように）: {'、'.join(taken) or 'なし'}\n"
                f"候補を{count}個考えてください。役職に合いそうな順に並べ、各候補に一言の由来を添えてください。"
            )}],
        )
        record_usage(session, model, response, agent_id=None, project_id=None, task_id=None, run_id=None)
        session.commit()
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    ideas: list[NameIdea] = []
    for block in response.content:
        if block.type == "tool_use" and block.name == "suggest_names":
            for item in (block.input or {}).get("names") or []:
                name = str(item.get("name", "")).strip()[:40]
                if name and name not in taken and all(i.name != name for i in ideas):
                    ideas.append(NameIdea(name=name, note=str(item.get("note", "")).strip()[:100]))
    if not ideas:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "名前の候補を作れませんでした。テーマを変えて試してください")
    return ideas[:count]


@router.get("/agents")
def list_agents(session: SessionDep, include_on_leave: bool = False) -> list[AgentOut]:
    query = select(Agent).order_by(Agent.active.desc(), Agent.id)
    if not include_on_leave:
        query = query.where(Agent.active.is_(True))
    return list(session.scalars(query))


@router.get("/agents/{agent_id}")
def get_agent(agent_id: int, session: SessionDep) -> AgentOut:
    return _get_or_404(session, agent_id)


@router.post("/agents", status_code=status.HTTP_201_CREATED)
def hire_agent(body: AgentCreate, session: SessionDep) -> AgentOut:
    _check_model_profile(body.model_profile)
    _check_unique_name(session, body.name)
    color = body.avatar_color or _next_color(session)
    agent = Agent(
        name=body.name,
        title=body.title,
        avatar_color=color,
        personality=body.personality,
        instructions=body.instructions,
        model_profile=body.model_profile,
        template_key=body.template_key,
        skills=_load_skills(session, body.skill_ids),
    )
    session.add(agent)
    session.commit()
    return agent


@router.patch("/agents/{agent_id}")
def update_agent(agent_id: int, body: AgentUpdate, session: SessionDep) -> AgentOut:
    agent = _get_or_404(session, agent_id)
    changes = body.model_dump(exclude_unset=True)
    if "model_profile" in changes:
        _check_model_profile(changes["model_profile"])
    if "name" in changes and agent.active:
        _check_unique_name(session, changes["name"], exclude_id=agent.id)
    if "skill_ids" in changes:
        agent.skills = _load_skills(session, changes.pop("skill_ids"))
    for field, value in changes.items():
        if value is not None:
            setattr(agent, field, value)
    session.commit()
    return agent


class CloneIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    copy_notes: bool = True


@router.post("/agents/{agent_id}/clone", status_code=status.HTTP_201_CREATED)
def clone_agent(agent_id: int, body: CloneIn, session: SessionDep) -> AgentOut:
    """Hire a new agent like an existing one: same role, persona, model and skills, optionally its 業務メモ too."""
    source = _get_or_404(session, agent_id)
    _check_unique_name(session, body.name)
    agent = Agent(name=body.name, title=source.title, avatar_color=_next_color(session),
                  personality=source.personality, instructions=source.instructions,
                  model_profile=source.model_profile, template_key=source.template_key, skills=list(source.skills))
    if body.copy_notes:
        agent.notes = [AgentNote(body=n.body, source=n.source, task_id=n.task_id) for n in source.notes]
    session.add(agent)
    session.commit()
    return agent


@router.post("/agents/{agent_id}/leave")
def start_leave(agent_id: int, session: SessionDep) -> AgentOut:
    agent = _get_or_404(session, agent_id)
    if agent.status == "working":
        raise HTTPException(status.HTTP_409_CONFLICT, "作業中の社員は休暇に入れません。作業が終わってから操作してください")
    sole = _projects_where_sole_manager(session, agent.id)
    if sole:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{agent.name}さんはプロジェクト「{'」「'.join(sole)}」の唯一のマネージャーです。"
            "休暇の間の窓口として、先に別のマネージャーをアサインしてください",
        )
    agent.active = False
    agent.leave_started_at = datetime.now(timezone.utc)
    agent.status = "idle"
    session.commit()
    return agent


@router.post("/agents/{agent_id}/return")
def end_leave(agent_id: int, session: SessionDep) -> AgentOut:
    agent = _get_or_404(session, agent_id)
    _check_unique_name(session, agent.name, exclude_id=agent.id)
    agent.active = True
    agent.leave_started_at = None
    session.commit()
    return agent


# ---- growth: 業務メモ and track record ----

NoteBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    source: str
    task_id: int | None
    task_title: str | None = None
    created_at: datetime
    updated_at: datetime


class NoteIn(BaseModel):
    body: NoteBody


class AgentStats(BaseModel):
    tasks_done: int
    tasks_open: int
    rejections: int
    first_pass_rate: float | None
    projects: int
    notes: int
    cost_usd: float


@router.get("/agents/{agent_id}/notes")
def list_notes(agent_id: int, session: SessionDep) -> list[NoteOut]:
    agent = _get_or_404(session, agent_id)
    titles = {t.id: t.title for t in session.scalars(select(Task).where(
        Task.id.in_([n.task_id for n in agent.notes if n.task_id])))}
    return [NoteOut.model_validate(n).model_copy(update={"task_title": titles.get(n.task_id)})
            for n in reversed(agent.notes)]


@router.post("/agents/{agent_id}/notes", status_code=status.HTTP_201_CREATED)
def add_note(agent_id: int, body: NoteIn, session: SessionDep) -> NoteOut:
    agent = _get_or_404(session, agent_id)
    note = AgentNote(agent_id=agent.id, body=body.body, source="manager")
    session.add(note)
    session.commit()
    return note


@router.patch("/notes/{note_id}")
def edit_note(note_id: int, body: NoteIn, session: SessionDep) -> NoteOut:
    note = _get_note(session, note_id)
    note.body = body.body
    note.source = "manager"
    session.commit()
    return note


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, session: SessionDep) -> None:
    session.delete(_get_note(session, note_id))
    session.commit()


@router.get("/agents/{agent_id}/stats")
def agent_stats(agent_id: int, session: SessionDep) -> AgentStats:
    agent = _get_or_404(session, agent_id)
    done_ids = session.scalars(select(Task.id).where(Task.assignee_id == agent.id, Task.status == "done")).all()
    open_count = session.scalar(select(func.count()).select_from(Task).where(
        Task.assignee_id == agent.id, Task.status != "done")) or 0
    rejected_tasks = set(session.scalars(select(Message.task_id).where(
        Message.agent_id == agent.id, Message.sender == "manager", Message.kind == "review",
        Message.body.contains("差し戻"), Message.task_id.is_not(None))).all())
    rejections = session.scalar(select(func.count()).select_from(Message).where(
        Message.agent_id == agent.id, Message.sender == "manager", Message.kind == "review",
        Message.body.contains("差し戻"), Message.task_id.is_not(None))) or 0
    first_pass = sum(1 for t in done_ids if t not in rejected_tasks)
    cost = session.scalar(select(func.coalesce(func.sum(UsageRecord.cost_usd), 0)).where(
        UsageRecord.agent_id == agent.id)) or 0
    projects = session.scalar(select(func.count()).select_from(ProjectMember).where(
        ProjectMember.agent_id == agent.id)) or 0
    return AgentStats(tasks_done=len(done_ids), tasks_open=open_count, rejections=rejections,
                      first_pass_rate=first_pass / len(done_ids) if done_ids else None, projects=projects,
                      notes=len(agent.notes), cost_usd=float(cost))


def _get_note(session: Session, note_id: int) -> AgentNote:
    note = session.get(AgentNote, note_id)
    if note is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "業務メモが見つかりません")
    return note


def _get_or_404(session: Session, agent_id: int) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "社員が見つかりません")
    return agent


def _check_model_profile(name: str) -> None:
    profiles = {p.name: p for p in load_profiles(get_settings())}
    profile = profiles.get(name)
    if profile is None or profile.kind != "chat":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"モデルプロファイル「{name}」は社員に使えません")


def _check_unique_name(session: Session, name: str, exclude_id: int | None = None) -> None:
    query = select(Agent.id).where(Agent.active.is_(True), func.lower(Agent.name) == name.lower())
    if exclude_id is not None:
        query = query.where(Agent.id != exclude_id)
    if session.scalar(query) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"「{name}」という名前の社員がすでにいます")


def _load_skills(session: Session, skill_ids: list[int]) -> list[Skill]:
    ids = list(dict.fromkeys(skill_ids))
    skills = list(session.scalars(select(Skill).where(Skill.id.in_(ids)).order_by(Skill.id))) if ids else []
    if len(skills) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "存在しないスキルが含まれています")
    return skills


def _next_color(session: Session) -> str:
    count = session.scalar(select(func.count()).select_from(Agent)) or 0
    return AVATAR_COLORS[count % len(AVATAR_COLORS)]


def _projects_where_sole_manager(session: Session, agent_id: int) -> list[str]:
    managed = session.scalars(
        select(Project)
        .join(ProjectMember)
        .join(ProjectRole)
        .where(ProjectMember.agent_id == agent_id, ProjectRole.is_manager.is_(True), Project.status != "archived")
    )
    return [p.name for p in managed if sum(1 for m in p.members if m.role.is_manager and m.agent.active) == 1]
