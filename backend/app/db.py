from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with session_factory()() as session:
        yield session


def run_migrations() -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    command.upgrade(cfg, "head")


def check_database() -> tuple[bool, str]:
    """Return (ok, detail) for the health check."""
    try:
        with get_engine().connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
        return True, f"PostgreSQL {version}"
    except Exception as exc:  # noqa: BLE001 - surfaced to the settings screen
        return False, type(exc).__name__
