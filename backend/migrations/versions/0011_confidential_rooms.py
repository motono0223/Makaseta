"""confidential 資料室

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("library_rooms", sa.Column("confidential", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("library_rooms", "confidential")
