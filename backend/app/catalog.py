"""Built-in skills and agent templates shipped with makaseta.

Built-in skills are upserted into the database on startup so every agent can reference them by id.
Templates stay in code: they are only starting points for the hire form.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ProjectRole, Skill

AVATAR_COLORS = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]

BUILTIN_SKILLS = [
    {
        "key": "search",
        "name": "資料検索",
        "description": "リンクされた資料室から、依頼に関係する資料を探して読む",
        "instructions": "依頼のキーワードと言い換えで資料を検索し、関係する文書を読んでから作業する。使った資料は文書名で示す。",
        "tools": ["search_documents", "list_documents", "read_document"],
    },
    {
        "key": "write",
        "name": "文書作成",
        "description": "報告書やメモなどの成果物を下書きする",
        "instructions": "目的と読み手を確認し、結論を先に書く。見出しと箇条書きで整理し、成果物として保存する。",
        "tools": ["submit_deliverable"],
    },
    {
        "key": "summarize",
        "name": "要約",
        "description": "長い資料や会話の要点をまとめる",
        "instructions": "要点、根拠、未解決の点に分けて短くまとめる。原文にないことは書かない。",
        "tools": ["read_document"],
    },
    {
        "key": "review",
        "name": "レビュー",
        "description": "成果物の誤りや抜け漏れを確認する",
        "instructions": "依頼の目的に照らして確認し、事実誤り・根拠のない記述・抜け漏れを優先度付きで指摘する。指摘には修正案を添える。",
        "tools": ["list_documents", "read_document"],
    },
    {
        "key": "plan",
        "name": "タスク分解",
        "description": "依頼を具体的なタスクに分け、担当を割り振る",
        "instructions": "依頼のゴールと完了条件を確認し、1人が一度に終えられる大きさのタスクに分ける。各タスクに期待する成果物とロールを書く。",
        "tools": [],
    },
]

BUILTIN_ROLES = [
    {
        "key": "manager",
        "name": "マネージャー",
        "description": "オフィス長の窓口。依頼をタスクに分解して社員に割り振り、成果物を取りまとめて報告する",
        "is_manager": True,
    },
    {
        "key": "researcher",
        "name": "調査担当",
        "description": "資料室や情報源を調べ、根拠付きで要点をまとめる",
        "is_manager": False,
    },
    {
        "key": "writer",
        "name": "資料作成者",
        "description": "調査結果をもとに報告書や資料を作る",
        "is_manager": False,
    },
    {
        "key": "reviewer",
        "name": "レビュアー",
        "description": "成果物を確認し、誤りや抜け漏れを指摘する",
        "is_manager": False,
    },
]

AGENT_TEMPLATES = [
    {
        "key": "researcher",
        "title": "リサーチャー",
        "description": "資料を調べて要点を整理する",
        "personality": "好奇心が強く、事実と推測をはっきり分けて話す。",
        "instructions": "依頼に関係する資料を資料室から探し、根拠となる文書名を必ず示してまとめる。分からないことは推測で埋めず、質問する。",
        "skill_keys": ["search", "summarize"],
        "avatar_color": "c1",
    },
    {
        "key": "writer",
        "title": "ライター",
        "description": "報告書や資料の文章を書く",
        "personality": "読み手を意識し、平易で簡潔な文章を好む。",
        "instructions": "目的と読み手を確認してから書く。結論を先に書き、見出しと箇条書きで読みやすく整える。",
        "skill_keys": ["search", "write", "summarize"],
        "avatar_color": "c2",
    },
    {
        "key": "analyst",
        "title": "アナリスト",
        "description": "データや情報を比較・分析する",
        "personality": "数字に強く、前提と限界を明示する。",
        "instructions": "比較の軸を先に決め、数字には出典と単位を付ける。結論には確からしさを添える。",
        "skill_keys": ["search", "summarize", "write"],
        "avatar_color": "c3",
    },
    {
        "key": "reviewer",
        "title": "レビュアー",
        "description": "成果物の誤りや抜け漏れを確認する",
        "personality": "慎重で率直。指摘には理由と修正案を添える。",
        "instructions": "依頼の目的に照らして成果物を確認し、事実誤り、根拠のない記述、抜け漏れを優先度付きで指摘する。",
        "skill_keys": ["search", "review"],
        "avatar_color": "c4",
    },
    {
        "key": "manager",
        "title": "プロジェクトマネージャー",
        "description": "依頼を分解し、社員に割り振って取りまとめる",
        "personality": "全体を見渡し、段取りと期限を重視する。",
        "instructions": "オフィス長の依頼を具体的なタスクに分解し、ロールに合う社員に割り振る。進捗を把握し、成果物を取りまとめて報告する。判断に迷う点はオフィス長に確認する。",
        "skill_keys": ["plan", "review", "summarize"],
        "avatar_color": "c5",
    },
]


def seed_builtin_skills(session: Session) -> None:
    """Create or refresh the built-in skills; user-made skills are left alone."""
    existing = {s.key: s for s in session.scalars(select(Skill).where(Skill.builtin.is_(True)))}
    for spec in BUILTIN_SKILLS:
        skill = existing.get(spec["key"])
        if skill is None:
            session.add(Skill(builtin=True, **spec))
            continue
        for field in ("name", "description", "instructions", "tools"):
            setattr(skill, field, spec[field])
    session.commit()


def seed_builtin_roles(session: Session) -> None:
    existing = {r.key: r for r in session.scalars(select(ProjectRole).where(ProjectRole.builtin.is_(True)))}
    for spec in BUILTIN_ROLES:
        role = existing.get(spec["key"])
        if role is None:
            session.add(ProjectRole(builtin=True, **spec))
            continue
        for field in ("name", "description", "is_manager"):
            setattr(role, field, spec[field])
    session.commit()
