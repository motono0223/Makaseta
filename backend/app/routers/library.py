import shutil
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import library
from ..config import get_settings
from ..db import get_session
from ..extract import EDITABLE_SUFFIXES, TEXT_SUFFIXES, decode_text
from ..library import LibraryError
from ..models import Document, LibraryRoom

router = APIRouter(prefix="/api/library", tags=["library"])
SessionDep = Annotated[Session, Depends(get_session)]

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_VIEW_BYTES = 2 * 1024 * 1024
SNIPPET_RADIUS = 60


def _fail(exc: LibraryError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


# ---- schemas ----

class RoomOut(BaseModel):
    name: str
    description: str
    documents: int
    total_size: int
    updated_at: datetime | None


class RoomCreate(BaseModel):
    name: str
    description: str = Field(default="", max_length=2000)


class RoomUpdate(BaseModel):
    description: str = Field(max_length=2000)


class EntryOut(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: datetime | None = None
    indexed: bool = False
    text_chars: int = 0
    extract_error: str = ""
    created_by_kind: str | None = None


class FolderCreate(BaseModel):
    path: str


class TextFile(BaseModel):
    path: str
    content: str = Field(max_length=MAX_VIEW_BYTES)


class TextView(BaseModel):
    path: str
    editable: bool
    source: str  # raw | extracted | none
    content: str
    extract_error: str = ""


class SearchHit(BaseModel):
    room: str
    path: str
    snippet: str
    size: int


class LibraryStatus(BaseModel):
    host_path: str
    scanning: bool
    last_scan_at: datetime | None
    last_result: dict[str, int]
    documents: int


# ---- status and rescan ----

@router.get("/status")
def library_status(request: Request, session: SessionDep) -> LibraryStatus:
    scanner = request.app.state.scanner
    return LibraryStatus(
        host_path=get_settings().library_host_path,
        scanning=scanner.scanning,
        last_scan_at=scanner.last_scan_at,
        last_result=scanner.last_result,
        documents=session.scalar(select(func.count()).select_from(Document)) or 0,
    )


@router.post("/rescan")
def rescan(request: Request) -> dict[str, int]:
    return request.app.state.scanner.scan_now()


# ---- rooms ----

@router.get("/rooms")
def list_rooms(session: SessionDep) -> list[RoomOut]:
    settings = {r.name: r for r in session.scalars(select(LibraryRoom))}
    stats = {
        room: (count, size or 0, updated)
        for room, count, size, updated in session.execute(
            select(Document.room, func.count(), func.sum(Document.size), func.max(Document.indexed_at)).group_by(
                Document.room
            )
        )
    }
    rooms = []
    for name in library.list_room_names():
        count, size, updated = stats.get(name, (0, 0, None))
        rooms.append(
            RoomOut(
                name=name,
                description=settings[name].description if name in settings else "",
                documents=count,
                total_size=size,
                updated_at=updated,
            )
        )
    return rooms


@router.post("/rooms", status_code=status.HTTP_201_CREATED)
def create_room(body: RoomCreate, session: SessionDep) -> RoomOut:
    try:
        name = library.check_name(body.name, "資料室の名前")
    except LibraryError as exc:
        raise _fail(exc) from exc
    path = library.root() / name
    if path.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, f"資料室「{name}」はすでにあります")
    path.mkdir(parents=True)
    session.merge(LibraryRoom(name=name, description=body.description))
    session.commit()
    return RoomOut(name=name, description=body.description, documents=0, total_size=0, updated_at=None)


@router.patch("/rooms/{room}")
def update_room(room: str, body: RoomUpdate, session: SessionDep) -> dict[str, str]:
    try:
        library.room_dir(room)
    except LibraryError as exc:
        raise _fail(exc) from exc
    session.merge(LibraryRoom(name=room, description=body.description))
    session.commit()
    return {"name": room, "description": body.description}


@router.delete("/rooms/{room}", status_code=status.HTTP_204_NO_CONTENT)
def delete_room(room: str, session: SessionDep) -> None:
    try:
        path = library.room_dir(room)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if any(p for p in path.iterdir() if not p.name.startswith(".")):
        raise HTTPException(status.HTTP_409_CONFLICT, "資料室が空ではありません。中のファイルを先に削除してください")
    shutil.rmtree(path)
    library.forget(session, room, "")
    session.execute(LibraryRoom.__table__.delete().where(LibraryRoom.name == room))
    session.commit()


# ---- browsing ----

@router.get("/rooms/{room}/entries")
def list_entries(room: str, session: SessionDep, path: str = "") -> list[EntryOut]:
    try:
        folder = library.resolve(room, path)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if not folder.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "フォルダが見つかりません")

    prefix = library.relative(room, folder)
    prefix = "" if prefix == "." else prefix + "/"
    docs = {
        d.path: d
        for d in session.scalars(
            select(Document).where(Document.room == room, Document.path.startswith(prefix, autoescape=True))
        )
    }
    entries = []
    for child in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue
        rel = library.relative(room, child)
        if child.is_dir():
            entries.append(EntryOut(name=child.name, path=rel, is_dir=True))
            continue
        stat = child.stat()
        doc = docs.get(rel)
        entries.append(
            EntryOut(
                name=child.name,
                path=rel,
                is_dir=False,
                size=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc),
                indexed=doc is not None and doc.mtime == stat.st_mtime,
                text_chars=len(doc.text) if doc else 0,
                extract_error=doc.extract_error if doc else "",
                created_by_kind=doc.created_by_kind if doc else None,
            )
        )
    return entries


@router.get("/rooms/{room}/download")
def download(room: str, path: str) -> FileResponse:
    try:
        target = library.resolve(room, path)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ファイルが見つかりません")
    return FileResponse(target, filename=target.name)


@router.get("/rooms/{room}/text")
def view_text(room: str, path: str, session: SessionDep) -> TextView:
    try:
        target = library.resolve(room, path)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ファイルが見つかりません")
    suffix = target.suffix.lower()
    rel = library.relative(room, target)
    if suffix in TEXT_SUFFIXES:
        if target.stat().st_size > MAX_VIEW_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ファイルが大きすぎて表示できません")
        return TextView(path=rel, editable=suffix in EDITABLE_SUFFIXES, source="raw",
                        content=decode_text(target.read_bytes()))
    doc = session.scalar(select(Document).where(Document.room == room, Document.path == rel))
    if doc is None:
        return TextView(path=rel, editable=False, source="none", content="")
    return TextView(path=rel, editable=False, source="extracted", content=doc.text[:MAX_VIEW_BYTES],
                    extract_error=doc.extract_error)


# ---- changes ----

@router.post("/rooms/{room}/folders", status_code=status.HTTP_201_CREATED)
def create_folder(room: str, body: FolderCreate) -> EntryOut:
    try:
        target = library.resolve(room, body.path)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if target.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "同じ名前のファイルかフォルダがすでにあります")
    target.mkdir(parents=True)
    return EntryOut(name=target.name, path=library.relative(room, target), is_dir=True)


@router.post("/rooms/{room}/text", status_code=status.HTTP_201_CREATED)
def create_text(room: str, body: TextFile, session: SessionDep) -> EntryOut:
    return _write_text(room, body, session, create=True)


@router.put("/rooms/{room}/text")
def save_text(room: str, body: TextFile, session: SessionDep) -> EntryOut:
    return _write_text(room, body, session, create=False)


def _write_text(room: str, body: TextFile, session: Session, create: bool) -> EntryOut:
    try:
        target = library.resolve(room, body.path)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if target.suffix.lower() not in EDITABLE_SUFFIXES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "この形式のファイルは画面で編集できません")
    if create and target.exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "同じ名前のファイルがすでにあります")
    if not create and not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ファイルが見つかりません")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    library.index_file(session, room, target, force=True)
    session.commit()
    return EntryOut(name=target.name, path=library.relative(room, target), is_dir=False,
                    size=target.stat().st_size, indexed=True, text_chars=len(body.content))


@router.post("/rooms/{room}/upload", status_code=status.HTTP_201_CREATED)
def upload(
    room: str,
    session: SessionDep,
    files: Annotated[list[UploadFile], File()],
    folder: Annotated[str, Form()] = "",
    overwrite: Annotated[bool, Form()] = False,
) -> list[EntryOut]:
    try:
        base = library.resolve(room, folder)
        targets = [library.resolve(room, f"{folder}/{library.check_name(f.filename or '', 'ファイル名')}") for f in files]
    except LibraryError as exc:
        raise _fail(exc) from exc
    if not base.is_dir():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "アップロード先のフォルダが見つかりません")
    if not overwrite:
        existing = [t.name for t in targets if t.exists()]
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, f"同じ名前のファイルがあります: {', '.join(existing)}")

    saved = []
    for upload_file, target in zip(files, targets):
        _save_upload(upload_file, target)
        doc = library.index_file(session, room, target, force=True)
        session.commit()
        saved.append(EntryOut(name=target.name, path=doc.path, is_dir=False, size=doc.size, indexed=True,
                              text_chars=len(doc.text), extract_error=doc.extract_error,
                              created_by_kind=doc.created_by_kind))
    return saved


def _save_upload(upload_file: UploadFile, target) -> None:
    partial = target.with_name(f".{target.name}.uploading")
    written = 0
    try:
        with partial.open("wb") as out:
            while chunk := upload_file.file.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        f"{upload_file.filename} が大きすぎます（上限 100MB）")
                out.write(chunk)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


@router.delete("/rooms/{room}/entries", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(room: str, path: str, session: SessionDep) -> None:
    try:
        target = library.resolve(room, path)
    except LibraryError as exc:
        raise _fail(exc) from exc
    if target == library.room_dir(room):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "資料室そのものはこの操作では削除できません")
    rel = library.relative(room, target)
    if target.is_dir():
        if any(True for p in target.iterdir() if not p.name.startswith(".")):
            raise HTTPException(status.HTTP_409_CONFLICT, "フォルダが空ではありません")
        shutil.rmtree(target)
    elif target.is_file():
        target.unlink()
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ファイルが見つかりません")
    library.forget(session, room, rel)
    session.commit()


# ---- search ----

@router.get("/search")
def search(session: SessionDep, q: str, room: str | None = None, limit: int = 50) -> list[SearchHit]:
    terms = [t for t in q.split() if t][:8]
    if not terms:
        return []
    query = select(Document)
    for term in terms:
        pattern = "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(Document.text.ilike(pattern, escape="\\"), Document.path.ilike(pattern, escape="\\")))
    if room:
        query = query.where(Document.room == room)
    query = query.order_by(Document.indexed_at.desc()).limit(min(limit, 200))
    return [SearchHit(room=d.room, path=d.path, snippet=_snippet(d.text, terms), size=d.size)
            for d in session.scalars(query)]


def _snippet(text: str, terms: list[str]) -> str:
    lowered = text.lower()
    positions = [p for p in (lowered.find(t.lower()) for t in terms) if p >= 0]
    if not positions:
        return text[: SNIPPET_RADIUS * 2].replace("\n", " ")
    start = max(min(positions) - SNIPPET_RADIUS, 0)
    snippet = text[start : start + SNIPPET_RADIUS * 3].replace("\n", " ")
    return ("…" if start > 0 else "") + snippet + ("…" if start + SNIPPET_RADIUS * 3 < len(text) else "")
