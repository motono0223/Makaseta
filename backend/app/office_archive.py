"""Move a whole office to another machine: export everything to one zip, import it elsewhere.

The zip holds the database rows as JSON (per table), the 資料室 and skill folders, kept deliverable files,
the model profiles for reference and, optionally, the task workspaces. Secrets (.env, the session key) are
never included. Importing replaces the current office, after saving a backup of it.
"""

import json
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Date, DateTime, Numeric, delete, insert, select, text
from sqlalchemy.orm import Session

from . import __version__
from .config import get_settings
from .models import Base, Run

FORMAT = "makaseta-office/1"
SKIP_FILES = {".session-key"}
EXPORTS = "exports"


class ArchiveError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def exports_dir() -> Path:
    path = get_settings().data_dir / "files" / EXPORTS
    path.mkdir(parents=True, exist_ok=True)
    return path


def _revision(session: Session) -> str:
    return session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _folders(include_work: bool) -> dict[str, Path]:
    settings = get_settings()
    folders = {
        "library": settings.library_root,
        "skills": settings.skills_root,
        "files": settings.data_dir / "files",
    }
    if include_work:
        folders["work"] = settings.work_root
    return folders


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def export_office(session: Session, include_work: bool = False) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    target = exports_dir() / f"makaseta-office-{stamp}.zip"
    manifest = {"format": FORMAT, "app_version": __version__, "revision": _revision(session),
                "created_at": datetime.now(timezone.utc).isoformat(), "include_work": include_work, "tables": {}}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for table in Base.metadata.sorted_tables:
            rows = [{k: _json_value(v) for k, v in row._mapping.items()} for row in session.execute(select(table))]
            zf.writestr(f"db/{table.name}.json", json.dumps(rows, ensure_ascii=False))
            manifest["tables"][table.name] = len(rows)
        for prefix, folder in _folders(include_work).items():
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*")):
                rel = path.relative_to(folder)
                if not path.is_file() or path.is_symlink() or rel.name in SKIP_FILES:
                    continue
                if prefix == "files" and rel.parts[0] == EXPORTS:
                    continue  # never nest earlier exports
                if prefix == "skills" and rel.parts[0] == ".staging":
                    continue  # imports still under review
                zf.write(path, f"{prefix}/{rel.as_posix()}")
        models = get_settings().models_config
        if models.is_file():
            zf.write(models, "config/models.yaml")
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return target


def read_manifest(archive: Path) -> dict:
    try:
        with zipfile.ZipFile(archive) as zf:
            manifest = json.loads(zf.read("manifest.json"))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ArchiveError("makaseta のオフィスの書き出しファイルではありません") from exc
    if manifest.get("format") != FORMAT:
        raise ArchiveError("対応していない形式のファイルです")
    return manifest


def import_office(session: Session, archive: Path, scanner) -> dict:
    manifest = read_manifest(archive)
    revision = _revision(session)
    if manifest["revision"] != revision:
        raise ArchiveError(
            f"書き出したアプリと、このアプリのデータの版が違います（書き出し: {manifest['revision']} / "
            f"このアプリ: {revision}）。両方を同じバージョンにそろえてから取り込んでください", 409)
    busy = session.scalar(select(Run.id).where(Run.status.in_(("queued", "running"))).limit(1))
    if busy is not None:
        raise ArchiveError("社員が作業中です。作業が終わってから取り込んでください", 409)

    backup = export_office(session, include_work=False)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                name = Path(member.filename)
                if name.is_absolute() or ".." in name.parts:
                    raise ArchiveError("ファイルに不正なパスが含まれています")
            zf.extractall(tmp)
        staged = Path(tmp)
        with scanner.paused():
            _restore_database(session, staged / "db")
            for prefix, folder in _folders(bool(manifest.get("include_work"))).items():
                _replace_folder(staged / prefix, folder, keep={EXPORTS, ".session-key"} if prefix == "files" else set())
    return {"backup": backup.name, "tables": manifest["tables"], "created_at": manifest["created_at"]}


def _restore_database(session: Session, folder: Path) -> None:
    tables = Base.metadata.sorted_tables
    for table in reversed(tables):
        session.execute(delete(table))
    for table in tables:
        path = folder / f"{table.name}.json"
        rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if rows:
            session.execute(insert(table), [_from_json(table, row) for row in rows])
    session.flush()
    for table in tables:
        if "id" in table.c and table.c.id.type.python_type is int:
            session.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"))
    session.commit()


def _from_json(table, row: dict) -> dict:
    out = {}
    for key, value in row.items():
        column = table.c.get(key)
        if column is None:
            continue
        if value is not None and isinstance(column.type, DateTime):
            value = datetime.fromisoformat(value)
        elif value is not None and isinstance(column.type, Date):
            value = date.fromisoformat(value)
        elif value is not None and isinstance(column.type, Numeric):
            value = Decimal(value)
        out[key] = value
    return out


def _replace_folder(source: Path, target: Path, keep: set[str]) -> None:
    """Make target's contents match source, leaving the named top-level entries alone."""
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        if child.name in keep or child.name == ".gitkeep":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    if source.is_dir():
        for child in source.iterdir():
            if child.name in keep:
                continue
            destination = target / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            else:
                shutil.copy2(child, destination)
    os.sync()


def list_exports() -> list[dict]:
    return [{"name": p.name, "size": p.stat().st_size,
             "created_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
            for p in sorted(exports_dir().glob("makaseta-office-*.zip"), reverse=True)]


def export_path(name: str) -> Path:
    path = exports_dir() / name
    if "/" in name or not name.startswith("makaseta-office-") or not path.is_file():
        raise ArchiveError("書き出しファイルが見つかりません", 404)
    return path
