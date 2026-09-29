"""skill packages (Agent Skills folders)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("skills", sa.Column("source", sa.String(16), nullable=False, server_default="builtin"))
    op.add_column("skills", sa.Column("folder", sa.String(80), unique=True))
    op.add_column("skills", sa.Column("source_url", sa.Text, nullable=False, server_default=""))
    op.add_column("skills", sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    for column in ("enabled", "source_url", "folder", "source"):
        op.drop_column("skills", column)
