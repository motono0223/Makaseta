"""manager plans and task dependencies

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False,
                  index=True),
        sa.Column("agent_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("request", sa.Text, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="drafting"),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("items", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.add_column("tasks", sa.Column("plan_id", sa.Integer, sa.ForeignKey("plans.id", ondelete="SET NULL")))
    op.add_column("tasks", sa.Column("depends_on", sa.JSON, nullable=False, server_default="[]"))
    op.add_column("runs", sa.Column("plan_id", sa.Integer, sa.ForeignKey("plans.id", ondelete="CASCADE")))


def downgrade() -> None:
    op.drop_column("runs", "plan_id")
    op.drop_column("tasks", "depends_on")
    op.drop_column("tasks", "plan_id")
    op.drop_table("plans")
