from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from . import __version__
from .catalog import seed_builtin_skills
from .config import get_settings
from .db import check_database, run_migrations, session_factory
from .llm_profiles import ModelProfile, load_profiles
from .routers import agents


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    with session_factory()() as session:
        seed_builtin_skills(session)
    yield


app = FastAPI(title="makaseta", version=__version__, lifespan=lifespan)
app.include_router(agents.router)


@app.get("/api/health")
def health() -> dict:
    db_ok, db_detail = check_database()
    files_dir = get_settings().data_dir / "files"
    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "database": {"ok": db_ok, "detail": db_detail},
        "storage": {"ok": files_dir.is_dir(), "path": str(files_dir)},
    }


@app.get("/api/settings/models")
def model_profiles() -> list[ModelProfile]:
    return load_profiles(get_settings())


# ---- 画面（ビルド済みのReact）を配信する。未知のパスは index.html に回す ----

@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404)
    static_dir: Path = get_settings().static_dir.resolve()
    candidate = (static_dir / path).resolve()
    if path and candidate.is_file() and candidate.is_relative_to(static_dir):
        return FileResponse(candidate)
    index = static_dir / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="frontend is not built")
    return FileResponse(index)
