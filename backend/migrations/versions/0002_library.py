"""library rooms and documents

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "library_rooms",
        sa.Column("name", sa.String(80), primary_key=True),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("room", sa.String(80), nullable=False, index=True),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("size", sa.BigInteger, nullable=False),
        sa.Column("mtime", sa.Float, nullable=False),
        sa.Column("text", sa.Text, nullable=False, server_default=""),
        sa.Column("extract_error", sa.Text, nullable=False, server_default=""),
        sa.Column("created_by_kind", sa.String(16), nullable=False, server_default="manager"),
        sa.Column("created_by_agent_id", sa.Integer, sa.ForeignKey("agents.id", ondelete="SET NULL")),
        sa.Column("source_task_id", sa.Integer),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("room", "path"),
    )
    op.execute("CREATE INDEX ix_documents_text_trgm ON documents USING gin (text gin_trgm_ops)")
    op.execute("CREATE INDEX ix_documents_path_trgm ON documents USING gin (path gin_trgm_ops)")


def downgrade() -> None:
    op.drop_table("documents")
    op.drop_table("library_rooms")
