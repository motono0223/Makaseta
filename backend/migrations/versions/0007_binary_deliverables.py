"""binary deliverables

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deliverables", sa.Column("file_path", sa.Text))


def downgrade() -> None:
    op.drop_column("deliverables", "file_path")
