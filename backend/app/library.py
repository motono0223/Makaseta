"""資料室: folders under LIBRARY_ROOT whose files are indexed into the documents table.

The folders on disk are the source of truth. Files copied in on the host are picked up by the
periodic scan; files changed through the app are indexed right away.
Hidden files and folders (names starting with ".") are ignored and cannot be created.
"""

import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import get_settings
from .extract import EXTRACTABLE_SUFFIXES, extract_text
from .models import Document

log = logging.getLogger(__name__)

MAX_NAME_LENGTH = 80
_FORBIDDEN_CHARS = set('/\\\0:*?"<>|')


class LibraryError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def root() -> Path:
    return get_settings().library_root.resolve()


def check_name(name: str, what: str = "名前") -> str:
    name = name.strip()
    if not name or name in {".", ".."} or name.startswith("."):
        raise LibraryError(f"{what}が空か、「.」で始まっています")
    if len(name) > MAX_NAME_LENGTH:
        raise LibraryError(f"{what}は{MAX_NAME_LENGTH}文字以内にしてください")
    if any(c in _FORBIDDEN_CHARS for c in name):
        raise LibraryError(f'{what}に使えない文字（/ \\ : * ? " < > |）が含まれています')
    return name


def room_dir(room: str) -> Path:
    path = root() / check_name(room, "資料室の名前")
    if not path.is_dir():
        raise LibraryError(f"資料室「{room}」が見つかりません", 404)
    return path


def resolve(room: str, rel: str) -> Path:
    """Map a path inside a room to disk, refusing anything that leaves the room."""
    base = room_dir(room)
    parts = [p for p in PurePosixPath(rel.replace("\\", "/")).parts if p not in {"", "/"}]
    for part in parts:
        check_name(part, "ファイル名")
    target = base.joinpath(*parts)
    if not target.resolve().is_relative_to(base.resolve()):
        raise LibraryError("資料室の外は参照できません")
    return target


def relative(room: str, path: Path) -> str:
    return path.relative_to(room_dir(room)).as_posix()


def list_room_names() -> list[str]:
    base = root()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith("."))


def iter_files(base: Path):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            if not filename.startswith("."):
                yield Path(dirpath) / filename


# ---- indexing ----

def index_file(
    session: Session,
    room: str,
    path: Path,
    *,
    created_by_kind: str = "manager",
    agent_id: int | None = None,
    task_id: int | None = None,
    force: bool = False,
) -> Document:
    rel = relative(room, path)
    stat = path.stat()
    doc = session.scalar(select(Document).where(Document.room == room, Document.path == rel))
    if doc is not None and not force and doc.size == stat.st_size and doc.mtime == stat.st_mtime:
        return doc

    text, error = "", ""
    if path.suffix.lower() in EXTRACTABLE_SUFFIXES:
        try:
            text = extract_text(path)
        except Exception as exc:  # noqa: BLE001 - a broken file must not stop the scan
            error = f"{type(exc).__name__}: {exc}"[:500]

    if doc is None:
        doc = Document(room=room, path=rel, created_by_kind=created_by_kind, created_by_agent_id=agent_id,
                       source_task_id=task_id)
        session.add(doc)
    doc.size = stat.st_size
    doc.mtime = stat.st_mtime
    doc.text = text
    doc.extract_error = error
    doc.indexed_at = datetime.now(timezone.utc)
    return doc


def forget(session: Session, room: str, rel_prefix: str) -> None:
    """Drop index entries for a file, or for everything under a folder."""
    session.execute(
        delete(Document).where(
            Document.room == room,
            (Document.path == rel_prefix) | Document.path.startswith(rel_prefix + "/", autoescape=True),
        )
    )


def scan(session: Session) -> dict[str, int]:
    """Bring the index in line with the folders on disk."""
    known = {(d.room, d.path): (d.size, d.mtime) for d in session.execute(select(Document.room, Document.path,
                                                                                  Document.size, Document.mtime))}
    seen: set[tuple[str, str]] = set()
    counts = {"indexed": 0, "removed": 0, "files": 0}

    for room in list_room_names():
        base = root() / room
        for path in iter_files(base):
            try:
                stat = path.stat()
            except OSError:
                continue
            key = (room, path.relative_to(base).as_posix())
            seen.add(key)
            counts["files"] += 1
            if known.get(key) == (stat.st_size, stat.st_mtime):
                continue
            index_file(session, room, path)
            session.commit()
            counts["indexed"] += 1

    for room, rel in set(known) - seen:
        session.execute(delete(Document).where(Document.room == room, Document.path == rel))
        counts["removed"] += 1
    session.commit()
    return counts


class Scanner:
    """Background thread that rescans the library every few seconds."""

    def __init__(self, session_factory, interval: int):
        self._session_factory = session_factory
        self._interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="library-scanner", daemon=True)
        self.last_scan_at: datetime | None = None
        self.last_result: dict[str, int] = {}

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    @property
    def scanning(self) -> bool:
        return self._lock.locked()

    def scan_now(self) -> dict[str, int]:
        with self._lock, self._session_factory()() as session:
            self.last_result = scan(session)
            self.last_scan_at = datetime.now(timezone.utc)
            return self.last_result

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_now()
            except Exception:  # noqa: BLE001 - keep scanning on the next tick
                log.exception("library scan failed")
            self._stop.wait(self._interval)
