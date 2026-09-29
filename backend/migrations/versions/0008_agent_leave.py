"""agents take leave instead of retiring

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-29
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("agents", "retired_at", new_column_name="leave_started_at")


def downgrade() -> None:
    op.alter_column("agents", "leave_started_at", new_column_name="retired_at")
