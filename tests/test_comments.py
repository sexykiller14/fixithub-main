"""Tests for reader comments and the gated download route."""

from __future__ import annotations

import hashlib
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import USER_SESSION_COOKIE
from app.db import SessionLocal
from app.main import app
from app.models import AppDownload, Article, Comment, User
from app.services import accounts


@pytest.fixture(autouse=True)
def clean_state():
    session = SessionLocal()
    try:
        for user in session.query(User).all():
            session.query(Comment).filter(Comment.user_id == user.id).delete()
            session.delete(user)
        session.query(Comment).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        for user in session.query(User).all():
            session.query(Comment).filter(Comment.user_id == user.id).delete()
            session.delete(user)
        session.query(Comment).delete()
        session.commit()
    finally:
        session.close()


ARTICLE_SLUG = "test-ram-memory-errors"


def target_article_id() -> int:
    """The id of the article the tests comment on and read back."""
    session = SessionLocal()
    try:
        return session.scalar(select(Article).where(Article.slug == ARTICLE_SLUG)).id
    finally:
        session.close()


def csrf_from(client, path: str = "/login") -> str:
    page = client.get(path)
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None, f"no CSRF token on {path}"
    return match.group(1)


def sign_in(client, email: str, password: str = "a-long-good-phrase"):
    client.post(
        "/login",
        data={"email": email, "password": password, "csrf": csrf_from(client)},
        follow_redirects=True,
    )


def register(client, email: str = "reader@example.com", password: str = "a-long-good-phrase"):
    return client.post(
        "/signup",
        data={
            "email": email,
            "password": password,
            "confirm": password,
            "csrf": csrf_from(client, "/signup"),
        },
        follow_redirects=True,
    )


def confirm_account(email: str) -> None:
    """Flip is_verified, standing in for clicking the emailed link."""
    session = SessionLocal()
    try:
        row = session.scalar(select(User).where(User.email == email))
        row.is_verified = True
        session.commit()
    finally:
        session.close()


def make_published_app() -> AppDownload:
    """A published upload whose file really exists, so the checksum verifies."""
    from app.services.apps import store_upload

    payload = b"MZ" + b"payload for the download gating tests"
    uploaded = store_upload("gated-tool", "setup.exe", [payload])
    session = SessionLocal()
    try:
        row = session.scalar(select(AppDownload).where(AppDownload.slug == "gated-tool"))
        if row is None:
            row = AppDownload(
                slug="gated-tool",
                title="Gated Tool",
                summary="A tool used by the tests.",
                filename="gated-tool.exe",
                size_bytes=1024,
                sha256=uploaded.sha256,
                vendor="Test Vendor",
                vendor_url="https://example.com/tool",
                category="hardware",
                purpose="## When to use it\n\nTesting only.",
                is_published=True,
            )
            session.add(row)
            session.commit()
        return row
    finally:
        session.close()


# ---------------------------------------------------------------- posting


def test_signed_in_reader_can_post_a_comment(client):
    register(client)
    article_id = target_article_id()

    response = client.post(
        "/comments",
        data={
            "target_type": "article",
            "target_id": str(article_id),
            "body": "This fixed it for me, thanks.",
            "csrf": csrf_from(client, "/articles/" + ARTICLE_SLUG),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    session = SessionLocal()
    try:
        comment = session.query(Comment).one()
        assert comment.body == "This fixed it for me, thanks."
        # The whole point of moderation: nothing is public yet.
        assert comment.status == Comment.STATUS_PENDING
        assert comment.ip_hash, "the IP hash should be recorded"
    finally:
        session.close()


def test_anonymous_visitor_is_sent_to_sign_in(client):
    article_id = target_article_id()
    response = client.post(
        "/comments",
        data={
            "target_type": "article",
            "target_id": str(article_id),
            "body": "Trying to comment without an account.",
            "csrf": csrf_from(client, "/login"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/login" in response.headers["location"]

    session = SessionLocal()
    try:
        assert session.query(Comment).count() == 0
    finally:
        session.close()


def test_short_comment_is_refused(client):
    register(client)
    article_id = target_article_id()
    client.post(
        "/comments",
        data={
            "target_type": "article",
            "target_id": str(article_id),
            "body": "no",
            "csrf": csrf_from(client, "/login"),
        },
        follow_redirects=False,
    )
    session = SessionLocal()
    try:
        assert session.query(Comment).count() == 0
    finally:
        session.close()


def test_unknown_target_type_is_refused(client):
    register(client)
    response = client.post(
        "/comments",
        data={
            "target_type": "stopcode",
            "target_id": "1",
            "body": "A comment on a target type that does not exist.",
            "csrf": csrf_from(client, "/login"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    session = SessionLocal()
    try:
        assert session.query(Comment).count() == 0
    finally:
        session.close()


def test_comment_without_csrf_is_refused(client):
    register(client)
    article_id = target_article_id()
    client.post(
        "/comments",
        data={
            "target_type": "article",
            "target_id": str(article_id),
            "body": "Posting this without a CSRF token at all.",
            "csrf": "",
        },
        follow_redirects=False,
    )
    session = SessionLocal()
    try:
        assert session.query(Comment).count() == 0
    finally:
        session.close()


# ---------------------------------------------------------------- rendering


def test_pending_comment_is_not_public(client):
    """A pending comment is invisible to other readers, but its own author sees
    that it was received."""
    register(client, "author@example.com")
    article_id = target_article_id()

    session = SessionLocal()
    try:
        author = session.query(User).one()
        session.add(
            Comment(
                user_id=author.id,
                target_type="article",
                target_id=article_id,
                body="A comment awaiting approval.",
                status=Comment.STATUS_PENDING,
            )
        )
        # A second reader whose page must not show the pending comment.
        other, _ = accounts.create_user(session, "other@example.com", "a-long-good-phrase")
        other_session = accounts.start_session(session, other)
        session.commit()
        other_token = other_session.raw
    finally:
        session.close()

    # The author sees their own, clearly marked as not yet published.
    author_page = client.get("/articles/" + ARTICLE_SLUG)
    assert author_page.status_code == 200
    assert "A comment awaiting approval." in author_page.text
    assert "awaiting approval" in author_page.text

    # Another signed-in reader does not.
    other_client = TestClient(app)
    other_client.cookies.set(USER_SESSION_COOKIE, other_token)
    other_page = other_client.get("/articles/" + ARTICLE_SLUG)
    assert other_page.status_code == 200
    assert "A comment awaiting approval." not in other_page.text
    other_client.close()


def test_approved_comment_is_public(client):
    article_id = target_article_id()
    session = SessionLocal()
    try:
        user, _ = accounts.create_user(session, "public@example.com", "a-long-good-phrase")
        session.add(
            Comment(
                user_id=user.id,
                target_type="article",
                target_id=article_id,
                body="This guide solved my problem.",
                status=Comment.STATUS_APPROVED,
            )
        )
        session.commit()
    finally:
        session.close()

    page = client.get("/articles/" + ARTICLE_SLUG)
    assert page.status_code == 200
    assert "This guide solved my problem." in page.text


def test_comment_body_is_escaped_not_rendered(client):
    """A reader's words must never reach the markdown renderer."""
    article_id = target_article_id()
    session = SessionLocal()
    try:
        user, _ = accounts.create_user(session, "xss@example.com", "a-long-good-phrase")
        session.add(
            Comment(
                user_id=user.id,
                target_type="article",
                target_id=article_id,
                body="<script>alert('xss')</script><img src=x onerror=alert(1)>",
                status=Comment.STATUS_APPROVED,
            )
        )
        session.commit()
    finally:
        session.close()

    page = client.get("/articles/" + ARTICLE_SLUG)
    assert page.status_code == 200
    # No tag was created: the angle brackets are escaped, so these literal
    # strings cannot appear.
    assert "<script>alert(" not in page.text
    assert "<img" not in page.text
    # The attacker's text is shown to the reader as characters, not markup.
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in page.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in page.text


# ------------------------------------------------------------ moderation


def test_admin_can_approve_a_comment(admin_client, clean_state):
    # One client holds both cookies, which is fine: each request is exercised
    # as the actor that owns it.
    reader = admin_client
    register(reader, "mod@example.com")
    article_id = target_article_id()

    reader.post(
        "/comments",
        data={
            "target_type": "article",
            "target_id": str(article_id),
            "body": "Waiting to be approved by a moderator.",
            "csrf": csrf_from(reader, "/articles/" + ARTICLE_SLUG),
        },
        follow_redirects=False,
    )

    queue = admin_client.get("/admin/comments")
    assert queue.status_code == 200
    assert "Waiting to be approved by a moderator." in queue.text

    comment_id = SessionLocal().query(Comment).one().id
    admin_client.post(
        f"/admin/comments/{comment_id}/moderate",
        data={"csrf": csrf_from(admin_client, "/admin/comments"), "action": "approve"},
        follow_redirects=False,
    )

    session = SessionLocal()
    try:
        assert session.get(Comment, comment_id).status == Comment.STATUS_APPROVED
    finally:
        session.close()


def test_admin_can_delete_a_comment(admin_client):
    article_id = target_article_id()
    session = SessionLocal()
    try:
        user, _ = accounts.create_user(session, "del@example.com", "a-long-good-phrase")
        comment = Comment(
            user_id=user.id,
            target_type="article",
            target_id=article_id,
            body="This should be removed entirely.",
            status=Comment.STATUS_PENDING,
        )
        session.add(comment)
        session.commit()
        comment_id = comment.id
    finally:
        session.close()

    admin_client.post(
        f"/admin/comments/{comment_id}/delete",
        data={"csrf": csrf_from(admin_client, "/admin/comments")},
        follow_redirects=False,
    )
    session = SessionLocal()
    try:
        assert session.get(Comment, comment_id) is None
    finally:
        session.close()


def test_moderation_queue_needs_the_admin_session(client):
    """A reader must not be able to reach the queue."""
    register(client)
    for path in ("/admin/comments",):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"


# -------------------------------------------------------- download gating


def test_anonymous_download_redirects_to_sign_in(client):
    make_published_app()
    response = client.get("/apps/gated-tool/download", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_download_is_refused_until_the_email_is_confirmed(client):
    make_published_app()
    register(client)
    assert client.get("/account").status_code == 200

    response = client.get("/apps/gated-tool/download", follow_redirects=False)
    assert response.status_code == 303
    assert "/account" in response.headers["location"]

    # A missing file also 404s, so assert on the redirect rather than the file.
    confirm_account("reader@example.com")

    # Confirmed, so the gate is fully open and the real bytes come back.
    allowed = client.get("/apps/gated-tool/download")
    assert allowed.status_code == 200
    assert allowed.content == b"MZ" + b"payload for the download gating tests"
    assert "attachment" in allowed.headers["content-disposition"]


def test_vendor_link_stays_reachable_without_an_account(client):
    """The escape hatch for anyone the sign-in wall turns away."""
    make_published_app()
    page = client.get("/apps/gated-tool")
    assert page.status_code == 200
    assert "https://example.com/tool" in page.text
    assert "No sign-in needed" in page.text


def test_detail_page_tells_a_visitor_signing_in_is_needed(client):
    make_published_app()
    page = client.get("/apps/gated-tool")
    assert page.status_code == 200
    assert "Sign in to download" in page.text