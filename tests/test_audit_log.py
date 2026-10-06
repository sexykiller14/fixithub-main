"""The admin audit log.

The table exists so that "what happened in the panel" is answerable after the
fact. That only works if two things hold: writes are actually recorded, and
nothing sensitive is ever recorded. Both are tested here, because a log that
quietly skips a route is worse than no log - it looks like evidence.
"""

import re

import pytest
from sqlalchemy import select

from app.models import AdminAuditLog
from app.services import audit


@pytest.fixture(autouse=True)
def clear_log(db):
    """Empty the log before each test in this file.

    The prepared database is session-scoped and other test files write to the
    same table - signing in is itself an audited action - so a test that
    inspects "the first row" would otherwise see another test's row.
    """
    db.query(AdminAuditLog).delete()
    db.commit()
    yield
    db.rollback()


def _fresh(db):
    """The test session's rows, committed by the app's own session.

    The app writes through a separate session from get_db, so this session may
    still be holding a read transaction from the delete above and would not see
    those commits. Ending it first is what makes the row visible.
    """
    db.rollback()
    return db


@pytest.mark.usefixtures("admin_client")
def test_signing_in_is_recorded(admin_client, db):
    """The login that just happened in the admin_client fixture."""
    rows = audit.recent(_fresh(db), limit=50, action="auth.login")
    assert rows, "a successful sign-in was not recorded"
    assert rows[0].detail, "the row carries no detail"


def test_a_wrong_password_is_recorded(client, db):
    # Deliberately NOT using admin_client: this test needs an anonymous client,
    # and a signed-in one is redirected away from the login form.
    from app.security import clear_login_failures, login_locked_out

    # Other tests in the suite deliberately fail the login, and the lockout is
    # keyed on the same client address. A locked-out attempt short-circuits
    # before the password is ever checked, so clear it first.
    clear_login_failures("ece")
    assert login_locked_out("ece")[0] is False

    page = client.get("/admin")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"password": "definitely-not-it", "csrf": token},
        follow_redirects=True,
    )
    assert "Incorrect password" in response.text, (
        f"the login did not report a wrong password; status={response.status_code}"
    )

    rows = audit.recent(_fresh(db), limit=50, action="auth.login_failed")
    assert rows, "a failed sign-in attempt was not recorded"


@pytest.mark.usefixtures("admin_client")
def test_the_audit_page_is_readable_by_an_admin(admin_client):
    response = admin_client.get("/admin/audit")
    assert response.status_code == 200
    assert "Audit log" in response.text


def test_the_audit_page_needs_a_login(client):
    response = client.get("/admin/audit", follow_redirects=False)
    assert response.status_code in (303, 307), response.status_code


@pytest.mark.usefixtures("admin_client")
def test_moderating_a_comment_is_recorded(admin_client, db):
    """Comment approval is the highest-traffic write in the panel."""
    from app.models import Comment, User
    from app.security import hash_password

    user = User(
        email="audittest@example.com",
        email_normalised="audittest@example.com",
        password_hash=hash_password("x" * 12),
        is_verified=True,
    )
    db.add(user)
    db.flush()
    comment = Comment(
        user_id=user.id,
        target_type="article",
        target_id=1,
        body="A comment to moderate.",
        status=Comment.STATUS_PENDING,
    )
    db.add(comment)
    db.commit()
    comment_id = comment.id

    csrf = re.search(
        r'name="csrf"[^>]*value="([^"]+)"',
        admin_client.get("/admin/comments").text,
    ).group(1)
    response = admin_client.post(
        f"/admin/comments/{comment_id}/moderate",
        data={"action": "approve", "csrf": csrf},
        follow_redirects=False,
    )
    assert response.status_code == 303

    rows = audit.recent(_fresh(db), limit=10, action="comment.approve")
    assert rows, "approving a comment wrote no audit row"
    assert str(comment_id) in rows[0].target_id


# --------------------------------------------------------------------------
# What must never be recorded
# --------------------------------------------------------------------------


def test_an_unknown_action_is_refused(db):
    """A typo in a caller must not create an ungroupable row."""
    assert audit.record(db, "not.a.real.action") is None
    assert db.scalar(select(AdminAuditLog).limit(1)) is None


def test_a_detail_string_is_clamped(db):
    audit.record(db, "article.save", detail="x" * 5000)
    row = db.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "article.save"))
    assert len(row.detail) <= audit.MAX_DETAIL


def test_a_detail_with_newlines_is_flattened(db):
    """One row is one line, so a multi-line detail cannot fake a table row."""
    audit.record(db, "article.save", detail="first\nsecond\r\nthird")
    row = db.scalar(select(AdminAuditLog).where(AdminAuditLog.action == "article.save"))
    assert "\n" not in row.detail
    assert "first second third" in row.detail


def test_addresses_are_stored_hashed(db):
    """The log must not become a list of visitor addresses."""
    digest = audit.hash_ip("203.0.113.9")
    assert "203.0.113.9" not in digest
    assert len(digest) == 32
    # Stable, so one client can still be recognised across rows.
    assert audit.hash_ip("203.0.113.9") == digest
    # Different addresses give different digests.
    assert audit.hash_ip("203.0.113.10") != digest


def test_ip_hashes_are_salted_by_the_secret_key():
    """Unsalted, the whole IPv4 space could be brute-forced offline."""
    a = audit.hash_ip("198.51.100.1")
    b = audit.hash_ip("198.51.100.1")
    assert a == b  # stable within a deployment
    # The salt is what makes it not a plain digest; check it depends on the key.
    from app.config import settings

    original = settings.secret_key
    try:
        settings.secret_key = "a-different-secret"
        assert audit.hash_ip("198.51.100.1") != a
    finally:
        settings.secret_key = original


def test_counts_group_by_action(db):
    audit.record(db, "article.save")
    audit.record(db, "article.save")
    audit.record(db, "comment.approve")
    counts = audit.counts_by_action(db)
    assert counts.get("article.save") == 2
    assert counts.get("comment.approve") == 1


def test_an_unknown_filter_is_ignored(admin_client):
    """A bogus action in the query string must not render as a live filter."""
    bogus = admin_client.get("/admin/audit?action=bogus.action")
    assert bogus.status_code == 200
    assert "bogus.action" not in bogus.text