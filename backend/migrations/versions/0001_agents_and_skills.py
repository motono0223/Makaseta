"""agents and skills

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("instructions", sa.Text, nullable=False, server_default=""),
        sa.Column("tools", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("builtin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "agents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("title", sa.String(40), nullable=False, server_default=""),
        sa.Column("avatar_color", sa.String(16), nullable=False, server_default="c1"),
        sa.Column("personality", sa.Text, nullable=False, server_default=""),
        sa.Column("instructions", sa.Text, nullable=False, server_default=""),
        sa.Column("model_profile", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("retired_at", sa.DateTime(timezone=True)),
        sa.Column("template_key", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "agent_skills",
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("skill_id", sa.Integer, sa.ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("agent_skills")
    op.drop_table("agents")
    op.drop_table("skills")
