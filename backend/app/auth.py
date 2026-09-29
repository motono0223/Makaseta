"""Optional password login: on when MAKASETA_PASSWORD is set (required before exposing the app on a network)."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

from .config import get_settings

COOKIE = "makaseta_session"
MAX_AGE = 30 * 24 * 3600
ATTEMPTS_PER_MINUTE = 10

_attempts: dict[str, deque] = defaultdict(deque)


def required() -> bool:
    return bool(get_settings().makaseta_password)


def _secret() -> bytes:
    """Per-install random key, so changing the password or the key file signs everyone out."""
    path = get_settings().data_dir / "files" / ".session-key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return hashlib.sha256(path.read_text().encode() + get_settings().makaseta_password.encode()).digest()


def issue() -> str:
    expires = str(int(time.time()) + MAX_AGE)
    return f"{expires}.{hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()}"


def valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    expires, signature = token.split(".", 1)
    if not expires.isdigit() or int(expires) < time.time():
        return False
    expected = hmac.new(_secret(), expires.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def check_password(password: str, client: str) -> bool:
    """Compare in constant time, allowing a few attempts per minute per client."""
    window = _attempts[client]
    now = time.monotonic()
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= ATTEMPTS_PER_MINUTE:
        return False
    window.append(now)
    return hmac.compare_digest(password.encode(), get_settings().makaseta_password.encode())


def too_many_attempts(client: str) -> bool:
    return len(_attempts[client]) >= ATTEMPTS_PER_MINUTE
