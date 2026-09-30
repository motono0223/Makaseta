"""subtasks, plan parents and manager-managed backlogs

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-30
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("parent_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="SET NULL")))
    op.create_index("ix_tasks_parent_id", "tasks", ["parent_id"])
    op.add_column("plans", sa.Column("parent_task_id", sa.Integer, sa.ForeignKey("tasks.id", ondelete="SET NULL")))
    op.add_column("plans", sa.Column("owns_parent", sa.Boolean, nullable=False, server_default=sa.false()))
    # Existing projects keep working by hand; new projects turn this on when created.
    op.add_column("projects", sa.Column("auto_manage", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("projects", "auto_manage")
    op.drop_column("plans", "owns_parent")
    op.drop_column("plans", "parent_task_id")
    op.drop_index("ix_tasks_parent_id", "tasks")
    op.drop_column("tasks", "parent_id")
