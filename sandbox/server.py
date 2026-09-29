"""Tiny command runner for the makaseta sandbox (standard library only).

POST /run {"workspace": "task-12", "command": "python make.py", "timeout": 120}
  -> {"exit_code": 0, "stdout": "...", "stderr": "...", "timed_out": false, "seconds": 1.2}
GET /health -> {"ok": true}
"""

import json
import os
import re
import signal
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WORK_ROOT = Path(os.environ.get("WORK_ROOT", "/work"))
SKILLS_ROOT = os.environ.get("SKILLS_ROOT", "/skills")
MAX_TIMEOUT = int(os.environ.get("MAX_TIMEOUT", "600"))
MAX_OUTPUT = 20_000
WORKSPACE_NAME = re.compile(r"^(task|plan)-\d+$")


def run(workspace: str, command: str, timeout: int) -> dict:
    cwd = WORK_ROOT / workspace
    cwd.mkdir(parents=True, exist_ok=True)
    home = cwd / ".home"
    home.mkdir(exist_ok=True)
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "NODE_PATH": os.environ.get("NODE_PATH", "/usr/local/lib/node_modules"),
        "SKILLS_ROOT": SKILLS_ROOT,
        "PYTHONUNBUFFERED": "1",
    }
    started = time.monotonic()
    process = subprocess.Popen(["bash", "-c", command], cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    return {
        "exit_code": process.returncode,
        "stdout": _clip(stdout),
        "stderr": _clip(stderr),
        "timed_out": timed_out,
        "seconds": round(time.monotonic() - started, 2),
    }


def _clip(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    if len(text) <= MAX_OUTPUT:
        return text
    half = MAX_OUTPUT // 2
    return f"{text[:half]}\n…（{len(text) - MAX_OUTPUT}文字省略）…\n{text[-half:]}"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send(404, {"error": "not found"})
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            workspace = str(body["workspace"])
            command = str(body["command"])
            timeout = min(max(int(body.get("timeout", 120)), 1), MAX_TIMEOUT)
        except (ValueError, KeyError, TypeError):
            self._send(400, {"error": "bad request"})
            return
        if not WORKSPACE_NAME.match(workspace):
            self._send(400, {"error": "bad workspace"})
            return
        self._send(200, run(workspace, command, timeout))

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
