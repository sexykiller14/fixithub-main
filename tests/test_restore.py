"""The restore endpoint used to fail on every attempt.

admin_restore built its snapshot path with pathlib.Path, but Path was only
imported inside a different function, so the handler raised NameError before it
wrote anything. A restore that cannot run is the worst kind of broken: the admin
sees a generic 500 and has no backup when they need one.

These tests drive the real endpoint with a real zip, against the temporary
database and upload directory the fixtures set up.
"""

import io
import re
import sqlite3
import zipfile

import pytest
from starlette.testclient import TestClient

from tests.conftest import make_csrf


def _backup_zip(db_path) -> bytes:
    """A zip shaped exactly like the one /admin/backup produces."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with open(db_path, "rb") as handle:
            zf.writestr("fixithub.db", handle.read())
    return buf.getvalue()


def _db_path() -> str:
    """The real on-disk path of the live database.

    engine.url.database, not str(engine.url): the string form percent-encodes
    a Windows drive letter, so the routes could only ever find the file by luck
    on POSIX. This is what made backup and restore fail here.
    """
    from app.db import engine

    return str(engine.url.database)


@pytest.mark.usefixtures("admin_client")
def test_restore_accepts_a_valid_backup(admin_client):
    """A valid archive is restored, and the success page is reached.

    This is the assertion that failed before: the handler raised NameError on
    Path(tempfile.mkdtemp(...)) and every restore 500'd.
    """
    csrf = make_csrf(admin_client)

    db_path = _db_path()
    payload = _backup_zip(db_path)

    response = admin_client.post(
        "/admin/restore",
        data={"confirm": "RESTORE", "csrf": csrf},
        files={"file": ("backup.zip", payload, "application/zip")},
        follow_redirects=True,
    )

    assert response.status_code == 200, response.text
    assert "Restore complete" in response.text, (
        "the restore did not report success; body was:\n" + response.text[:2000]
    )
    # The restored file must still be a usable database, not just present.
    restored = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in restored.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        restored.close()
    assert "articles" in tables, "the restored database is missing its tables"


@pytest.mark.usefixtures("admin_client")
def test_restore_refuses_a_wrong_confirmation(admin_client):
    """The RESTORE keyword is still required."""
    csrf = make_csrf(admin_client)
    payload = _backup_zip(_db_path())

    response = admin_client.post(
        "/admin/restore",
        data={"confirm": "yes", "csrf": csrf},
        files={"file": ("backup.zip", payload, "application/zip")},
        follow_redirects=True,
    )

    assert response.status_code in (403, 400, 200)
    assert "Restore complete" not in response.text, "a wrong confirmation still restored"


@pytest.mark.usefixtures("admin_client")
def test_restore_refuses_a_non_zip(admin_client):
    """A payload that is not a zip is rejected with a readable message."""
    csrf = make_csrf(admin_client)

    response = admin_client.post(
        "/admin/restore",
        data={"confirm": "RESTORE", "csrf": csrf},
        files={"file": ("notazip.zip", b"this is plain text", "application/zip")},
        follow_redirects=True,
    )

    assert "Restore complete" not in response.text
    assert "not a valid zip" in response.text, response.text[:2000]


@pytest.mark.usefixtures("admin_client")
def test_restore_refuses_a_zip_without_a_database(admin_client):
    """A zip that is valid but holds no database is rejected."""
    csrf = make_csrf(admin_client)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no database here")
    payload = buf.getvalue()

    response = admin_client.post(
        "/admin/restore",
        data={"confirm": "RESTORE", "csrf": csrf},
        files={"file": ("backup.zip", payload, "application/zip")},
        follow_redirects=True,
    )

    assert "Restore complete" not in response.text
    assert "does not contain a database" in response.text, response.text[:2000]


@pytest.mark.usefixtures("admin_client")
def test_restore_offers_a_downloadable_snapshot(admin_client):
    """The pre-restore snapshot must be reachable, not just written.

    The handler takes a snapshot before it replaces the database. If the admin
    cannot get that file back, the safety net is theoretical: the only copy of
    the pre-restore state is in a temp directory they cannot browse.
    """
    csrf = make_csrf(admin_client)
    payload = _backup_zip(_db_path())

    done = admin_client.post(
        "/admin/restore",
        data={"confirm": "RESTORE", "csrf": csrf},
        files={"file": ("backup.zip", payload, "application/zip")},
        follow_redirects=True,
    )
    assert "Restore complete" in done.text, done.text[:2000]

    href = re.search(r'href="(/admin/restore/snapshot/[^"]+)"', done.text)
    assert href is not None, "the success page offered no snapshot download"
    target = href.group(1)

    fetched = admin_client.get(target)
    assert fetched.status_code == 200, f"{target} returned {fetched.status_code}"
    # It really is the backup format, so it can be restored again.
    archive = zipfile.ZipFile(io.BytesIO(fetched.content))
    assert "fixithub.db" in archive.namelist()


@pytest.mark.usefixtures("admin_client")
def test_snapshot_route_refuses_a_traversal_name(admin_client):
    """The snapshot route matches a fixed pattern, so .. never resolves.

    The literal ".." has to be percent-encoded: an HTTP client normalises a
    plain "../" in the path away before the request is ever sent, so the test
    would be exercising the client rather than the route.
    """
    from app.routes.admin import admin_restore_snapshot  # noqa: F401

    for target in (
        "/admin/restore/snapshot/%2e%2e",
        "/admin/restore/snapshot/..%2f..%2fwindows",
        "/admin/restore/snapshot/not-a-snapshot-dir",
    ):
        response = admin_client.get(target)
        # 404 from the router (the segment never matched the path parameter) or
        # 403 from the pattern check. Both refuse; neither serves a file.
        assert response.status_code in (403, 404), f"{target} returned {response.status_code}"
        assert "attachment" not in response.headers.get("content-disposition", "")

    # An unauthenticated visitor must be sent to the login page. The test
    # client follows redirects by default, so the landing page being 200 is
    # correct; what matters is that it is the login form and not a file.
    anon = TestClient(admin_client.app)
    anonymous = anon.get("/admin/restore/snapshot/fixithub-restore-snapshot-abc123")
    assert anonymous.status_code == 200, anonymous.status_code
    assert "attachment" not in anonymous.headers.get("content-disposition", "")
    assert 'name="password"' in anonymous.text, "expected the admin login form"

    # And the same with redirects off, to see the actual status.
    strict = anon.get(
        "/admin/restore/snapshot/fixithub-restore-snapshot-abc123",
        follow_redirects=False,
    )
    assert strict.status_code in (303, 307), strict.status_code


@pytest.mark.usefixtures("admin_client")
def test_restore_does_not_roll_the_admin_password_back(admin_client):
    """admin.json in the archive must not overwrite the live password hash.

    A backup taken before a password change carries the old hash. Restoring it
    would both revert the password and invalidate every current session cookie,
    locking the admin out of the panel they are in the middle of using.
    """
    from app.config import ADMIN_HASH_FILE
    from app.security import load_admin_hash

    before = load_admin_hash()
    assert before, "the test environment has no admin hash to compare against"

    csrf = make_csrf(admin_client)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        with open(_db_path(), "rb") as handle:
            zf.writestr("fixithub.db", handle.read())
        zf.writestr("admin.json", b'{"password_hash": "$2b$12$definitelynotarealhash0000000000000000000000000000000000"}')

    response = admin_client.post(
        "/admin/restore",
        data={"confirm": "RESTORE", "csrf": csrf},
        files={"file": ("backup.zip", buf.getvalue(), "application/zip")},
        follow_redirects=True,
    )
    assert "Restore complete" in response.text, response.text[:2000]

    assert load_admin_hash() == before, "the restore replaced the admin password hash"
    assert ADMIN_HASH_FILE.is_file()