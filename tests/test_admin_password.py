"""Changing the admin password from the admin area.

The two things worth protecting are that a change cannot happen without the
current password, and that a change actually signs out the other admin sessions.
Everything else is refusing the wrong input before it reaches bcrypt.
"""

from __future__ import annotations

import re

import pytest

from app.security import (
    create_session_token,
    load_admin_hash,
    read_session_token,
    save_admin_hash,
)

NEW_PASSWORD = "a-much-longer-admin-phrase"


@pytest.fixture(autouse=True)
def restore_admin_hash():
    """Put the shared admin hash back after every test in this module.

    Changing the password rewrites the file that every other admin test signs
    in with, so without this one test would lock out the rest of the suite.

    The path is resolved inside the fixture rather than imported at module
    level. tests/conftest.py rebinds app.security.ADMIN_HASH_FILE to a fresh
    temp directory when it is imported as `tests.conftest`, which
    test_apps_routes.py and test_ask.py both do during collection. A path
    captured at import time would therefore point somewhere the app never
    writes, and this fixture would snapshot nothing and restore nothing.
    """
    import app.security as security

    path = security.ADMIN_HASH_FILE
    original = path.read_bytes() if path.is_file() else None
    yield
    if original is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(original)


def csrf_for(client) -> str:
    page = client.get("/admin/change-password")
    assert page.status_code == 200
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None, "the change-password form carried no CSRF token"
    return match.group(1)


def dashboard_csrf(client) -> str:
    page = client.get("/admin/dashboard")
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None
    return match.group(1)


def submit(client, current="test-admin-password", new=NEW_PASSWORD, confirm=NEW_PASSWORD):
    """Post the form. TestClient follows the redirect, so the response is the
    page the admin lands on, which is where the success notice lives."""
    return client.post(
        "/admin/change-password",
        data={
            "current_password": current,
            "new_password": new,
            "confirm_password": confirm,
            "csrf": csrf_for(client),
        },
    )


def test_the_page_is_reachable_from_the_admin_area(admin_client):
    page = admin_client.get("/admin/change-password")
    assert page.status_code == 200
    assert "Change password" in page.text
    # The three fields the flow needs, all masked by default.
    for name in ("current_password", "new_password", "confirm_password"):
        assert f'name="{name}"' in page.text
    assert page.text.count('type="password"') == 3


def test_the_dashboard_links_to_it(admin_client):
    assert 'href="/admin/change-password"' in admin_client.get("/admin/dashboard").text


def test_the_form_needs_a_signed_in_admin(client):
    """An unauthenticated POST must not be able to change anything."""
    before = load_admin_hash()

    response = client.post(
        "/admin/change-password",
        data={
            "current_password": "test-admin-password",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
            "csrf": "guessed",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert load_admin_hash() == before


def test_a_forged_csrf_token_changes_nothing(admin_client):
    before = load_admin_hash()

    response = admin_client.post(
        "/admin/change-password",
        data={
            "current_password": "test-admin-password",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
            "csrf": "not-the-token",
        },
    )

    assert response.status_code == 403
    assert load_admin_hash() == before


def test_a_wrong_current_password_is_refused(admin_client):
    before = load_admin_hash()

    response = submit(admin_client, current="definitely-not-it")

    assert response.status_code == 400
    assert "current password is not correct" in response.text
    assert load_admin_hash() == before


def test_a_mismatched_confirmation_is_refused(admin_client):
    before = load_admin_hash()

    response = submit(admin_client, confirm="something-else-entirely")

    assert response.status_code == 400
    assert "do not match" in response.text
    assert load_admin_hash() == before


def test_a_weak_password_is_refused(admin_client):
    before = load_admin_hash()

    response = submit(admin_client, new="short", confirm="short")

    assert response.status_code == 400
    assert "at least 10 characters" in response.text
    assert load_admin_hash() == before


def test_an_obvious_password_is_refused(admin_client):
    before = load_admin_hash()

    response = submit(admin_client, new="password123", confirm="password123")

    assert response.status_code == 400
    assert "too easy to guess" in response.text
    assert load_admin_hash() == before


def test_reusing_the_current_password_is_refused(admin_client):
    before = load_admin_hash()

    response = submit(
        admin_client, new="test-admin-password", confirm="test-admin-password"
    )

    assert response.status_code == 400
    assert "same as the current one" in response.text
    assert load_admin_hash() == before


def test_a_successful_change_then_signing_in_with_the_new_password(client):
    from app.db import get_db  # noqa: F401 - imported to prove the app boots

    # Sign in with the seeded password first, so we are a real admin session.
    login = client.get("/admin")
    login_csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', login.text).group(1)
    client.post(
        "/admin/login",
        data={"password": "test-admin-password", "csrf": login_csrf},
        follow_redirects=True,
    )
    assert client.get("/admin/dashboard").status_code == 200

    response = submit(client)
    assert "Password changed" in response.text

    # The old password no longer works.
    client.cookies.clear()
    fresh = client.get("/admin")
    fresh_csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', fresh.text).group(1)
    old = client.post(
        "/admin/login",
        data={"password": "test-admin-password", "csrf": fresh_csrf},
        follow_redirects=False,
    )
    assert old.status_code == 401  # re-renders the form with an error
    assert "Incorrect password" in old.text

    # The new one does.
    current_csrf = re.search(
        r'name="csrf"[^>]*value="([^"]+)"', client.get("/admin").text
    ).group(1)
    new_login = client.post(
        "/admin/login",
        data={"password": NEW_PASSWORD, "csrf": current_csrf},
        follow_redirects=False,
    )
    assert new_login.status_code == 303


def test_the_admin_stays_signed_in_after_the_change(client):
    login = client.get("/admin")
    login_csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', login.text).group(1)
    client.post(
        "/admin/login",
        data={"password": "test-admin-password", "csrf": login_csrf},
        follow_redirects=True,
    )

    response = submit(client)

    # A fresh cookie was issued, so the dashboard still loads.
    assert client.get("/admin/dashboard").status_code == 200
    # The submit followed the redirect to the success notice.
    assert "Password changed" in response.text
    assert "signed out" in response.text


def test_other_sessions_are_signed_out_by_the_change():
    """The cookie minted before the change must stop working."""
    stale = create_session_token()

    save_admin_hash(load_admin_hash(), password_changed_at=1.0)
    # Minted while password_changed_at was 0, so it predates this change.
    assert read_session_token(stale) is None

    fresh = create_session_token()
    assert read_session_token(fresh) is not None


def test_attempts_are_rate_limited(client):
    from app.rate_limit import password_limiter

    login = client.get("/admin")
    login_csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', login.text).group(1)
    client.post(
        "/admin/login",
        data={"password": "test-admin-password", "csrf": login_csrf},
        follow_redirects=True,
    )

    password_limiter.reset()
    statuses = []
    for _ in range(7):
        statuses.append(submit(client, current="wrong-password-here").status_code)

    assert 429 in statuses, "the change-password form was never throttled"


def test_a_pinned_environment_hash_disables_the_form(admin_client, monkeypatch):
    """An env hash wins over the saved file, so the form must say so."""
    from app.config import settings

    monkeypatch.setattr(settings, "admin_password_hash", "$2b$12$" + "x" * 53)
    before = load_admin_hash()

    page = admin_client.get("/admin/change-password")
    assert "takes priority over the saved file" in page.text
    assert 'name="new_password"' not in page.text

    response = admin_client.post(
        "/admin/change-password",
        data={
            "current_password": "test-admin-password",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
            # Taken from the dashboard: the form is correctly absent from the
            # change-password page while the hash is pinned.
            "csrf": dashboard_csrf(admin_client),
        },
    )
    assert response.status_code == 400
    assert load_admin_hash() == before


def test_no_password_is_echoed_back(admin_client):
    """A refusal must not reflect what was typed into the fields."""
    response = submit(admin_client, current="wrong-password-here")

    assert response.status_code == 400
    assert "wrong-password-here" not in response.text
    assert NEW_PASSWORD not in response.text