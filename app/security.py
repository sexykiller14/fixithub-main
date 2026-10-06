"""Security helpers: password hashing, signed sessions, CSRF, client IP."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import ADMIN_HASH_FILE, settings

SESSION_COOKIE = "fixithub_admin"

SESSION_MAX_AGE = 60 * 60 * 8  # 8 hours

_serialiser = URLSafeTimedSerializer(settings.secret_key, salt="fixithub-session")


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a bcrypt hash. Never raises."""
    if not password or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def save_admin_hash(password_hash: str, password_changed_at: float | None = None) -> None:
    """Persist the admin bcrypt hash to data/admin.json.

    `password_changed_at` is when the password last changed. It is written
    separately from `updated_at` because it is load-bearing: admin sessions are
    signed cookies with no database row, so this timestamp is the only way to
    tell whether a cookie was issued before or after the current password was
    set. Without it a leaked password would leave every existing admin cookie
    valid for the rest of its eight-hour life.

    Raises OSError if the file cannot be written, so a caller can report a
    failed change rather than claim one succeeded. A read-only volume is the
    realistic case.
    """
    ADMIN_HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_HASH_FILE.write_text(
        json.dumps(
            {
                "password_hash": password_hash,
                "updated_at": time.time(),
                "password_changed_at": (
                    time.time() if password_changed_at is None else password_changed_at
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def admin_password_changed_at() -> float:
    """When the admin password last changed, or 0.0 if it is not recorded.

    0.0 for a file written before this field existed, so an older admin.json
    keeps working rather than locking the admin out.
    """
    if not ADMIN_HASH_FILE.is_file():
        return 0.0
    try:
        data = json.loads(ADMIN_HASH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0.0
    try:
        return float(data.get("password_changed_at") or 0.0)
    except (TypeError, ValueError):
        return 0.0


_password_cache: dict[str, str] = {}


def load_admin_hash() -> str:
    """Resolve the admin hash: explicit hash env var, then the saved file,
    then the plain password env var.

    The plain password is hashed on demand with bcrypt, which costs roughly
    300ms at cost 12. Since the footer asks whether an admin password is
    configured on every single page render, that cost would otherwise be paid
    on every request whenever the hash env var and the file are both absent,
    which is the normal state of a fresh cloud deploy. The result is cached
    because the inputs cannot change without a restart.

    The cache is keyed on the password itself so that it is correct even if
    settings is reloaded in-process, which the tests do.
    """
    if settings.admin_password_hash:
        return settings.admin_password_hash.strip()
    if ADMIN_HASH_FILE.is_file():
        try:
            data = json.loads(ADMIN_HASH_FILE.read_text(encoding="utf-8"))
            stored = str(data.get("password_hash", "")).strip()
        except (OSError, ValueError):
            stored = ""
        # An unreadable or half-written file must not stop us falling through
        # to the environment, or a corrupt file locks the admin out entirely
        # even when a working password is configured.
        if stored:
            return stored

    password = settings.admin_password
    if not password:
        return ""
    cached = _password_cache.get(password)
    if cached is None:
        cached = hash_password(password)
        _password_cache[password] = cached
    return cached


def admin_configured() -> bool:
    return bool(load_admin_hash())


# --------------------------------------------------------------------------
# Login throttling
# --------------------------------------------------------------------------

_login_attempts: dict[str, list[float]] = {}
LOGIN_WINDOW = 300.0        # 5 minutes
LOGIN_MAX_FAILURES = 5


def login_locked_out(identifier: str) -> tuple[bool, int]:
    """Return (is_locked, seconds_remaining) for an identifier."""
    now = time.time()
    attempts = [ts for ts in _login_attempts.get(identifier, []) if now - ts < LOGIN_WINDOW]
    _login_attempts[identifier] = attempts
    if len(attempts) >= LOGIN_MAX_FAILURES:
        oldest = attempts[0]
        return True, int(max(0, LOGIN_WINDOW - (now - oldest)))
    return False, 0


def record_login_failure(identifier: str) -> None:
    _login_attempts.setdefault(identifier, []).append(time.time())


def clear_login_failures(identifier: str) -> None:
    _login_attempts.pop(identifier, None)


# --------------------------------------------------------------------------
# Signed session cookie
# --------------------------------------------------------------------------


@dataclass
class AdminSession:
    username: str = "admin"
    issued_at: float = 0.0
    # The password_changed_at in force when this cookie was issued. Compared
    # against the stored value on every read, which is what invalidates the
    # cookies minted before a password change.
    password_changed_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def create_session_token(username: str = "admin") -> str:
    payload = AdminSession(
        username=username,
        issued_at=time.time(),
        password_changed_at=admin_password_changed_at(),
    ).to_dict()
    return _serialiser.dumps(payload)


def read_session_token(token: str | None) -> AdminSession | None:
    """Verify and decode the signed session cookie.

    A cookie issued before the current password was set is rejected here, which
    is how changing the password signs out every other admin browser. The caller
    that performed the change immediately issues a fresh cookie, so the admin
    who made the change stays signed in.
    """
    if not token:
        return None
    try:
        data = _serialiser.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:  # noqa: BLE001 - any decoding failure means no session
        return None
    if not isinstance(data, dict) or "username" not in data:
        return None

    stamped = float(data.get("password_changed_at", 0.0))
    if stamped != admin_password_changed_at():
        return None

    return AdminSession(
        username=str(data["username"]),
        issued_at=float(data.get("issued_at", 0.0)),
        password_changed_at=stamped,
    )


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------


def generate_csrf(session_token: str) -> str:
    """Derive a CSRF token from a session secret.

    Tying it to the session means a token is useless without the matching
    cookie, and it survives page loads without extra storage.
    """
    raw = hashlib.sha256(f"{session_token}:{settings.secret_key}".encode()).hexdigest()
    return raw[:48]


# Key holding a random value inside the signed-cookie session. CSRF for reader
# forms is derived from it rather than from the cookie string, because on a
# first visit no session cookie exists yet and there would be nothing to derive
# from. Writing the anchor into the session makes Starlette's SessionMiddleware
# set the cookie on the same response, so the very first form already has a
# usable token.
READER_CSRF_ANCHOR = "_csrf_anchor"


def reader_csrf(request) -> str:
    """The CSRF token for reader-facing forms, seeding the anchor if needed."""
    anchor = request.session.get(READER_CSRF_ANCHOR)
    if not anchor:
        anchor = secrets.token_urlsafe(32)
        request.session[READER_CSRF_ANCHOR] = anchor
    return generate_csrf(anchor)


def valid_reader_csrf(request, submitted: str) -> bool:
    """Check a submitted reader CSRF token against the session's anchor."""
    anchor = request.session.get(READER_CSRF_ANCHOR) or ""
    if not anchor or not submitted:
        return False
    return hmac.compare_digest(generate_csrf(anchor), submitted)


def valid_csrf(session_token: str, submitted: str) -> bool:
    """Constant-time comparison of the submitted token against the session."""
    if not session_token or not submitted:
        return False
    return hmac.compare_digest(generate_csrf(session_token), submitted)


# --------------------------------------------------------------------------
# Client identification
# --------------------------------------------------------------------------

_trusted_proxy_header = "x-forwarded-for"


def client_ip(request) -> str:
    """Best-effort client IP.

    X-Forwarded-For is only consulted when the app is explicitly configured to
    sit behind a proxy, because otherwise a client could spoof it to bypass
    rate limiting.
    """
    if settings.debug or getattr(settings, "trust_proxy_headers", False):
        forwarded = request.headers.get(_trusted_proxy_header)
        if forwarded:
            # Left-most entry is the original client.
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return _sanitise_ip(candidate)
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return _sanitise_ip(client.host)
    return "unknown"


def _sanitise_ip(value: str) -> str:
    """Keep only characters that can appear in an address."""
    return "".join(ch for ch in value if ch in "0123456789abcdefABCDEF.:_[]-")[:64]


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left or "", right or "")


# Schemes an admin-entered link may use. Anything else, javascript: and
# data: in particular, would be rendered into an href on every public page.
_LINK_SCHEMES = ("http://", "https://", "mailto:")


def safe_link_url(value: str) -> str:
    """Return a link that is safe to put in an href, or "" to reject it.

    Two shapes are accepted: an absolute URL with an allowed scheme, and a
    root-relative path. A relative path has no scheme to check, but must
    still start at the root so "//evil.example" cannot be used to send the
    browser to another host while looking local.
    """
    candidate = (value or "").strip()
    if not candidate:
        return ""
    lowered = candidate.lower()
    if lowered.startswith(_LINK_SCHEMES):
        return candidate
    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate
    return ""


def new_token(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


# Removed rather than left in place, because dead security constants are worse
# than absent ones - they read as if they are load-bearing:
#   CSRF_FIELD, CSRF_SESSION_KEY, _csrf_tokens, CSRF_TOKEN_TTL
# Those were the remains of a stored-CSRF-token scheme that was replaced by a
# token derived from the session cookie. Every form and route uses the field
# name "csrf"; nothing reads CSRF_FIELD, which claimed the name was
# "csrf_token".
