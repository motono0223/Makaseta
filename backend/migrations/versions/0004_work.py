"""runs, work log, threads, deliverables and usage

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _fk(table: str, ondelete: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{table}.id", ondelete=ondelete)


def upgrade() -> None:
    now = sa.func.now()
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(8), nullable=False, server_default="task"),
        sa.Column("agent_id", sa.Integer, _fk("agents", "CASCADE"), nullable=False, index=True),
        sa.Column("project_id", sa.Integer, _fk("projects", "CASCADE")),
        sa.Column("task_id", sa.Integer, _fk("tasks", "CASCADE"), index=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued", index=True),
        sa.Column("transcript", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("pending_tool_use_id", sa.String(80)),
        sa.Column("pending_results", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("steps", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Integer, _fk("runs", "CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent_id", sa.Integer, _fk("agents", "CASCADE"), index=True),
        sa.Column("project_id", sa.Integer, _fk("projects", "CASCADE"), index=True),
        sa.Column("task_id", sa.Integer, _fk("tasks", "SET NULL")),
        sa.Column("run_id", sa.Integer, _fk("runs", "SET NULL")),
        sa.Column("sender", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="chat"),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_table(
        "deliverables",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, _fk("tasks", "CASCADE"), nullable=False, index=True),
        sa.Column("agent_id", sa.Integer, _fk("agents", "SET NULL")),
        sa.Column("room", sa.String(80), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now, index=True),
        sa.Column("agent_id", sa.Integer, _fk("agents", "SET NULL")),
        sa.Column("project_id", sa.Integer, _fk("projects", "SET NULL")),
        sa.Column("task_id", sa.Integer, _fk("tasks", "SET NULL")),
        sa.Column("run_id", sa.Integer, _fk("runs", "SET NULL")),
        sa.Column("model_profile", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    for table in ("usage_records", "deliverables", "messages", "run_steps", "runs"):
        op.drop_table(table)
