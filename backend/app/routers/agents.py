from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..catalog import AGENT_TEMPLATES, AVATAR_COLORS
from ..config import get_settings
from ..db import get_session
from ..llm_profiles import load_profiles
from ..models import Agent, Skill
from ..schemas import AgentCreate, AgentOut, AgentTemplateOut, AgentUpdate, SkillOut

router = APIRouter(prefix="/api", tags=["agents"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/agent-templates")
def list_templates() -> list[AgentTemplateOut]:
    return [AgentTemplateOut(**t) for t in AGENT_TEMPLATES]


@router.get("/skills")
def list_skills(session: SessionDep) -> list[SkillOut]:
    return list(session.scalars(select(Skill).order_by(Skill.builtin.desc(), Skill.id)))


@router.get("/agents")
def list_agents(session: SessionDep, include_retired: bool = False) -> list[AgentOut]:
    query = select(Agent).order_by(Agent.active.desc(), Agent.id)
    if not include_retired:
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


@router.post("/agents/{agent_id}/retire")
def retire_agent(agent_id: int, session: SessionDep) -> AgentOut:
    agent = _get_or_404(session, agent_id)
    if agent.status == "working":
        raise HTTPException(status.HTTP_409_CONFLICT, "作業中の社員は退職させられません。作業が終わってから操作してください")
    agent.active = False
    agent.retired_at = datetime.now(timezone.utc)
    agent.status = "idle"
    session.commit()
    return agent


@router.post("/agents/{agent_id}/rehire")
def rehire_agent(agent_id: int, session: SessionDep) -> AgentOut:
    agent = _get_or_404(session, agent_id)
    _check_unique_name(session, agent.name, exclude_id=agent.id)
    agent.active = True
    agent.retired_at = None
    session.commit()
    return agent


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
    skills = list(session.scalars(select(Skill).where(Skill.id.in_(ids)))) if ids else []
    if len(skills) != len(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "存在しないスキルが含まれています")
    return skills


def _next_color(session: Session) -> str:
    count = session.scalar(select(func.count()).select_from(Agent)) or 0
    return AVATAR_COLORS[count % len(AVATAR_COLORS)]
