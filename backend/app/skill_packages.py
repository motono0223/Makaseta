"""Skill packages: Agent Skills folders (SKILL.md plus scripts and references) under SKILLS_ROOT.

Imports from GitHub land in a hidden staging folder first; the office head reviews the contents and
only then are they moved into place. Nothing in a package runs inside the app container: scripts run
in the sandbox, and the app only reads the files.
"""

import io
import json
import re
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Skill

STAGING = ".staging"
MAX_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_PACKAGE_BYTES = 50 * 1024 * 1024
MAX_FILES = 2000
MAX_READ_CHARS = 60_000
SCRIPT_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".sh", ".bash"}
# Reading the package, plus the sandbox workspace its scripts need.
PACKAGE_TOOLS = ["read_skill", "read_skill_file", "run_command", "list_workspace", "read_workspace_file",
                 "write_workspace_file", "copy_to_workspace", "submit_file"]


class SkillPackageError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class SkillMeta:
    name: str
    description: str
    license: str
    body: str


def root() -> Path:
    return get_settings().skills_root.resolve()


def parse_skill_md(path: Path) -> SkillMeta:
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not match:
        raise SkillPackageError("SKILL.md の先頭に name と description を書いた YAML（--- で囲む）がありません")
    try:
        front = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillPackageError(f"SKILL.md の YAML を読めません: {exc}") from exc
    name = str(front.get("name") or "").strip()
    description = str(front.get("description") or "").strip()
    if not name or not description:
        raise SkillPackageError("SKILL.md に name と description が必要です")
    return SkillMeta(name=name, description=description, license=str(front.get("license") or ""),
                     body=match.group(2))


def folder_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.").lower()
    if not slug:
        raise SkillPackageError("スキル名からフォルダ名を作れません")
    return slug[:80]


def package_dir(folder: str) -> Path:
    if not folder or folder.startswith(".") or "/" in folder or "\\" in folder:
        raise SkillPackageError("スキルのフォルダ名が正しくありません")
    path = root() / folder
    if not (path / "SKILL.md").is_file():
        raise SkillPackageError(f"スキル「{folder}」が見つかりません", 404)
    return path


def resolve_file(folder: str, rel: str) -> Path:
    base = package_dir(folder)
    target = (base / rel).resolve()
    if not target.is_relative_to(base.resolve()):
        raise SkillPackageError("スキルのフォルダの外は読めません")
    return target


def list_files(base: Path) -> list[dict]:
    files = []
    for path in sorted(base.rglob("*")):
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(base).parts):
            rel = path.relative_to(base).as_posix()
            files.append({"path": rel, "size": path.stat().st_size, "script": path.suffix.lower() in SCRIPT_SUFFIXES})
    return files


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return f"（バイナリファイルのため表示できません: {len(data)} bytes）"
    text = data.decode("utf-8", errors="replace")
    if len(text) > MAX_READ_CHARS:
        return text[:MAX_READ_CHARS] + f"\n…（{len(text) - MAX_READ_CHARS}文字省略）"
    return text


# ---- scanning ----

def scan(session: Session) -> None:
    """Match Skill rows to the package folders on disk."""
    base = root()
    base.mkdir(parents=True, exist_ok=True)
    found: dict[str, SkillMeta] = {}
    for path in sorted(base.iterdir()):
        if path.is_dir() and not path.name.startswith(".") and (path / "SKILL.md").is_file():
            try:
                found[path.name] = parse_skill_md(path / "SKILL.md")
            except SkillPackageError:
                continue
    existing = {s.folder: s for s in session.scalars(select(Skill).where(Skill.source == "package"))}
    for folder, meta in found.items():
        skill = existing.get(folder)
        if skill is None:
            skill = Skill(key=f"pkg:{folder}", source="package", folder=folder, builtin=False)
            session.add(skill)
        skill.name = meta.name[:80]
        skill.description = meta.description
        skill.tools = list(PACKAGE_TOOLS)
        skill.enabled = True
    for folder, skill in existing.items():
        if folder not in found:
            skill.enabled = False
    session.commit()


def meta_file(folder: Path) -> Path:
    return folder / ".makaseta.json"


# ---- import from GitHub ----

def parse_github_url(url: str) -> tuple[str, str, str | None, str]:
    """(owner, repo, ref or None, path inside the repo) from a github.com URL."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https" or parsed.netloc not in {"github.com", "www.github.com"}:
        raise SkillPackageError("https://github.com/ で始まるURLを指定してください")
    parts = [urllib.parse.unquote(p) for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise SkillPackageError("リポジトリのURLではありません")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        path = "/".join(parts[4:])
        if parts[2] == "blob":
            path = str(PurePosixPath(path).parent) if path.endswith("SKILL.md") else path
        return owner, repo, parts[3], path.strip("/").removeprefix(".")
    return owner, repo, None, ""


def _fetch(url: str, limit: int) -> bytes:
    headers = {"User-Agent": "makaseta", "Accept": "application/vnd.github+json"}
    token = get_settings().github_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SkillPackageError("GitHub でリポジトリかブランチが見つかりません（非公開なら .env に GITHUB_TOKEN を設定）", 404) from exc
        raise SkillPackageError(f"GitHub からの取得に失敗しました（{exc.code}）", 502) from exc
    except urllib.error.URLError as exc:
        raise SkillPackageError(f"GitHub に接続できませんでした: {exc.reason}", 502) from exc
    if len(data) > limit:
        raise SkillPackageError("ダウンロードが大きすぎます", 413)
    return data


def stage_from_github(url: str) -> str:
    """Download the folder a URL points to into staging and return the staging id."""
    owner, repo, ref, path = parse_github_url(url)
    if ref is None:
        info = json.loads(_fetch(f"https://api.github.com/repos/{owner}/{repo}", 1_000_000))
        ref = info.get("default_branch") or "main"
    archive = _fetch(f"https://api.github.com/repos/{owner}/{repo}/tarball/{urllib.parse.quote(ref)}",
                     MAX_ARCHIVE_BYTES)
    stage_id = uuid.uuid4().hex
    dest = root() / STAGING / stage_id
    dest.mkdir(parents=True)
    try:
        _extract(archive, path, dest)
        if not (dest / "SKILL.md").is_file():
            raise SkillPackageError("指定したフォルダに SKILL.md がありません。スキルのフォルダのURLを指定してください")
        meta_file(dest).write_text(json.dumps({"source_url": url, "ref": ref}), encoding="utf-8")
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return stage_id


def _extract(archive: bytes, subpath: str, dest: Path) -> None:
    prefix = PurePosixPath(subpath) if subpath else None
    total, count = 0, 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            parts = PurePosixPath(member.name).parts[1:]  # drop the "owner-repo-sha/" top folder
            if not parts:
                continue
            rel = PurePosixPath(*parts)
            if prefix is not None:
                if rel == prefix or not rel.is_relative_to(prefix):
                    continue
                rel = rel.relative_to(prefix)
            if member.isdir():
                continue
            if not member.isfile():
                continue  # symlinks, devices, etc. are never extracted
            if rel.is_absolute() or ".." in rel.parts:
                raise SkillPackageError("アーカイブに不正なパスが含まれています")
            total += member.size
            count += 1
            if total > MAX_PACKAGE_BYTES or count > MAX_FILES:
                raise SkillPackageError("スキルが大きすぎます（50MB・2000ファイルまで）", 413)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is not None:
                target.write_bytes(source.read())
    if count == 0:
        raise SkillPackageError("指定したフォルダにファイルがありません")


def staged_dir(stage_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", stage_id):
        raise SkillPackageError("取り込みIDが正しくありません", 404)
    path = root() / STAGING / stage_id
    if not path.is_dir():
        raise SkillPackageError("取り込み中のスキルが見つかりません（期限切れの可能性があります）", 404)
    return path


def install(session: Session, stage_id: str, replace: bool = False) -> Skill:
    staged = staged_dir(stage_id)
    meta = parse_skill_md(staged / "SKILL.md")
    folder = folder_name(meta.name)
    target = root() / folder
    if target.exists():
        if not replace:
            raise SkillPackageError(f"スキル「{folder}」はすでにあります。置き換える場合は上書きを選んでください", 409)
        shutil.rmtree(target)
    shutil.move(str(staged), str(target))
    source = json.loads(meta_file(target).read_text(encoding="utf-8")) if meta_file(target).exists() else {}
    scan(session)
    skill = session.scalar(select(Skill).where(Skill.folder == folder))
    skill.source_url = source.get("source_url", "")
    session.commit()
    return skill


def discard(stage_id: str) -> None:
    shutil.rmtree(staged_dir(stage_id), ignore_errors=True)


def remove(session: Session, skill: Skill) -> None:
    if skill.source != "package" or not skill.folder:
        raise SkillPackageError("組み込みスキルは削除できません")
    shutil.rmtree(root() / skill.folder, ignore_errors=True)
    session.delete(skill)
    session.commit()
