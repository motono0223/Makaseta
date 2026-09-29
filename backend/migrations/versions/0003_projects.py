"""projects, roles, members, linked rooms and tasks

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "project_roles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), unique=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_manager", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("builtin", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("goal", sa.Text, nullable=False, server_default=""),
        sa.Column("done_criteria", sa.Text, nullable=False, server_default=""),
        sa.Column("due_date", sa.Date),
        sa.Column("status", sa.String(16), nullable=False, server_default="planning"),
        sa.Column("require_plan_approval", sa.Boolean, nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_table(
        "project_members",
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Integer, sa.ForeignKey("project_roles.id"), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "project_rooms",
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("room", sa.String(80), primary_key=True),
        sa.Column("access", sa.String(8), nullable=False, server_default="read"),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("instructions", sa.Text, nullable=False, server_default=""),
        sa.Column("expected_output", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="backlog"),
        sa.Column("priority", sa.String(8), nullable=False, server_default="normal"),
        sa.Column("due_date", sa.Date),
        sa.Column("assignee_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("reviewer_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("requested_by_agent_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("rank", sa.Integer, nullable=False, server_default="0"),
        *_timestamps(),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("project_rooms")
    op.drop_table("project_members")
    op.drop_table("projects")
    op.drop_table("project_roles")
