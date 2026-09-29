"""peer review by a reviewer agent

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("review_stage", sa.String(8)))
    op.add_column("tasks", sa.Column("peer_rounds", sa.Integer, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("tasks", "peer_rounds")
    op.drop_column("tasks", "review_stage")
