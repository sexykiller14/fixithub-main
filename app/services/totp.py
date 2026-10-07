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

The secret is stored beside the password hash in data/. It is base32, not
encrypted: there is no crypto library in this project's dependencies and
adding one for a single admin's TOTP secret would be a large new surface. The
file is written with owner-only permissions and is gitignored, the same
treatment data/admin.json already gets.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
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


def _path() -> Path:
    default_path = Path(DATA_DIR) / "admin_2fa.json"
    if default_path.is_file():
        return default_path
    if bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")):
        return Path("/tmp/admin_2fa.json")
    return default_path


def is_enrolled() -> bool:
    """True when a usable secret is stored."""
    return bool(_load().get("secret"))


def _load() -> dict:
    path = _path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A corrupt file is treated as "not enrolled" rather than an error, so
        # a bad write cannot lock the admin out of their own panel.
        return {}
    return data if isinstance(data, dict) else {}


def save(secret: str, recovery_codes: list[str]) -> None:
    """Store the secret and the hashed recovery codes."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "secret": secret,
        # Recovery codes are stored hashed. They are single-use bearer
        # credentials, so a readable copy on disk would defeat the point.
        "recovery_hashes": [_hash_code(code) for code in recovery_codes],
        "enabled_at": time.time(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _restrict(path)


def _restrict(path: Path) -> None:
    """Owner-only permissions where the platform supports it."""
    import os

    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows has no POSIX mode bits that mean this. The file inherits the
        # directory's ACL, which is the same guarantee admin.json gets.
        pass


def clear() -> None:
    """Remove the enrolment entirely."""
    path = _path()
    try:
        path.unlink()
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
    path = _path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _restrict(path)
    return True


def remaining_recovery_codes() -> int:
    return len(_load().get("recovery_hashes") or [])