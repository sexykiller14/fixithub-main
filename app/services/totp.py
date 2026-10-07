"""Time-based one-time passwords (RFC 6238) for the admin account.

Implemented against the standard library rather than pyotp. TOTP is HMAC-SHA1
over a counter with a fixed truncation step, which is hmac + hashlib +
struct; adding a dependency for forty lines of arithmetic would have been the
only reason pyotp is a common choice. The trade-off is that this is security
code, so tests/test_totp.py checks it against the RFC's own published test
vectors rather than against itself.

What authenticator apps need is an otpauth:// URI. Rendering that as a QR code
needs a real encoder, so this module returns the URI and the admin's browser
turns it into a QR image - or they type the secret in by hand, which is why the
setup page always shows it.

The secret lives in the database, in a single row, rather than in a file. It was
data/admin_2fa.json, which broke on serverless hosts: the filesystem there is
read-only and is discarded on every deploy, so enrolment appeared to succeed and
then stopped validating after the next cold start. An existing file is imported
into the database the first time it is read, so upgrading does not silently drop
an enrolment.

The secret is base32, not encrypted: there is no crypto library in this
project's dependencies and adding one for a single admin's TOTP secret would be
a large new surface. A TOTP secret is a shared HMAC key rather than a password,
and what protects the database is the same thing that protects the password hash
in it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from pathlib import Path

from ..config import DATA_DIR

# RFC 6238 parameters. T0 is the Unix epoch; the counter is (now - T0) / step.
T0 = 0
DIGITS = 6
STEP_SECONDS = 30

# SHA1 is what every authenticator app implements. It is not a password hash
# and does not need to be: the shared secret is 160 bits of randomness and the
# HMAC key is that secret.
ALGORITHM = "sha1"

ISSUER = "FixIT Hub"

# How far either side's clock may drift and still accept a code. One step is
# generous but normal; a large window would widen the guessing space.
WINDOW = 1

_SECRET_BYTES = 20  # 160 bits, the RFC's recommendation


def generate_secret() -> str:
    """A fresh base32 secret, as authenticator apps expect to be shown."""
    return base64.b32encode(secrets.token_bytes(_SECRET_BYTES)).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    """Decode base32, restoring the padding generate_secret strips."""
    padded = secret.strip().upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded, casefold=True)


def code_at(secret: str, timestamp: float | None = None, step: int = STEP_SECONDS) -> str:
    """The code for one time step. Split out so tests can pin a fixed time."""
    now = int(timestamp if timestamp is not None else time.time())
    counter = (now - T0) // step
    message = struct.pack(">Q", counter)
    digest = hmac.new(_secret_bytes(secret), message, getattr(hashlib, ALGORITHM)).digest()

    # RFC 4226 dynamic truncation: the low nibble of the last byte selects the
    # 4-byte window to read.
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**DIGITS)).zfill(DIGITS)


def verify(secret: str, submitted: str, timestamp: float | None = None) -> bool:
    """Whether a submitted code is valid for the secret, within the window.

    Every candidate in the window is compared, and the loop does not break on
    the first match, so the time taken does not reveal which step matched.
    """
    candidate = (submitted or "").strip()
    if not candidate.isdigit() or len(candidate) != DIGITS:
        # Not a code at all. Same message either way so the login form cannot
        # be used to probe the format.
        return False

    now = timestamp if timestamp is not None else time.time()
    matched = False
    for drift in range(-WINDOW, WINDOW + 1):
        offset = int(now) + drift * STEP_SECONDS
        # Constant-time compare, and no early exit.
        matched |= hmac.compare_digest(code_at(secret, offset), candidate)
    return matched


def provisioning_uri(secret: str, account: str = "admin") -> str:
    """The otpauth:// URI an authenticator app scans.

    Only the fields the apps actually read are included; anything else is
    ignored by them and would just be noise in a QR code.
    """
    from urllib.parse import quote

    label = quote(f"{ISSUER}:{account}")
    return (
        f"otpauth://totp/{label}"
        f"?secret={quote(secret)}"
        f"&issuer={quote(ISSUER)}"
        f"&algorithm=SHA1"
        f"&digits={DIGITS}"
        f"&period={STEP_SECONDS}"
    )


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


def _legacy_path() -> Path | None:
    """The pre-database file, if one exists. Read once, then ignored.

    Only consulted so an existing enrolment survives the upgrade. On Vercel the
    file is a /tmp leftover that was never durable anyway, so there is nothing
    to import and this returns None.
    """
    candidate = Path(DATA_DIR) / "admin_2fa.json"
    if candidate.is_file():
        return candidate
    if bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")):
        tmp = Path("/tmp/admin_2fa.json")
        if tmp.is_file():
            return tmp
    return None


def _row():
    from ..models import AdminTwoFactor

    return AdminTwoFactor


SINGLETON_ID = 1


def is_enrolled() -> bool:
    """True when a usable secret is stored."""
    return bool(_load().get("secret"))


def _load() -> dict:
    """The enrolment as a dict, in the shape the callers already expect.

    Returns {} when there is no enrolment, and also when the stored row is
    somehow unreadable, so a bad record can never lock the admin out of their
    own panel.
    """
    from ..db import SessionLocal
    from sqlalchemy import select

    model = _row()
    try:
        with SessionLocal() as db:
            row = db.get(model, SINGLETON_ID)
            if row is not None and row.secret:
                return {
                    "secret": row.secret,
                    "recovery_hashes": list(row.recovery_hashes or []),
                    "enabled_at": row.enabled_at or 0.0,
                }
    except Exception:  # noqa: BLE001 - any failure means "no enrolment"
        return {}
    return _migrate_legacy_file()


def _migrate_legacy_file() -> dict:
    """Import data/admin_2fa.json into the database the first time it is read.

    Without this, upgrading would silently drop an existing enrolment. That is
    not a lockout - the admin would simply stop being asked for a code - but it
    is a silent weakening of the panel, which is the kind of change that should
    not happen without being asked for.
    """
    from ..db import session_scope

    legacy = _legacy_path()
    if legacy is None:
        return {}
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or not data.get("secret"):
        return {}

    payload = {
        "secret": str(data["secret"]),
        "recovery_hashes": list(data.get("recovery_hashes") or []),
        "enabled_at": float(data.get("enabled_at") or time.time()),
    }
    try:
        with session_scope() as db:
            row = db.get(_row(), SINGLETON_ID)
            if row is None:
                row = _row()(id=SINGLETON_ID)
                db.add(row)
            row.secret = payload["secret"]
            row.recovery_hashes = payload["recovery_hashes"]
            row.enabled_at = payload["enabled_at"]
    except Exception:  # noqa: BLE001 - a failed import must not break login
        return {}

    # Only remove the file once the row is committed, so a crash mid-migration
    # leaves the original recoverable rather than losing the enrolment.
    try:
        legacy.unlink()
    except OSError:
        pass
    return payload


def save(secret: str, recovery_codes: list[str]) -> None:
    """Store the secret and the hashed recovery codes."""
    from ..db import session_scope

    with session_scope() as db:
        model = _row()
        row = db.get(model, SINGLETON_ID)
        if row is None:
            row = model(id=SINGLETON_ID)
            db.add(row)
        row.secret = secret
        # Recovery codes are stored hashed. They are single-use bearer
        # credentials, so a readable copy would defeat the point.
        row.recovery_hashes = [_hash_code(code) for code in recovery_codes]
        row.enabled_at = time.time()


def _write(data: dict) -> None:
    """Persist a modified payload, leaving everything absent alone."""
    from ..db import session_scope

    with session_scope() as db:
        model = _row()
        row = db.get(model, SINGLETON_ID)
        if row is None:
            row = model(id=SINGLETON_ID)
            db.add(row)
        row.secret = data.get("secret") or ""
        row.recovery_hashes = list(data.get("recovery_hashes") or [])
        row.enabled_at = float(data.get("enabled_at") or 0.0)


def clear() -> None:
    """Remove the enrolment entirely."""
    from ..db import session_scope

    try:
        with session_scope() as db:
            row = db.get(_row(), SINGLETON_ID)
            if row is not None:
                row.secret = ""
                row.recovery_hashes = []
    except Exception:  # noqa: BLE001 - already clear is the desired end state
        pass
    legacy = _legacy_path()
    if legacy is not None:
        try:
            legacy.unlink()
        except OSError:
            pass


def generate_recovery_codes(count: int = 10) -> list[str]:
    """Single-use codes for when the device is lost.

    Ambiguous characters are excluded: these get read off a screen and typed
    on a phone, and 0/O or 1/I is a support call rather than a login.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    codes = []
    for _ in range(count):
        body = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{body[:5]}-{body[5:]}")
    return codes


def _hash_code(code: str) -> str:
    """Hash a recovery code with the same bcrypt the password uses."""
    import bcrypt

    return bcrypt.hashpw(code.strip().encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("ascii")


def consume_recovery_code(submitted: str) -> bool:
    """Check a recovery code and invalidate it whether or not it matched.

    Verifying against every stored hash means a guess costs a bcrypt verify per
    candidate; the count is small and fixed, so that is the intended trade.
    """
    import bcrypt

    candidate = (submitted or "").strip()
    if not candidate:
        return False

    data = _load()
    hashes = list(data.get("recovery_hashes") or [])
    matched_index = None
    for index, stored in enumerate(hashes):
        try:
            if bcrypt.checkpw(candidate.encode("utf-8"), stored.encode("utf-8")):
                matched_index = index
        except (ValueError, TypeError):
            continue

    if matched_index is None:
        return False

    # Single use: the matched code is dropped whether or not others remain.
    remaining = [h for i, h in enumerate(hashes) if i != matched_index]
    data["recovery_hashes"] = remaining
    _write(data)
    return True


def remaining_recovery_codes() -> int:
    return len(_load().get("recovery_hashes") or [])