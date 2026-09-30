"""Tools an agent can call while working on a task.

Every tool checks the project's 資料室 links itself: what the model asks for never widens access.
Document text goes back wrapped in <document> tags and is treated as data, not instructions.
"""

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from . import library
from . import sandbox
from . import skill_packages as packages
from .config import get_settings
from .library import LibraryError
from .sandbox import SandboxError
from .skill_packages import SkillPackageError
from .llm_profiles import load_profiles
from .models import Agent, Deliverable, Document, LibraryRoom, Project, ProjectMember, Task

READ_CHUNK = 20_000
SEARCH_LIMIT = 10
DELIVERABLE_SUFFIXES = {".md", ".txt", ".csv"}

# Tools every agent has, regardless of skills, per kind of work.
ALWAYS = {
    "task": ["ask_colleague", "ask_manager", "finish"],
    "plan": ["list_members", "ask_colleague", "ask_manager", "propose_plan"],
    # A reviewer can always read what it is reviewing, whatever its skills.
    "review": ["list_documents", "read_document", "read_deliverables", "approve_work", "request_changes"],
}
# Skill tools that make sense while planning (reading only; deliverables come from the tasks).
PLAN_SKILL_TOOLS = {"search_documents", "list_documents", "read_document", "read_skill", "read_skill_file",
                    "web_search", "web_fetch"}
# Tools that run on Anthropic's side (Claude API only; Bedrock does not offer them).
SERVER_TOOLS = {"web_search", "web_fetch"}
WEB_USES_PER_CALL = 5
MAX_WORKSPACE_WRITE = 1_000_000
MAX_SUBMIT_BYTES = 100 * 1024 * 1024

DEFINITIONS = {
    "search_documents": {
        "name": "search_documents",
        "description": "リンクされた資料室の文書を全文検索する。スペース区切りの語はすべて含む文書が返る。"
                       "結果は文書名と該当箇所の抜粋。中身は read_document で読む。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "検索語（日本語可、スペース区切りで複数語）"},
                "room": {"type": "string", "description": "資料室名で絞り込む場合に指定"},
            },
            "required": ["query"],
        },
    },
    "list_documents": {
        "name": "list_documents",
        "description": "リンクされた資料室のフォルダの中身（文書とサブフォルダ）を一覧する。",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {"type": "string", "description": "資料室名"},
                "folder": {"type": "string", "description": "資料室内のフォルダのパス。省略時は最上位"},
            },
            "required": ["room"],
        },
    },
    "read_document": {
        "name": "read_document",
        "description": f"資料室の文書のテキストを読む。1回に最大{READ_CHUNK}文字。続きは offset を指定して読む。",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "path": {"type": "string", "description": "資料室内のパス（例: 人事/経費精算.pdf）"},
                "offset": {"type": "integer", "description": "読み始める文字位置（既定 0）"},
            },
            "required": ["room", "path"],
        },
    },
    "submit_deliverable": {
        "name": "submit_deliverable",
        "description": "成果物（Markdown・テキスト・CSV）を提出する。読み書きできる資料室にだけ提出できる。"
                       "オフィス長が承認すると資料室に保存される。同じパスに再提出すると置き換わる。",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {"type": "string", "description": "保存先の資料室名"},
                "path": {"type": "string", "description": "保存するパス（例: 報告/出張規程_要点.md）"},
                "content": {"type": "string", "description": "成果物の本文"},
            },
            "required": ["room", "path", "content"],
        },
    },
    "ask_manager": {
        "name": "ask_manager",
        "description": "判断に必要な情報が足りないとき、オフィス長に質問する。回答が届くまで作業は止まる。"
                       "資料を調べれば分かることは質問しない。",
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string", "description": "具体的な質問（選択肢があれば示す）"}},
            "required": ["question"],
        },
    },
    "read_skill": {
        "name": "read_skill",
        "description": "スキルパッケージの手順書（SKILL.md）と、スキルに含まれるファイルの一覧を読む。"
                       "スキルを使う作業の前に必ず読む。",
        "input_schema": {
            "type": "object",
            "properties": {"skill": {"type": "string", "description": "スキルのフォルダ名（システムプロンプトに記載）"}},
            "required": ["skill"],
        },
    },
    "read_skill_file": {
        "name": "read_skill_file",
        "description": "スキルパッケージに含まれるファイル（参考資料やスクリプトの中身）を読む。",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {"type": "string"},
                "path": {"type": "string", "description": "スキルのフォルダ内のパス（例: scripts/thumbnail.py）"},
            },
            "required": ["skill", "path"],
        },
    },
    "run_command": {
        "name": "run_command",
        "description": "サンドボックスの作業フォルダで bash コマンドを実行する（スキルのスクリプト実行、ファイル変換など）。"
                       "スキルのファイルは /skills/<フォルダ名>/ にある（読み取り専用）。python3・uv・node・LibreOffice(soffice)・"
                       "zip が使える。インターネットには接続できないことがある。長く動くコマンドは timeout 秒で止まる。",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "実行する bash コマンド"},
                "timeout": {"type": "integer", "description": "秒（既定180、最大600）"},
            },
            "required": ["command"],
        },
    },
    "list_workspace": {
        "name": "list_workspace",
        "description": "このタスクの作業フォルダにあるファイルを一覧する。",
        "input_schema": {"type": "object", "properties": {}},
    },
    "read_workspace_file": {
        "name": "read_workspace_file",
        "description": f"作業フォルダのテキストファイルを読む（1回{READ_CHUNK}文字まで。続きは offset で）。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}},
            "required": ["path"],
        },
    },
    "write_workspace_file": {
        "name": "write_workspace_file",
        "description": "作業フォルダにテキストファイル（スクリプトや下書きなど）を書く。既存のファイルは上書きする。",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    "copy_to_workspace": {
        "name": "copy_to_workspace",
        "description": "リンクされた資料室のファイルを、作業フォルダにコピーする（スクリプトで加工するときに使う）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {"type": "string"},
                "path": {"type": "string", "description": "資料室内のパス"},
                "dest": {"type": "string", "description": "作業フォルダ内の保存先（省略時はファイル名のまま）"},
            },
            "required": ["room", "path"],
        },
    },
    "submit_file": {
        "name": "submit_file",
        "description": "作業フォルダで作ったファイル（.pptx・.docx・.xlsx・.pdf・画像など）を成果物として提出する。"
                       "読み書きできる資料室にだけ提出でき、オフィス長が承認すると資料室に保存される。",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "作業フォルダ内のファイルのパス"},
                "room": {"type": "string", "description": "保存先の資料室名"},
                "dest_path": {"type": "string", "description": "資料室内の保存先パス（例: 報告/研修資料.pptx）"},
            },
            "required": ["path", "room", "dest_path"],
        },
    },
    "ask_colleague": {
        "name": "ask_colleague",
        "description": "同じプロジェクトのメンバーに相談する（専門の知識、前の作業の意図、進め方の確認など）。"
                       "相手はその場で答える。オフィス長の判断が必要なことは ask_manager を使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "相談する相手の名前"},
                "question": {"type": "string", "description": "相談内容（背景も簡潔に）"},
            },
            "required": ["name", "question"],
        },
    },
    "read_deliverables": {
        "name": "read_deliverables",
        "description": "レビュー対象のタスクで提出された成果物（下書き）を読む。",
        "input_schema": {"type": "object", "properties": {}},
    },
    "approve_work": {
        "name": "approve_work",
        "description": "レビューの結果、問題がないと判断してオフィス長の確認に回す。",
        "input_schema": {
            "type": "object",
            "properties": {"comment": {"type": "string", "description": "オフィス長向けの所見（良い点、確認した点、気になる点）"}},
            "required": ["comment"],
        },
    },
    "request_changes": {
        "name": "request_changes",
        "description": "レビューの結果、直してほしい点があるので担当者に差し戻す。",
        "input_schema": {
            "type": "object",
            "properties": {"comment": {"type": "string", "description": "担当者への具体的な修正依頼（優先度の高い順）"}},
            "required": ["comment"],
        },
    },
    "list_members": {
        "name": "list_members",
        "description": "このプロジェクトのメンバー（名前・ロール・役職・スキル・担当中のタスク数）を一覧する。"
                       "タスクの担当を決める前に使う。",
        "input_schema": {"type": "object", "properties": {}},
    },
    "propose_plan": {
        "name": "propose_plan",
        "description": "オフィス長の依頼をタスクに分けた計画を提案する。オフィス長が承認すると、タスクが作られて担当者に"
                       "割り振られ、前工程のないタスクから作業が始まる。最後の取りまとめタスクはあなたに自動で追加される。",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "計画の概要と進め方（オフィス長向け、数行）"},
                "tasks": {
                    "type": "array",
                    "description": "実行する順に並べたタスク（1〜8件）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "instructions": {"type": "string", "description": "担当者への具体的な指示"},
                            "expected_output": {"type": "string", "description": "期待する成果物"},
                            "assignee": {"type": "string", "description": "担当するメンバーの名前"},
                            "reviewer": {"type": "string",
                                         "description": "成果物を先に確認するレビュー担当の名前（任意。担当とは別の人）"},
                            "priority": {"type": "string", "enum": ["high", "normal", "low"]},
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "先に終わっている必要があるタスクの番号（このリストの1始まりの番号。前にあるものだけ）",
                            },
                        },
                        "required": ["title", "instructions", "assignee"],
                    },
                },
            },
            "required": ["summary", "tasks"],
        },
    },
    "finish": {
        "name": "finish",
        "description": "タスクの作業を終え、オフィス長に報告する。報告後はレビュー待ちになる。",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "結果の要点、提出した成果物、残った課題を簡潔に"},
            },
            "required": ["summary"],
        },
    },
}


def tools_for(agent: Agent, kind: str = "task") -> list[dict]:
    """Tool definitions for an agent's kind of work: skill tools plus the always-available ones, in a stable order."""
    names = {t for s in agent.skills if s.enabled for t in s.tools}
    if kind in ("plan", "review"):
        names &= PLAN_SKILL_TOOLS
    names |= set(ALWAYS[kind])
    return [DEFINITIONS[n] for n in DEFINITIONS if n in names]


def server_tools_for(agent: Agent, kind: str, provider: str, model: str) -> list[dict]:
    """Anthropic-hosted tools (web search and fetch) for agents with the Web検索 skill on the Claude API."""
    names = {t for s in agent.skills if s.enabled for t in s.tools} & SERVER_TOOLS
    if kind == "review":
        names &= PLAN_SKILL_TOOLS
    if provider != "anthropic" or not names:
        return []
    # Newer models filter results before they reach the context; older ones (e.g. Haiku 4.5) use the basic tools.
    legacy = "haiku" in model or re.search(r"-4-[0-5](?!\d)", model) is not None
    versions = {"web_search": "web_search_20250305" if legacy else "web_search_20260209",
                "web_fetch": "web_fetch_20250910" if legacy else "web_fetch_20260209"}
    return [{"type": versions[n], "name": n, "max_uses": WEB_USES_PER_CALL} for n in ("web_search", "web_fetch")
            if n in names]


@dataclass
class ToolContext:
    session: Session
    agent: Agent
    project: Project | None
    task: Task | None
    workspace: str = ""
    allowed: set[str] = field(default_factory=set)
    rooms: dict[str, str] = field(default_factory=dict)  # room -> read | write
    # Linked rooms this agent's model may not read (confidential, and its provider is not allowed).
    blocked: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, session: Session, agent: Agent, project: Project, task: Task | None,
              kind: str = "task", plan_id: int | None = None) -> "ToolContext":
        return cls(session=session, agent=agent, project=project, task=task,
                   workspace=sandbox.workspace_name(task.id if task else None, plan_id),
                   allowed={t["name"] for t in tools_for(agent, kind)},
                   rooms={r.room: r.access for r in project.rooms},
                   blocked=blocked_rooms(session, agent, [r.room for r in project.rooms]))


class ToolFailure(Exception):
    """Returned to the model as an is_error tool result."""


# Control-flow tools: the runner handles them itself.
PAUSING = {"ask_manager", "finish", "propose_plan", "approve_work", "request_changes"}
# Tools the runner answers itself because they call another agent's model.
RUNNER_TOOLS = {"ask_colleague"}


def run_tool(ctx: ToolContext, name: str, args: dict) -> str:
    if name not in ctx.allowed:
        raise ToolFailure(f"ツール「{name}」は使えません（スキルが付与されていません）")
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolFailure(f"ツール「{name}」はありません")
    try:
        return handler(ctx, args)
    except (LibraryError, SkillPackageError, SandboxError) as exc:
        raise ToolFailure(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolFailure(f"引数が正しくありません: {exc}") from exc


# Reading tools an agent can use while talking in its thread, whatever its skills.
CHAT_TOOLS = ["search_documents", "list_documents", "read_document"]


def chat_context(session: Session, agent: Agent) -> ToolContext:
    """Read-only access, for thread conversations, to the rooms linked to the agent's current projects."""
    rooms: dict[str, str] = {}
    for member in session.scalars(select(ProjectMember).join(Project).where(
            ProjectMember.agent_id == agent.id, Project.status != "archived")):
        for link in member.project.rooms:
            rooms.setdefault(link.room, "read")
    return ToolContext(session=session, agent=agent, project=None, task=None, allowed=set(CHAT_TOOLS), rooms=rooms,
                       blocked=blocked_rooms(session, agent, list(rooms)))


def blocked_rooms(session: Session, agent: Agent, rooms: list[str]) -> set[str]:
    """Confidential rooms among `rooms` that this agent's model provider may not read."""
    confidential = set(session.scalars(select(LibraryRoom.name).where(
        LibraryRoom.name.in_(rooms), LibraryRoom.confidential.is_(True))))
    if not confidential:
        return set()
    allowed = {p.strip() for p in get_settings().confidential_providers.split(",") if p.strip()}
    profile = next((p for p in load_profiles(get_settings()) if p.name == agent.model_profile), None)
    return set() if profile is not None and profile.provider in allowed else confidential


def _room(ctx: ToolContext, room: str, write: bool = False) -> str:
    access = ctx.rooms.get(room)
    if access is None:
        linked = "、".join(ctx.rooms) or "なし"
        raise ToolFailure(f"資料室「{room}」はこのプロジェクトにリンクされていません（リンク済み: {linked}）")
    if room in ctx.blocked:
        raise ToolFailure(f"資料室「{room}」は機密扱いのため、あなたが使っているモデルでは読めません。"
                          "オフィス長に、この資料室を読める社員への依頼を相談してください")
    if write and access != "write":
        raise ToolFailure(f"資料室「{room}」は読み取り専用です")
    return room


def _search(ctx: ToolContext, args: dict) -> str:
    rooms = [_room(ctx, args["room"])] if args.get("room") else [r for r in ctx.rooms if r not in ctx.blocked]
    terms = [t for t in str(args["query"]).split() if t][:8]
    if not rooms and ctx.blocked:
        return "リンクされた資料室はすべて機密のため、あなたが使っているモデルでは検索できません。"
    if not rooms or not terms:
        return "検索対象の資料室がないか、検索語が空です。"
    skipped = f"（機密のため検索しなかった資料室: {'、'.join(sorted(ctx.blocked))}）" if ctx.blocked and not args.get("room") else ""
    matches = [_term_match(t) for t in terms]
    base = select(Document).where(Document.room.in_(rooms))
    docs = list(ctx.session.scalars(base.where(and_(*matches)).limit(SEARCH_LIMIT)))
    note = ""
    if not docs and len(terms) > 1:
        # No document has every word: fall back to documents with any of them.
        docs = list(ctx.session.scalars(base.where(or_(*matches)).limit(SEARCH_LIMIT)))
        note = "（すべての語を含む文書はなかったため、いずれかの語を含む文書を示します）"
    if not docs:
        return f"「{args['query']}」に一致する文書はありませんでした。言い換えや別の語でも検索してみてください。{skipped}"
    lines = [f"{len(docs)}件見つかりました{note}。{skipped}"]
    for d in docs:
        lines.append(f"- 資料室: {d.room} / パス: {d.path}（{len(d.text)}字）\n  抜粋: {_snippet(d.text, terms)}")
    return "\n".join(lines)


def _term_match(term: str):
    pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return or_(Document.text.ilike(pattern, escape="\\"), Document.path.ilike(pattern, escape="\\"))


def _snippet(text: str, terms: list[str], radius: int = 80) -> str:
    lowered = text.lower()
    hits = [p for p in (lowered.find(t.lower()) for t in terms) if p >= 0]
    start = max(min(hits) - radius, 0) if hits else 0
    return text[start:start + radius * 2].replace("\n", " ")


def _list(ctx: ToolContext, args: dict) -> str:
    room = _room(ctx, args["room"])
    folder = library.resolve(room, args.get("folder") or "")
    if not folder.is_dir():
        raise ToolFailure("フォルダが見つかりません")
    lines = []
    for child in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
        if child.name.startswith("."):
            continue
        rel = library.relative(room, child)
        lines.append(f"- 📁 {rel}/" if child.is_dir() else f"- {rel}（{child.stat().st_size} bytes）")
    return "\n".join(lines) if lines else "（空のフォルダ）"


def _read(ctx: ToolContext, args: dict) -> str:
    room = _room(ctx, args["room"])
    target = library.resolve(room, args["path"])
    rel = library.relative(room, target)
    doc = ctx.session.scalar(select(Document).where(Document.room == room, Document.path == rel))
    if doc is None:
        raise ToolFailure("文書が見つかりません。search_documents か list_documents でパスを確認してください")
    if doc.extract_error:
        raise ToolFailure(f"この文書は読み取れませんでした（{doc.extract_error}）")
    offset = max(int(args.get("offset") or 0), 0)
    chunk = doc.text[offset:offset + READ_CHUNK]
    end = offset + len(chunk)
    more = f"続きがあります。offset={end} で続きを読めます。" if end < len(doc.text) else "文書の最後まで読みました。"
    return (f'<document room="{room}" path="{rel}" chars="{len(doc.text)}" from="{offset}" to="{end}">\n'
            f"{chunk}\n</document>\n{more}")


def _members(ctx: ToolContext, args: dict) -> str:
    lines = []
    for m in ctx.project.members:
        if not m.agent.active:
            continue
        open_tasks = ctx.session.scalar(select(func.count()).select_from(Task).where(
            Task.assignee_id == m.agent_id, Task.status.in_(("backlog", "in_progress", "waiting", "review"))))
        skills = "、".join(s.name for s in m.agent.skills) or "なし"
        me = "（あなた）" if m.agent_id == ctx.agent.id else ""
        lines.append(f"- {m.agent.name}{me}: ロール {m.role.name} / 役職 {m.agent.title or 'なし'} / "
                     f"スキル {skills} / 担当中のタスク {open_tasks}件")
    return "\n".join(lines) or "メンバーがいません。"


def _submit(ctx: ToolContext, args: dict) -> str:
    if ctx.task is None:
        raise ToolFailure("成果物はタスクの作業中にだけ提出できます")
    room = _room(ctx, args["room"], write=True)
    rel = library.relative(room, library.resolve(room, args["path"]))
    if PurePosixPath(rel).suffix.lower() not in DELIVERABLE_SUFFIXES:
        raise ToolFailure("成果物は .md / .txt / .csv のいずれかで提出してください")
    content = str(args["content"])
    for old in ctx.session.scalars(select(Deliverable).where(
            Deliverable.task_id == ctx.task.id, Deliverable.room == room, Deliverable.path == rel,
            Deliverable.status == "draft")):
        old.status = "superseded"
    ctx.session.add(Deliverable(task_id=ctx.task.id, agent_id=ctx.agent.id, room=room, path=rel, content=content))
    ctx.session.flush()
    exists = (library.room_dir(room) / rel).exists()
    note = "（承認されると既存のファイルを上書きします）" if exists else ""
    return f"成果物「{room}/{rel}」（{len(content)}字）を提出しました{note}。"


def _own_package(ctx: ToolContext, folder: str) -> str:
    owned = {s.folder for s in ctx.agent.skills if s.source == "package" and s.enabled}
    if folder not in owned:
        raise ToolFailure(f"スキル「{folder}」は付与されていません（付与済み: {'、'.join(sorted(owned)) or 'なし'}）")
    return folder


def _read_skill(ctx: ToolContext, args: dict) -> str:
    folder = _own_package(ctx, str(args["skill"]))
    base = packages.package_dir(folder)
    meta = packages.parse_skill_md(base / "SKILL.md")
    files = "\n".join(f"- {f['path']}（{f['size']} bytes）" for f in packages.list_files(base))
    return (f"<skill name=\"{meta.name}\" folder=\"{folder}\">\n{meta.body}\n</skill>\n\n"
            f"## スキルのファイル（パスはスキルのフォルダからの相対パス）\n{files}")


def _read_skill_file(ctx: ToolContext, args: dict) -> str:
    folder = _own_package(ctx, str(args["skill"]))
    target = packages.resolve_file(folder, str(args["path"]))
    if not target.is_file():
        raise ToolFailure("ファイルが見つかりません。read_skill でファイル一覧を確認してください")
    return f"<skill_file skill=\"{folder}\" path=\"{args['path']}\">\n{packages.read_text(target)}\n</skill_file>"


def _run_command(ctx: ToolContext, args: dict) -> str:
    timeout = args.get("timeout")
    result = sandbox.run(ctx.workspace, str(args["command"]), int(timeout) if timeout else None)
    parts = [f"終了コード: {result['exit_code']}（{result['seconds']}秒）"]
    if result.get("timed_out"):
        parts.append("⚠ 時間切れで止めました。処理を分けるか timeout を延ばしてください。")
    if result.get("stdout"):
        parts.append("--- stdout ---\n" + result["stdout"])
    if result.get("stderr"):
        parts.append("--- stderr ---\n" + result["stderr"])
    return "\n".join(parts)


def _list_workspace(ctx: ToolContext, args: dict) -> str:
    base = sandbox.workspace_dir(ctx.workspace)
    lines = []
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base)
        if rel.parts[0] in {".home", "node_modules"} or not path.is_file():
            continue
        lines.append(f"- {rel.as_posix()}（{path.stat().st_size} bytes）")
        if len(lines) >= 300:
            lines.append("…（以下省略）")
            break
    return "\n".join(lines) if lines else "（作業フォルダは空です）"


def _read_workspace_file(ctx: ToolContext, args: dict) -> str:
    target = sandbox.resolve(ctx.workspace, str(args["path"]))
    if not target.is_file():
        raise ToolFailure("ファイルが見つかりません。list_workspace で確認してください")
    text = packages.read_text(target) if target.stat().st_size < 5_000_000 else "（大きすぎるため表示できません）"
    offset = max(int(args.get("offset") or 0), 0)
    chunk = text[offset:offset + READ_CHUNK]
    more = f"\n続きは offset={offset + len(chunk)} で読めます。" if offset + len(chunk) < len(text) else ""
    return chunk + more


def _write_workspace_file(ctx: ToolContext, args: dict) -> str:
    content = str(args["content"])
    if len(content) > MAX_WORKSPACE_WRITE:
        raise ToolFailure("内容が大きすぎます（1MBまで）")
    target = sandbox.resolve(ctx.workspace, str(args["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"{args['path']} に書きました（{len(content)}字）。"


def _copy_to_workspace(ctx: ToolContext, args: dict) -> str:
    room = _room(ctx, args["room"])
    source = library.resolve(room, args["path"])
    if not source.is_file():
        raise ToolFailure("資料室にそのファイルがありません")
    dest = sandbox.resolve(ctx.workspace, str(args.get("dest") or source.name))
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    return f"{room}/{args['path']} を作業フォルダの {dest.relative_to(sandbox.workspace_dir(ctx.workspace).resolve()).as_posix()} にコピーしました。"


def _submit_file(ctx: ToolContext, args: dict) -> str:
    if ctx.task is None:
        raise ToolFailure("成果物はタスクの作業中にだけ提出できます")
    room = _room(ctx, args["room"], write=True)
    source = sandbox.resolve(ctx.workspace, str(args["path"]))
    if not source.is_file():
        raise ToolFailure("作業フォルダにそのファイルがありません。list_workspace で確認してください")
    if source.stat().st_size > MAX_SUBMIT_BYTES:
        raise ToolFailure("ファイルが大きすぎます（100MBまで）")
    rel = library.relative(room, library.resolve(room, args["dest_path"]))
    kept = get_settings().data_dir / "files" / "deliverables" / f"task-{ctx.task.id}" / f"{uuid.uuid4().hex}{source.suffix}"
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, kept)
    for old in ctx.session.scalars(select(Deliverable).where(
            Deliverable.task_id == ctx.task.id, Deliverable.room == room, Deliverable.path == rel,
            Deliverable.status == "draft")):
        old.status = "superseded"
    ctx.session.add(Deliverable(task_id=ctx.task.id, agent_id=ctx.agent.id, room=room, path=rel, content="",
                                file_path=str(kept)))
    ctx.session.flush()
    return f"ファイル「{room}/{rel}」（{kept.stat().st_size} bytes）を成果物として提出しました。"


def _read_deliverables(ctx: ToolContext, args: dict) -> str:
    if ctx.task is None:
        raise ToolFailure("レビュー対象のタスクがありません")
    drafts = list(ctx.session.scalars(select(Deliverable).where(Deliverable.task_id == ctx.task.id,
                                                                Deliverable.status == "draft")))
    if not drafts:
        return "提出された成果物はありません（報告のみ）。"
    parts = []
    for d in drafts:
        if d.file_path:
            parts.append(f'<deliverable room="{d.room}" path="{d.path}">（ファイル成果物のため本文は読めません）</deliverable>')
        else:
            parts.append(f'<deliverable room="{d.room}" path="{d.path}">\n{d.content[:READ_CHUNK]}\n</deliverable>')
    return "\n\n".join(parts)


_HANDLERS = {
    "search_documents": _search,
    "list_documents": _list,
    "read_document": _read,
    "submit_deliverable": _submit,
    "list_members": _members,
    "read_deliverables": _read_deliverables,
    "read_skill": _read_skill,
    "read_skill_file": _read_skill_file,
    "run_command": _run_command,
    "list_workspace": _list_workspace,
    "read_workspace_file": _read_workspace_file,
    "write_workspace_file": _write_workspace_file,
    "copy_to_workspace": _copy_to_workspace,
    "submit_file": _submit_file,
}


def describe_call(name: str, args: dict) -> str:
    """Short, human-readable line for the work log."""
    if name in ("submit_deliverable", "write_workspace_file"):
        return json.dumps({k: v for k, v in args.items() if k != "content"} | {"content": f"{len(args.get('content', ''))}字"},
                          ensure_ascii=False)
    return json.dumps(args, ensure_ascii=False)
