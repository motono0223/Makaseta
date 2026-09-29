"""agent notes (業務メモ)

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_notes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="reflection"),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("agent_notes")
