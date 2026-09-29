"""Client for the sandbox container that runs skill scripts, and the task workspaces it shares with the app."""

import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import get_settings

WORKSPACE_NAME = re.compile(r"^(task|plan)-\d+$")


class SandboxError(Exception):
    pass


def workspace_name(task_id: int | None, plan_id: int | None) -> str:
    return f"task-{task_id}" if task_id is not None else f"plan-{plan_id}"


def workspace_dir(name: str) -> Path:
    if not WORKSPACE_NAME.match(name):
        raise SandboxError("作業フォルダの名前が正しくありません")
    path = get_settings().work_root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve(name: str, rel: str) -> Path:
    base = workspace_dir(name).resolve()
    target = (base / rel.lstrip("/")).resolve()
    if not target.is_relative_to(base):
        raise SandboxError("作業フォルダの外は扱えません")
    return target


def run(name: str, command: str, timeout: int | None = None) -> dict:
    workspace_dir(name)
    limit = min(timeout or get_settings().sandbox_timeout, 600)
    body = json.dumps({"workspace": name, "command": command, "timeout": limit}).encode()
    request = urllib.request.Request(f"{get_settings().sandbox_url}/run", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=limit + 30) as response:
            return json.loads(response.read())
    except urllib.error.URLError as exc:
        raise SandboxError(f"サンドボックスに接続できません（{exc.reason}）。sandbox コンテナが起動しているか確認してください") from exc


_ips: tuple[float, set[str]] = (0.0, set())


def addresses() -> set[str]:
    """IP addresses of the sandbox container, refreshed every 30 seconds."""
    global _ips
    checked, ips = _ips
    if time.monotonic() - checked > 30:
        host = urllib.parse.urlparse(get_settings().sandbox_url).hostname or ""
        try:
            ips = set(socket.gethostbyname_ex(host)[2]) if host not in {"localhost", "127.0.0.1"} else set()
        except OSError:
            ips = set()
        _ips = (time.monotonic(), ips)
    return ips


def healthy() -> bool:
    try:
        with urllib.request.urlopen(f"{get_settings().sandbox_url}/health", timeout=3) as response:
            return json.loads(response.read()).get("ok") is True
    except (urllib.error.URLError, ValueError, OSError):
        return False
