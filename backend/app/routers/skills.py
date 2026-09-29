from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import skill_packages as packages
from ..db import get_session
from ..models import Agent, Skill, agent_skills
from ..skill_packages import SkillPackageError

router = APIRouter(prefix="/api/skills", tags=["skills"])
SessionDep = Annotated[Session, Depends(get_session)]


class SkillDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str | None
    name: str
    description: str
    instructions: str
    tools: list[str]
    builtin: bool
    source: str
    folder: str | None
    source_url: str
    enabled: bool
    agents: list[str] = []
    files: list[dict] = []
    body: str = ""
    license: str = ""
    updated_at: datetime


class ImportIn(BaseModel):
    url: str


class Preview(BaseModel):
    stage_id: str
    name: str
    folder: str
    description: str
    license: str
    body: str
    files: list[dict]
    exists: bool


class InstallIn(BaseModel):
    stage_id: str
    replace: bool = False


def _fail(exc: SkillPackageError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.post("/rescan")
def rescan(session: SessionDep) -> list[SkillDetail]:
    packages.scan(session)
    return list_details(session)


@router.get("/details")
def list_details(session: SessionDep) -> list[SkillDetail]:
    names = {}
    for skill_id, agent_name in session.execute(
            select(agent_skills.c.skill_id, Agent.name).join(Agent, Agent.id == agent_skills.c.agent_id)
            .where(Agent.active.is_(True))):
        names.setdefault(skill_id, []).append(agent_name)
    skills = session.scalars(select(Skill).order_by(Skill.source, Skill.id))
    return [SkillDetail.model_validate(s).model_copy(update={"agents": names.get(s.id, [])}) for s in skills]


@router.get("/{skill_id}/detail")
def skill_detail(skill_id: int, session: SessionDep) -> SkillDetail:
    skill = session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "スキルが見つかりません")
    detail = SkillDetail.model_validate(skill)
    if skill.source == "package" and skill.enabled:
        try:
            base = packages.package_dir(skill.folder)
            meta = packages.parse_skill_md(base / "SKILL.md")
            detail = detail.model_copy(update={"files": packages.list_files(base), "body": meta.body,
                                               "license": meta.license})
        except SkillPackageError:
            pass
    return detail


@router.post("/import/preview")
def preview_import(body: ImportIn) -> Preview:
    try:
        stage_id = packages.stage_from_github(body.url)
        base = packages.staged_dir(stage_id)
        meta = packages.parse_skill_md(base / "SKILL.md")
        folder = packages.folder_name(meta.name)
    except SkillPackageError as exc:
        raise _fail(exc) from exc
    return Preview(stage_id=stage_id, name=meta.name, folder=folder, description=meta.description,
                   license=meta.license, body=meta.body, files=packages.list_files(base),
                   exists=(packages.root() / folder).exists())


@router.post("/import/install", status_code=status.HTTP_201_CREATED)
def install_import(body: InstallIn, session: SessionDep) -> SkillDetail:
    try:
        skill = packages.install(session, body.stage_id, body.replace)
    except SkillPackageError as exc:
        raise _fail(exc) from exc
    return SkillDetail.model_validate(skill)


@router.delete("/import/{stage_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_import(stage_id: str) -> None:
    try:
        packages.discard(stage_id)
    except SkillPackageError as exc:
        raise _fail(exc) from exc


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, session: SessionDep) -> None:
    skill = session.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "スキルが見つかりません")
    try:
        packages.remove(session, skill)
    except SkillPackageError as exc:
        raise _fail(exc) from exc
