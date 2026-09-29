from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from .config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def check_database() -> tuple[bool, str]:
    """Return (ok, detail) for the health check."""
    try:
        with get_engine().connect() as conn:
            version = conn.execute(text("SHOW server_version")).scalar_one()
        return True, f"PostgreSQL {version}"
    except Exception as exc:  # noqa: BLE001 - surfaced to the settings screen
        return False, type(exc).__name__
