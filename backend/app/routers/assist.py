"""AI help for setting up work: draft a project and its team from a one-line idea."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import library
from ..catalog import AGENT_TEMPLATES
from ..config import get_settings
from ..db import get_session
from ..llm import LLMError, check_budget, open_model, record_usage
from ..models import Agent, Document, ProjectRole, Task

router = APIRouter(prefix="/api/assist", tags=["assist"])
SessionDep = Annotated[Session, Depends(get_session)]


class ProjectIdea(BaseModel):
    idea: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class MemberDraft(BaseModel):
    agent_id: int
    role_id: int
    is_primary: bool = False
    reason: str = ""


class NewMemberDraft(BaseModel):
    name: str
    title: str
    role_id: int
    template_key: str | None = None
    clone_of: int | None = None
    reason: str = ""


class RoomDraft(BaseModel):
    room: str
    access: str
    reason: str = ""


class ProjectDraft(BaseModel):
    name: str
    goal: str
    done_criteria: str
    members: list[MemberDraft]
    new_members: list[NewMemberDraft]
    rooms: list[RoomDraft]


DRAFT_PROJECT = {
    "name": "draft_project",
    "description": "プロジェクトの下書きとチーム編成を返す。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "プロジェクト名（短く）"},
            "goal": {"type": "string", "description": "目的（何を達成したいか、2〜3文）"},
            "done_criteria": {"type": "string", "description": "完了条件（確認できる形で、箇条書き可）"},
            "members": {
                "type": "array",
                "description": "今いる社員から選ぶメンバー",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "社員の名前"},
                        "role": {"type": "string", "description": "ロール名"},
                        "is_primary": {"type": "boolean", "description": "オフィス長の窓口にするマネージャーなら true"},
                        "reason": {"type": "string"},
                    },
                    "required": ["agent", "role"],
                },
            },
            "new_members": {
                "type": "array",
                "description": "足りない役割のために新しく雇う社員（今いる社員で足りるなら空）",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "新しい社員の名前の案"},
                        "role": {"type": "string", "description": "ロール名"},
                        "template": {"type": "string", "description": "役職テンプレートのキー（clone_of を使わない場合）"},
                        "clone_of": {"type": "string", "description": "複製元にする今いる社員の名前（同じ役割をもう1人ほしい場合）"},
                        "reason": {"type": "string"},
                    },
                    "required": ["name", "role"],
                },
            },
            "rooms": {
                "type": "array",
                "description": "リンクする資料室",
                "items": {
                    "type": "object",
                    "properties": {
                        "room": {"type": "string"},
                        "access": {"type": "string", "enum": ["read", "write"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["room", "access"],
                },
            },
        },
        "required": ["name", "goal", "done_criteria", "members", "new_members", "rooms"],
    },
}


@router.post("/project-draft")
def draft_project(body: ProjectIdea, session: SessionDep) -> ProjectDraft:
    agents = list(session.scalars(select(Agent).where(Agent.active.is_(True)).order_by(Agent.id)))
    roles = list(session.scalars(select(ProjectRole).order_by(ProjectRole.id)))
    rooms = library.list_room_names()
    context = _context(session, agents, roles, rooms)
    try:
        check_budget(session)
        model = open_model(get_settings().default_model_profile)
        response = model.create(
            system="あなたは仮想オフィスのオフィス長を補佐し、プロジェクトの立ち上げを手伝います。"
                   "やりたいことから、プロジェクト名・目的・完了条件を下書きし、今いる社員からチームを組みます。"
                   "マネージャーのロールを必ず1人入れ、そのうち1人を窓口（is_primary）にします。"
                   "今いる社員で足りない役割だけ new_members に入れます。新しい社員の名前は、今いる社員に合わせた人名にします。"
                   "資料室の一覧から、読ませる資料がありそうな資料室を rooms に入れ、成果物を置く資料室を1つ write にします。"
                   "draft_project で返します。",
            tools=[DRAFT_PROJECT],
            messages=[{"role": "user", "content": f"{context}\n\n## やりたいこと\n{body.idea}"}],
        )
        record_usage(session, model, response, agent_id=None, project_id=None, task_id=None, run_id=None)
        session.commit()
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    raw = next((b.input for b in response.content if b.type == "tool_use" and b.name == "draft_project"), None)
    if not raw:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "下書きを作れませんでした。やりたいことを具体的にして試してください")
    return _validate(raw, agents, roles, rooms)


def _context(session: Session, agents: list[Agent], roles: list[ProjectRole], rooms: list[str]) -> str:
    lines = ["## 今いる社員"]
    for a in agents:
        open_tasks = session.scalar(select(func.count()).select_from(Task).where(
            Task.assignee_id == a.id, Task.status != "done")) or 0
        skills = "、".join(s.name for s in a.skills) or "なし"
        lines.append(f"- {a.name}: 役職 {a.title or 'なし'} / スキル {skills} / 業務メモ {len(a.notes)}件 / 担当中 {open_tasks}件")
    if not agents:
        lines.append("（まだいません）")
    lines += ["", "## ロール", *[f"- {r.name}{'（マネージャー）' if r.is_manager else ''}: {r.description}" for r in roles]]
    lines += ["", "## 役職テンプレート（新しく雇う場合）",
              *[f"- {t['key']}: {t['title']}（{t['description']}）" for t in AGENT_TEMPLATES]]
    counts = dict(session.execute(select(Document.room, func.count()).group_by(Document.room)).all())
    lines += ["", "## 資料室", *[f"- {r}（文書 {counts.get(r, 0)}件）" for r in rooms]]
    if not rooms:
        lines.append("（まだありません）")
    return "\n".join(lines)


def _validate(raw: dict, agents: list[Agent], roles: list[ProjectRole], rooms: list[str]) -> ProjectDraft:
    """Keep only suggestions that point at real agents, roles, templates and rooms."""
    by_name = {a.name: a for a in agents}
    role_by_name = {r.name: r for r in roles}
    templates = {t["key"]: t for t in AGENT_TEMPLATES}
    default_role = next((r for r in roles if not r.is_manager), roles[0])

    members: list[MemberDraft] = []
    for m in raw.get("members") or []:
        agent, role = by_name.get(str(m.get("agent", "")).strip()), role_by_name.get(str(m.get("role", "")).strip())
        if agent and all(x.agent_id != agent.id for x in members):
            members.append(MemberDraft(agent_id=agent.id, role_id=(role or default_role).id,
                                       is_primary=bool(m.get("is_primary")), reason=str(m.get("reason", ""))[:200]))

    taken = set(by_name)
    new_members: list[NewMemberDraft] = []
    for n in raw.get("new_members") or []:
        name = str(n.get("name", "")).strip()[:40]
        role = role_by_name.get(str(n.get("role", "")).strip()) or default_role
        clone = by_name.get(str(n.get("clone_of") or "").strip())
        template = templates.get(str(n.get("template") or "").strip())
        if not name or name in taken or (clone is None and template is None):
            continue
        taken.add(name)
        new_members.append(NewMemberDraft(
            name=name, title=clone.title if clone else template["title"], role_id=role.id,
            template_key=None if clone else template["key"], clone_of=clone.id if clone else None,
            reason=str(n.get("reason", ""))[:200]))

    manager_ids = {r.id for r in roles if r.is_manager}
    managers = [m for m in members if m.role_id in manager_ids]
    if managers and not any(m.is_primary for m in managers):
        managers[0].is_primary = True
    for m in members:
        m.is_primary = m.is_primary and m.role_id in manager_ids

    links = []
    for r in raw.get("rooms") or []:
        room = str(r.get("room", "")).strip()
        if room in rooms and all(x.room != room for x in links):
            links.append(RoomDraft(room=room, access="write" if r.get("access") == "write" else "read",
                                   reason=str(r.get("reason", ""))[:200]))

    if links and not any(link.access == "write" for link in links):
        links[0].access = "write"  # somewhere to keep the deliverables

    def text(key: str) -> str:
        # Models sometimes double-escape line breaks inside tool input.
        return str(raw.get(key, "")).replace("\\n", "\n").strip()

    return ProjectDraft(name=text("name")[:80], goal=text("goal"),
                        done_criteria=text("done_criteria"), members=members,
                        new_members=new_members, rooms=links)
