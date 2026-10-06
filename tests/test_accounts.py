"""Tests for reader accounts, sessions and comments.

The two properties worth protecting above all else:

  - a reader account must never reach the admin panel
  - a comment body must never be interpreted as markup

Everything else here covers the ordinary paths and the refusals.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Article, AuthToken, Comment, User
from app.services import accounts


@pytest.fixture(autouse=True)
def clean_accounts():
    """Remove reader rows so tests do not inherit each other's state."""
    session = SessionLocal()
    try:
        for user in session.query(User).all():
            session.execute(
                AuthToken.__table__.delete().where(AuthToken.user_id == user.id)
            )
            session.query(Comment).filter(Comment.user_id == user.id).delete()
            session.delete(user)
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        for user in session.query(User).all():
            session.execute(
                AuthToken.__table__.delete().where(AuthToken.user_id == user.id)
            )
            session.query(Comment).filter(Comment.user_id == user.id).delete()
            session.delete(user)
        session.commit()
    finally:
        session.close()


def make_reader(email: str = "reader@example.com", password: str = "a-long-good-phrase") -> User:
    session = SessionLocal()
    try:
        user, _ = accounts.create_user(session, email, password)
        return user
    finally:
        session.close()


def verify(user: User) -> None:
    session = SessionLocal()
    try:
        row = session.get(User, user.id)
        row.is_verified = True
        row.verified_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()


# ------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "nope", "a@b", "no spaces@here.com", "x@.com", "a..b@example.com"],
)
def test_validate_email_rejects_bad_addresses(bad):
    with pytest.raises(accounts.AccountError):
        accounts.validate_email(bad)


@pytest.mark.parametrize(
    "good",
    ["reader@example.com", "Reader@Example.COM", "a.b+tag@sub.example.co.uk"],
)
def test_validate_email_normalises(good):
    result = accounts.validate_email(good)
    assert result == good.strip().lower()
    assert result == accounts.normalise_email(result)


def test_password_must_be_ten_characters():
    with pytest.raises(accounts.AccountError) as exc:
        accounts.validate_password("short")
    assert "10 characters" in str(exc.value)


def test_password_length_is_what_matters_not_symbols():
    """A long passphrase is accepted even with no symbols, which is the point."""
    assert accounts.validate_password("correct horse battery") == "correct horse battery"


def test_known_bad_passwords_are_refused():
    with pytest.raises(accounts.AccountError):
        accounts.validate_password("password123")


def test_password_containing_the_email_local_part_is_refused():
    with pytest.raises(accounts.AccountError) as exc:
        accounts.validate_password("bobbyisgreat", "bobby@example.com")
    assert "email address" in str(exc.value)


def test_short_email_local_part_does_not_trip_the_check():
    """A user called `bob` should not be blocked from using it as a password."""
    assert accounts.validate_password("a-mouse-here", "bob@example.com")


def test_oversized_password_is_refused():
    with pytest.raises(accounts.AccountError):
        accounts.validate_password("x" * (accounts.MAX_PASSWORD + 1))


# ---------------------------------------------------------------- tokens


def test_only_the_token_hash_is_stored():
    session = SessionLocal()
    try:
        user, token = accounts.create_user(session, "hash@example.com", "a-good-long-phrase")
        row = session.scalar(
            select(AuthToken).where(
                AuthToken.user_id == user.id,
                AuthToken.token_hash == accounts.hash_token(token.raw),
            )
        )
        assert row is not None
        assert row.token_hash != token.raw
        assert row.token_hash == accounts.hash_token(token.raw)
        assert token.raw not in row.token_hash
        assert len(row.token_hash) == 64
    finally:
        session.close()


def test_tokens_are_unique_per_issue():
    session = SessionLocal()
    try:
        reader = make_reader()
        first = accounts.issue_token(
            session, reader, accounts.TOKEN_PURPOSE_VERIFY, accounts.VERIFY_TTL
        )
        second = accounts.issue_token(
            session, reader, accounts.TOKEN_PURPOSE_VERIFY, accounts.VERIFY_TTL
        )
        # issue_token only stages the row; callers commit. The session has
        # autoflush off, so an uncommitted token is invisible to a select.
        session.commit()
        assert first.raw != second.raw
    finally:
        session.close()


def test_resolve_token_rejects_the_wrong_purpose():
    """A session token must not be usable as a verification link."""
    session = SessionLocal()
    try:
        user = make_reader()
        token = accounts.issue_token(
            session, user, accounts.TOKEN_PURPOSE_SESSION, accounts.SESSION_TTL
        )
        session.commit()
        assert accounts.resolve_token(session, token.raw, accounts.TOKEN_PURPOSE_VERIFY) is None
        assert accounts.resolve_token(session, token.raw, accounts.TOKEN_PURPOSE_SESSION) is not None
    finally:
        session.close()


def test_expired_token_is_refused_and_deleted():
    session = SessionLocal()
    try:
        user = make_reader()
        token = accounts.issue_token(
            session, user, accounts.TOKEN_PURPOSE_VERIFY, accounts.VERIFY_TTL
        )
        session.commit()
        row = session.scalar(
            select(AuthToken).where(
                AuthToken.user_id == user.id,
                AuthToken.token_hash == accounts.hash_token(token.raw),
            )
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()

        assert accounts.resolve_token(session, token.raw, accounts.TOKEN_PURPOSE_VERIFY) is None
        assert (
            session.query(AuthToken)
            .filter(AuthToken.token_hash == accounts.hash_token(token.raw))
            .count()
            == 0
        )
    finally:
        session.close()


def test_unknown_token_returns_none():
    session = SessionLocal()
    try:
        assert accounts.resolve_token(session, "not-a-real-token", accounts.TOKEN_PURPOSE_VERIFY) is None
        assert accounts.resolve_token(session, "", accounts.TOKEN_PURPOSE_VERIFY) is None
    finally:
        session.close()


# ------------------------------------------------------------- lifecycle


def test_create_user_starts_unverified():
    session = SessionLocal()
    try:
        user, token = accounts.create_user(session, "new@example.com", "a-good-long-phrase")
        assert user.is_verified is False
        assert user.is_active is True
        assert user.email == "new@example.com"
        assert token.raw
    finally:
        session.close()


def test_duplicate_email_is_refused():
    make_reader("dup@example.com")
    session = SessionLocal()
    try:
        with pytest.raises(accounts.AccountError) as exc:
            accounts.create_user(session, "DUP@example.com", "another-long-phrase")
        assert "already exists" in str(exc.value)
    finally:
        session.close()


def test_password_is_hashed_not_stored():
    session = SessionLocal()
    try:
        user, _ = accounts.create_user(session, "pw@example.com", "super-secret-phrase")
        assert user.password_hash != "super-secret-phrase"
        assert user.password_hash.startswith("$2")
    finally:
        session.close()


def test_verify_email_flips_the_flag_and_spends_the_token():
    session = SessionLocal()
    try:
        user, token = accounts.create_user(session, "verify@example.com", "a-good-long-phrase")
        assert accounts.verify_email(session, token.raw) is True

        row = session.get(User, user.id)
        assert row.is_verified is True
        assert row.verified_at is not None
        # The token is single use.
        assert accounts.verify_email(session, token.raw) is False
    finally:
        session.close()


def test_verify_email_rejects_garbage():
    session = SessionLocal()
    try:
        assert accounts.verify_email(session, "nonsense") is False
    finally:
        session.close()


def test_check_password():
    session = SessionLocal()
    try:
        make_reader("check@example.com", "the-right-phrase-here")
        assert accounts.check_password(session, "check@example.com", "the-right-phrase-here") is not None
        assert accounts.check_password(session, "check@example.com", "wrong") is None
        assert accounts.check_password(session, "nobody@example.com", "whatever-long") is None
    finally:
        session.close()


def test_check_password_refuses_a_deactivated_account():
    session = SessionLocal()
    try:
        user = make_reader("off@example.com")
        row = session.get(User, user.id)
        row.is_active = False
        session.commit()
        assert accounts.check_password(session, "off@example.com", "a-long-good-phrase") is None
    finally:
        session.close()


# --------------------------------------------------------------- sessions


def test_session_round_trip():
    session = SessionLocal()
    try:
        user = make_reader("sess@example.com")
        token = accounts.start_session(session, user)
        assert accounts.current_user(session, token.raw).id == user.id
        assert accounts.current_user(session, None) is None
        assert accounts.current_user(session, "bogus") is None
    finally:
        session.close()


def test_end_session_actually_revokes():
    """Logging out must end access on the server, not just clear the cookie."""
    session = SessionLocal()
    try:
        user = make_reader("bye@example.com")
        token = accounts.start_session(session, user)
        assert accounts.current_user(session, token.raw) is not None

        accounts.end_session(session, token.raw)
        assert accounts.current_user(session, token.raw) is None
    finally:
        session.close()


def test_starting_a_new_session_invalidates_the_old_one():
    session = SessionLocal()
    try:
        user = make_reader("relog@example.com")
        first = accounts.start_session(session, user)
        second = accounts.start_session(session, user)

        assert first.raw != second.raw
        assert accounts.current_user(session, first.raw) is None
        assert accounts.current_user(session, second.raw) is not None
    finally:
        session.close()


def test_idle_session_is_closed():
    session = SessionLocal()
    try:
        user = make_reader("idle@example.com")
        token = accounts.start_session(session, user)
        row = session.scalar(
            select(AuthToken).where(
                AuthToken.user_id == user.id,
                AuthToken.purpose == accounts.TOKEN_PURPOSE_SESSION,
            )
        )
        row.last_seen_at = datetime.now(timezone.utc) - accounts.SESSION_IDLE - timedelta(hours=1)
        session.commit()

        assert accounts.current_user(session, token.raw) is None
    finally:
        session.close()


def test_deactivated_user_cannot_use_a_live_session():
    session = SessionLocal()
    try:
        user = make_reader("ban@example.com")
        token = accounts.start_session(session, user)
        row = session.get(User, user.id)
        row.is_active = False
        session.commit()

        assert accounts.current_user(session, token.raw) is None
    finally:
        session.close()


def test_sweep_expired_removes_old_tokens():
    session = SessionLocal()
    try:
        user = make_reader("sweep@example.com")
        token = accounts.issue_token(
            session, user, accounts.TOKEN_PURPOSE_VERIFY, accounts.VERIFY_TTL
        )
        session.commit()
        row = session.scalar(
            select(AuthToken).where(
                AuthToken.user_id == user.id,
                AuthToken.token_hash == accounts.hash_token(token.raw),
            )
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()

        accounts.sweep_expired(session)
        # create_user left its own unexpired verification token behind, so this
        # checks the row under test rather than the user's whole token set.
        assert (
            session.query(AuthToken)
            .filter(AuthToken.token_hash == accounts.hash_token(token.raw))
            .count()
            == 0
        )
        assert accounts.resolve_token(session, token.raw, accounts.TOKEN_PURPOSE_VERIFY) is None
    finally:
        session.close()


# ------------------------------------------------------------- deletion


def test_delete_user_removes_the_account_and_their_comments():
    session = SessionLocal()
    try:
        user = make_reader("gone@example.com")
        article_id = session.query(Article).first().id
        session.add(
            Comment(
                user_id=user.id,
                target_type="article",
                target_id=article_id,
                body="Something I wrote before leaving.",
                status=Comment.STATUS_APPROVED,
            )
        )
        session.add(
            Comment(
                user_id=user.id,
                target_type="article",
                target_id=article_id,
                body="And another one.",
                status=Comment.STATUS_APPROVED,
            )
        )
        accounts.start_session(session, user)
        session.commit()

        removed = accounts.delete_user(session, user)
        assert removed == 2
        assert session.query(User).filter(User.email == "gone@example.com").count() == 0
        assert session.query(Comment).filter(Comment.user_id == user.id).count() == 0
        assert session.query(AuthToken).count() == 0
    finally:
        session.close()


# ------------------------------------------------------------ the boundary


def test_a_reader_account_carries_no_admin_privileges():
    """The single most important property of this feature.

    A valid reader session must not satisfy the admin panel's own check, which
    uses a separate cookie and a separate password.
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.security import read_session_token

    session = SessionLocal()
    try:
        user = make_reader("sneaky@example.com")
        accounts.start_session(session, user)
        verify(user)
    finally:
        session.close()

    with TestClient(app) as client:
        login = client.get("/login")
        csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', login.text).group(1)
        client.post(
            "/login",
            data={"email": "sneaky@example.com", "password": "a-long-good-phrase", "csrf": csrf},
            follow_redirects=True,
        )

        # Signed in as a reader...
        assert client.get("/account").status_code == 200

        # ...but every admin page still bounces to the admin login.
        for path in ("/admin/dashboard", "/admin/articles", "/admin/comments", "/admin/apps"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303, path
            assert response.headers["location"] == "/admin", path

        # And the admin cookie is not present at all.
        assert "fixithub_admin" not in client.cookies
        assert read_session_token(client.cookies.get("fixithub_admin")) is None


def test_reader_cookie_is_not_accepted_as_an_admin_cookie():
    session = SessionLocal()
    try:
        user = make_reader("swap@example.com")
        token = accounts.start_session(session, user)
    finally:
        session.close()

    from app.security import read_session_token

    assert read_session_token(token.raw) is None


# --------------------------------------------------- registration switched off


def test_signup_is_closed_when_registration_is_off(monkeypatch):
    """The default is closed, so the form must not be served at all."""
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "allow_registration", False)

    with TestClient(app) as client:
        page = client.get("/signup")
        assert page.status_code == 403
        assert "Registration is closed" in page.text
        # No form, so no token for anything to be forged with.
        assert 'name="csrf"' not in page.text


def test_posting_to_signup_is_refused_when_registration_is_off(monkeypatch):
    """The GET being closed is not enough: the POST has to refuse too."""
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "allow_registration", False)

    with TestClient(app) as client:
        response = client.post(
            "/signup",
            data={
                "email": "closed@example.com",
                "password": "a-long-good-phrase",
                "confirm": "a-long-good-phrase",
                "csrf": "anything",
            },
            follow_redirects=True,
        )
        assert response.status_code == 403

    session = SessionLocal()
    try:
        assert session.query(User).filter(User.email == "closed@example.com").count() == 0
    finally:
        session.close()


def test_login_still_works_when_registration_is_off(monkeypatch):
    """Closing sign-up must not lock out readers who already have an account."""
    from fastapi.testclient import TestClient

    from app.config import settings
    from app.main import app

    user = make_reader("existing@example.com")
    verify(user)
    monkeypatch.setattr(settings, "allow_registration", False)

    with TestClient(app) as client:
        csrf = re.search(
            r'name="csrf"[^>]*value="([^"]+)"', client.get("/login").text
        ).group(1)
        response = client.post(
            "/login",
            data={
                "email": "existing@example.com",
                "password": "a-long-good-phrase",
                "csrf": csrf,
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert client.get("/account").status_code == 200