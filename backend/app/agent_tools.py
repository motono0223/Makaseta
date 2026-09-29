"""Tools an agent can call while working on a task.

Every tool checks the project's 資料室 links itself: what the model asks for never widens access.
Document text goes back wrapped in <document> tags and is treated as data, not instructions.
"""

import json
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from . import library
from .library import LibraryError
from .models import Agent, Deliverable, Document, Project, Task

READ_CHUNK = 20_000
SEARCH_LIMIT = 10
DELIVERABLE_SUFFIXES = {".md", ".txt", ".csv"}

# Tools every agent has, regardless of skills.
ALWAYS = ["ask_manager", "finish"]

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


def tools_for(agent: Agent) -> list[dict]:
    """Tool definitions for an agent: its skills' tools plus the always-available ones, in a stable order."""
    names = {t for s in agent.skills for t in s.tools} | set(ALWAYS)
    return [DEFINITIONS[n] for n in DEFINITIONS if n in names]


@dataclass
class ToolContext:
    session: Session
    agent: Agent
    project: Project
    task: Task
    allowed: set[str] = field(default_factory=set)
    rooms: dict[str, str] = field(default_factory=dict)  # room -> read | write

    @classmethod
    def build(cls, session: Session, agent: Agent, project: Project, task: Task) -> "ToolContext":
        return cls(session=session, agent=agent, project=project, task=task,
                   allowed={t["name"] for t in tools_for(agent)},
                   rooms={r.room: r.access for r in project.rooms})


class ToolFailure(Exception):
    """Returned to the model as an is_error tool result."""


# Control-flow tools: the runner handles them itself.
PAUSING = {"ask_manager", "finish"}


def run_tool(ctx: ToolContext, name: str, args: dict) -> str:
    if name not in ctx.allowed:
        raise ToolFailure(f"ツール「{name}」は使えません（スキルが付与されていません）")
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolFailure(f"ツール「{name}」はありません")
    try:
        return handler(ctx, args)
    except LibraryError as exc:
        raise ToolFailure(str(exc)) from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ToolFailure(f"引数が正しくありません: {exc}") from exc


def _room(ctx: ToolContext, room: str, write: bool = False) -> str:
    access = ctx.rooms.get(room)
    if access is None:
        linked = "、".join(ctx.rooms) or "なし"
        raise ToolFailure(f"資料室「{room}」はこのプロジェクトにリンクされていません（リンク済み: {linked}）")
    if write and access != "write":
        raise ToolFailure(f"資料室「{room}」は読み取り専用です")
    return room


def _search(ctx: ToolContext, args: dict) -> str:
    rooms = [_room(ctx, args["room"])] if args.get("room") else list(ctx.rooms)
    terms = [t for t in str(args["query"]).split() if t][:8]
    if not rooms or not terms:
        return "検索対象の資料室がないか、検索語が空です。"
    matches = [_term_match(t) for t in terms]
    base = select(Document).where(Document.room.in_(rooms))
    docs = list(ctx.session.scalars(base.where(and_(*matches)).limit(SEARCH_LIMIT)))
    note = ""
    if not docs and len(terms) > 1:
        # No document has every word: fall back to documents with any of them.
        docs = list(ctx.session.scalars(base.where(or_(*matches)).limit(SEARCH_LIMIT)))
        note = "（すべての語を含む文書はなかったため、いずれかの語を含む文書を示します）"
    if not docs:
        return f"「{args['query']}」に一致する文書はありませんでした。言い換えや別の語でも検索してみてください。"
    lines = [f"{len(docs)}件見つかりました{note}。"]
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


def _submit(ctx: ToolContext, args: dict) -> str:
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


_HANDLERS = {
    "search_documents": _search,
    "list_documents": _list,
    "read_document": _read,
    "submit_deliverable": _submit,
}


def describe_call(name: str, args: dict) -> str:
    """Short, human-readable line for the work log."""
    if name == "submit_deliverable":
        return json.dumps({k: v for k, v in args.items() if k != "content"} | {"content": f"{len(args.get('content', ''))}字"},
                          ensure_ascii=False)
    return json.dumps(args, ensure_ascii=False)
