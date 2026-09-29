from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import office_archive as archive
from ..db import get_session
from ..office_archive import ArchiveError

router = APIRouter(prefix="/api/office", tags=["office"])
SessionDep = Annotated[Session, Depends(get_session)]
MAX_UPLOAD = 5 * 1024 * 1024 * 1024


class ExportIn(BaseModel):
    include_work: bool = False


def _fail(exc: ArchiveError) -> HTTPException:
    return HTTPException(exc.status, str(exc))


@router.post("/export", status_code=status.HTTP_201_CREATED)
def export_office(body: ExportIn, session: SessionDep) -> dict:
    path = archive.export_office(session, body.include_work)
    return {"name": path.name, "size": path.stat().st_size}


@router.get("/exports")
def list_exports() -> list[dict]:
    return archive.list_exports()


@router.get("/exports/{name}")
def download_export(name: str) -> FileResponse:
    try:
        return FileResponse(archive.export_path(name), filename=name, media_type="application/zip")
    except ArchiveError as exc:
        raise _fail(exc) from exc


@router.delete("/exports/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_export(name: str) -> None:
    try:
        archive.export_path(name).unlink()
    except ArchiveError as exc:
        raise _fail(exc) from exc


@router.post("/import")
def import_office(request: Request, session: SessionDep, file: Annotated[UploadFile, File()]) -> dict:
    upload = archive.exports_dir() / f".upload-{id(file)}.zip"
    try:
        written = 0
        with upload.open("wb") as out:
            while chunk := file.file.read(8 * 1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ファイルが大きすぎます")
                out.write(chunk)
        return archive.import_office(session, upload, request.app.state.scanner)
    except ArchiveError as exc:
        session.rollback()
        raise _fail(exc) from exc
    finally:
        upload.unlink(missing_ok=True)
