"""Shared pytest fixtures.

Every test runs against a temporary SQLite database and a temporary admin hash
file, so nothing touches the developer's real data.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Point the app at a scratch database before any app module is imported.
_TMP = tempfile.mkdtemp(prefix="fixithub-tests-")
os.environ["FIXITHUB_DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["FIXITHUB_SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["FIXITHUB_ADMIN_PASSWORD"] = "correct-horse-battery-staple"
# Registration is off by default, but the comment and download-gating tests
# sign a reader up through the real form, so it has to be on for them.
os.environ["FIXITHUB_ALLOW_REGISTRATION"] = "1"
os.environ["FIXITHUB_RATE_LIMIT_MAX"] = "10"
os.environ["FIXITHUB_RATE_LIMIT_WINDOW"] = "60"
# Uploads must never land in the project's apps_download directory during a
# test run, so point them at the same scratch directory as the database.
os.environ["FIXITHUB_APPS_DIR"] = str(Path(_TMP) / "apps")

from app import config as app_config  # noqa: E402
from app.db import create_all, engine, search, session_scope  # noqa: E402
from app.models import Article, StopCode  # noqa: E402
from app.security import hash_password, save_admin_hash  # noqa: E402
from app.services.content import load_all_articles, render_article  # noqa: E402
from app.services.stopcodes import load_stop_codes_file, sync_stop_codes  # noqa: E402

# Keep the admin hash out of the project's data directory, so running the tests
# never overwrites the password you set for your own instance.
app_config.ADMIN_HASH_FILE = Path(_TMP) / "admin.json"
import app.security as _security  # noqa: E402

_security.ADMIN_HASH_FILE = app_config.ADMIN_HASH_FILE


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    """Create the schema, load real content and set the test admin password."""
    create_all()

    with session_scope() as db:
        sync_stop_codes(db, load_stop_codes_file())
        for source in load_all_articles():
            rendered = render_article(source.body)
            db.add(
                Article(
                    slug=source.slug,
                    title=source.title,
                    category=source.category,
                    tags=source.tags,
                    difficulty=source.difficulty,
                    os_version=source.os_version,
                    summary=source.summary,
                    body=source.body,
                    reading_time=rendered.reading_time,
                    source_path=source.source_path,
                    is_featured=source.featured,
                )
            )
    search.rebuild()

    # A known admin password for the admin tests.
    save_admin_hash(hash_password("test-admin-password"))

    yield

    engine.dispose()


@pytest.fixture
def db():
    """A session with any test-created rows rolled back at the end."""
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client():
    """A TestClient, with rate limiters reset between tests."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.rate_limit import (
        ask_limiter,
        ask_poll_limiter,
        feedback_limiter,
        login_limiter,
        password_limiter,
        tool_limiter,
    )
    from app.routes.accounts import signin_limiter, signup_limiter
    from app.routes.comments import comment_limiter
    from app.security import clear_login_failures

    # Every limiter has to be reset, not just the original three. The account
    # and comment buckets are module-level like the others, so a test that
    # exhausts one leaks that exhaustion into later tests.
    for limiter in (
        tool_limiter,
        login_limiter,
        feedback_limiter,
        ask_limiter,
        ask_poll_limiter,
        password_limiter,
        signin_limiter,
        signup_limiter,
        comment_limiter,
    ):
        limiter.reset()

    # The login lockout is separate state from the sliding-window limiters: it
    # is a dict of failed attempts keyed by the same identifier admin_login uses.
    # A test that deliberately signs in with the wrong password would otherwise
    # lock the admin out of every later test in the session.
    #
    # The key is what security.client_ip() returns for a TestClient request,
    # not the raw request.client.host: client_ip sanitises the address down to
    # the characters an IP can contain, and the test host name "testclient"
    # does not survive that intact. Deriving the key the same way the route
    # does is the only way to be sure it matches.
    for key in _test_client_ip_keys():
        clear_login_failures(key)

    with TestClient(app) as test_client:
        yield test_client


def _test_client_ip_keys() -> list[str]:
    """Every key admin_login could record a failure under in the test suite.

    security.client_ip() sanitises an address down to the characters an IP can
    contain, so the TestClient host "testclient" does not survive that intact
    and the key the route uses is not the host string. Rather than hardcode the
    mangled result, run the same sanitiser over the same input the route uses.
    """
    from app.security import _sanitise_ip

    return ["testclient", _sanitise_ip("testclient"), "unknown"]


@pytest.fixture
def admin_client(client):
    """A logged-in TestClient, plus the CSRF token its forms expect."""
    import re

    page = client.get("/admin")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert csrf is not None, "login form did not carry a CSRF token"

    response = client.post(
        "/admin/login",
        data={"password": "test-admin-password", "csrf": csrf.group(1)},
        follow_redirects=True,
    )
    assert response.status_code == 200

    client.headers.update({"x-test-csrf": csrf.group(1)})
    return client


@pytest.fixture(autouse=True)
def clear_two_factor_enrolment():
    """Empty the admin TOTP row before every test.

    The enrolment moved from a file in a per-test temporary directory to a
    single database row, and the prepared database is session-scoped. Without
    this, one test's enrolment would satisfy the next one's assertion that
    nothing is enrolled, and a test that disables two-factor would silently
    change the state a later test depends on.
    """
    from app.db import session_scope
    from app.models import AdminTwoFactor

    with session_scope() as db:
        row = db.get(AdminTwoFactor, 1)
        if row is not None:
            row.secret = ""
            row.recovery_hashes = []
            row.enabled_at = 0.0
    yield


def make_csrf(client) -> str:
    """Read a CSRF token out of the current admin session's page."""
    import re

    page = client.get("/admin/dashboard")
    assert page.status_code == 200
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None, "admin page did not carry a CSRF token"
    return match.group(1)


def fake_exe(marker: bytes = b"MZ") -> bytes:
    """Bytes that pass the executable magic check."""
    return marker + b"\x00" * 512 + b"fixithub-test-upload"


def fake_png() -> bytes:
    """Bytes that pass the PNG magic check.

    The body is not a real image. Nothing in the app decodes an uploaded
    screenshot, it is stored and served as-is, so a header is all the check
    ever looks at.
    """
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 64 + b"fixithub-test-image"


def fake_jpeg() -> bytes:
    """Bytes that pass the JPEG magic check (SOI marker)."""
    return b"\xff\xd8\xff" + b"\x00" * 64 + b"fixithub-test-image"


def fake_webp() -> bytes:
    """Bytes that pass the WebP magic check: RIFF size, then the WEBP tag."""
    return b"RIFF" + (32).to_bytes(4, "little") + b"WEBP" + b"\x00" * 64


@pytest.fixture
def sample_dump():
    """A minimal synthetic PMDMP buffer for the minidump tests.

    Laid out like a real minidump: a 32-byte header whose first four bytes are
    the ``PMDMP`` signature, one directory entry, then the bugcheck stream.
    """
    import struct

    bugcheck_code = 0x0000001A
    parameters = [0x2, 0x1234ABCD, 0x0, 0x0]

    # MINIDUMP_HEADER, 32 bytes.
    header = b"PMDM"
    header += b"P"                       # version low byte, which completes "PMDMP"
    header += b"\x00\x00\x00"
    header += struct.pack("<I", 1)       # number of streams
    header += struct.pack("<I", 32)      # RVA of the stream directory
    header += struct.pack("<I", 0)       # checksum
    header += struct.pack("<I", 0)       # timestamp
    header += struct.pack("<Q", 0)       # flags
    assert len(header) == 32

    # Stream type 16 is BugCheckStream: a 32-bit code then four 64-bit params.
    directory = struct.pack("<III", 16, 4 + 8 * 4, 32 + 12)

    stream = struct.pack("<I", bugcheck_code)
    for value in parameters:
        stream += struct.pack("<Q", value)

    return header + directory + stream
