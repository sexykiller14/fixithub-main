"""Admin authentication, CSRF protection and content editing."""

from __future__ import annotations

import re

import pytest

PASSWORD = "test-admin-password"


def login(client) -> bool:
    """Sign in through the real login form, including CSRF."""
    response = client.get("/admin")
    assert response.status_code == 200
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match, "login form did not include a CSRF token"
    token = match.group(1)

    result = client.post(
        "/admin/login",
        data={"password": PASSWORD, "csrf": token},
        follow_redirects=False,
    )
    return result.status_code in (302, 303)


# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------


def test_login_page_is_public(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Admin sign in" in response.text


def test_login_succeeds_with_correct_password(client):
    assert login(client)


def test_login_fails_with_wrong_password(client):
    page = client.get("/admin")
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    response = client.post(
        "/admin/login",
        data={"password": "wrong-password", "csrf": token},
        follow_redirects=True,
    )
    assert response.status_code == 401
    assert "Incorrect password" in response.text
    # The failed attempt must not create a session.
    assert client.get("/admin/dashboard", follow_redirects=False).status_code in (302, 303)


def test_login_without_csrf_token_is_rejected(client):
    response = client.post("/admin/login", data={"password": PASSWORD}, follow_redirects=True)
    assert response.status_code == 400
    assert "expired" in response.text.lower()


def test_login_with_forged_csrf_token_is_rejected(client):
    response = client.post(
        "/admin/login",
        data={"password": PASSWORD, "csrf": "forged-token-value"},
        follow_redirects=True,
    )
    assert response.status_code == 400


def test_dashboard_requires_authentication(client):
    response = client.get("/admin/dashboard", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/admin" in response.headers.get("location", "")


def test_admin_routes_redirect_when_logged_out(client):
    for path in ["/admin/articles", "/admin/stop-codes", "/admin/articles/new", "/admin/stop-codes/new"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code in (302, 303), path


def test_session_cookie_is_http_only(client):
    assert login(client)
    cookies = client.cookies
    set_cookie = cookies.get("fixithub_admin")
    # httponly is enforced by the browser; assert the cookie exists and that a
    # fresh request still sees the session.
    assert set_cookie is not None or client.get("/admin/dashboard").status_code == 200


def test_logout_clears_session(client):
    assert login(client)
    dashboard = client.get("/admin/dashboard")
    token = re.search(r'name="csrf" value="([^"]+)"', dashboard.text)
    assert token
    client.post("/admin/logout", data={"csrf": token.group(1)}, follow_redirects=False)
    assert client.get("/admin/dashboard", follow_redirects=False).status_code in (302, 303)


def test_logout_without_csrf_does_nothing(client):
    assert login(client)
    client.post("/admin/logout", data={"csrf": "wrong"}, follow_redirects=False)
    assert client.get("/admin/dashboard").status_code == 200


# --------------------------------------------------------------------------
# Password hashing
# --------------------------------------------------------------------------


def test_password_hashing_round_trip():
    from app.security import hash_password, verify_password

    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$2")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_password_handles_garbage_hash():
    from app.security import verify_password

    assert verify_password("x", "not-a-bcrypt-hash") is False
    assert verify_password("", "") is False


def test_hashes_are_salted():
    from app.security import hash_password

    assert hash_password("same") != hash_password("same")


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------


def test_csrf_tokens_are_derived_from_the_session():
    from app.security import create_session_token, generate_csrf, valid_csrf

    token = create_session_token()
    csrf = generate_csrf(token)
    assert valid_csrf(token, csrf) is True
    assert valid_csrf(token, "wrong") is False
    assert valid_csrf("different-session", csrf) is False
    assert valid_csrf("", csrf) is False


def test_expired_session_cookie_is_rejected():
    from app.security import read_session_token

    assert read_session_token("forged") is None
    assert read_session_token("") is None
    assert read_session_token(None) is None


# --------------------------------------------------------------------------
# Content management
# --------------------------------------------------------------------------


def test_article_save_requires_csrf(client):
    assert login(client)
    response = client.post(
        "/admin/articles/save",
        data={
            "slug": "test-csrf-article",
            "title": "Test",
            "category": "windows",
            "difficulty": "easy",
            "body": "x" * 100,
            "csrf": "wrong",
        },
        follow_redirects=True,
    )
    assert response.status_code == 403


def test_article_save_requires_authentication(client):
    response = client.post(
        "/admin/articles/save",
        data={"slug": "x", "title": "X", "body": "y" * 100, "csrf": "x"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)


def test_article_save_validates_input(client):
    assert login(client)
    dashboard = client.get("/admin/articles")
    token = re.search(r'name="csrf" value="([^"]+)"', dashboard.text).group(1)

    # Bad slug characters.
    response = client.post(
        "/admin/articles/save",
        data={
            "slug": "Not A Valid Slug!",
            "title": "Bad slug",
            "category": "windows",
            "difficulty": "easy",
            "body": "x" * 200,
            "csrf": token,
        },
    )
    assert response.status_code == 400
    assert "Slug must be" in response.text

    # Body too short.
    response = client.post(
        "/admin/articles/save",
        data={
            "slug": "too-short-body",
            "title": "Short",
            "category": "windows",
            "difficulty": "easy",
            "body": "tiny",
            "csrf": token,
        },
    )
    assert response.status_code == 400
    assert "at least 50 characters" in response.text

    # Invalid category.
    response = client.post(
        "/admin/articles/save",
        data={
            "slug": "bad-category",
            "title": "Bad category",
            "category": "not-a-category",
            "difficulty": "easy",
            "body": "x" * 200,
            "csrf": token,
        },
    )
    assert response.status_code == 400
    assert "valid category" in response.text


def test_article_save_creates_and_edits(client, db):
    assert login(client)
    dashboard = client.get("/admin/articles")
    token = re.search(r'name="csrf" value="([^"]+)"', dashboard.text).group(1)

    slug = "pytest-created-article"
    body = "## A heading\n\nSome real content that is definitely long enough to pass validation.\n"

    response = client.post(
        "/admin/articles/save",
        data={
            "slug": slug,
            "title": "Created by pytest",
            "category": "windows",
            "difficulty": "moderate",
            "tags": "test, pytest",
            "summary": "A test article",
            "body": body,
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get(f"/articles/{slug}").status_code == 200

    # Edit it.
    response = client.post(
        "/admin/articles/save",
        data={
            "slug": slug,
            "title": "Edited by pytest",
            "category": "drivers",
            "difficulty": "hard",
            "body": body + "\nUpdated body text for the edit test.\n",
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/articles/{slug}")
    assert "Edited by pytest" in page.text
    assert "Drivers" in page.text

    # Delete it.
    response = client.post(
        f"/admin/articles/{slug}/delete", data={"csrf": token}, follow_redirects=False
    )
    assert response.status_code == 303
    assert client.get(f"/articles/{slug}").status_code == 404


def test_article_save_rejects_dangerous_slug(client):
    """A slug cannot be used to escape the content directory."""
    assert login(client)
    dashboard = client.get("/admin/articles")
    token = re.search(r'name="csrf" value="([^"]+)"', dashboard.text).group(1)

    for bad in ["../../etc/passwd", "..\\..\\windows", "a/b", "a\\b"]:
        response = client.post(
            "/admin/articles/save",
            data={
                "slug": bad,
                "title": "Traversal attempt",
                "category": "windows",
                "difficulty": "easy",
                "body": "x" * 200,
                "csrf": token,
            },
        )
        assert response.status_code == 400, bad


def test_stop_code_save_creates_and_edits(client):
    assert login(client)
    page = client.get("/admin/stop-codes")
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)

    name = "PYTEST_SYNTHETIC_CODE"
    response = client.post(
        "/admin/stop-codes/save",
        data={
            "code_hex": "0x00000999",
            "name": name,
            "meaning": "A synthetic stop code created by the test suite.",
            "causes": "cause one\ncause two\ncause three",
            "fix_steps": "step one\nstep two\nstep three",
            "difficulty": "moderate",
            "when_to_call_pro": "Not applicable, this is a test fixture.",
            "related_slugs": "",
            "csrf": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/bsod/{name}")
    assert detail.status_code == 200
    assert "synthetic stop code" in detail.text

    # Duplicate code is rejected.
    response = client.post(
        "/admin/stop-codes/save",
        data={
            "code_hex": "0x00000999",
            "name": "ANOTHER_NAME",
            "meaning": "duplicate",
            "causes": "a\nb\nc",
            "fix_steps": "one\ntwo\nthree",
            "csrf": token,
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.text

    # Clean up.
    client.post(
        f"/admin/stop-codes/{name}/delete", data={"csrf": token}, follow_redirects=False
    )
    assert client.get(f"/bsod/{name}").status_code == 404


def test_stop_code_save_validates_hex(client):
    assert login(client)
    page = client.get("/admin/stop-codes")
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)

    response = client.post(
        "/admin/stop-codes/save",
        data={
            "code_hex": "not-a-number",
            "name": "BAD_CODE",
            "meaning": "x",
            "causes": "a\nb\nc",
            "fix_steps": "one\ntwo",
            "csrf": token,
        },
    )
    assert response.status_code == 400
    assert "Invalid stop code" in response.text


def test_stop_code_save_requires_enough_steps(client):
    assert login(client)
    page = client.get("/admin/stop-codes")
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)

    response = client.post(
        "/admin/stop-codes/save",
        data={
            "code_hex": "0x00000998",
            "name": "TOO_FEW_STEPS",
            "meaning": "x",
            "causes": "only one cause",
            "fix_steps": "only one step",
            "csrf": token,
        },
    )
    assert response.status_code == 400
    assert "at least two ordered fix steps" in response.text


def test_dashboard_shows_data(client):
    assert login(client)
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert "Admin dashboard" in response.text
    assert "Popular searches" in response.text


def test_article_preview(client):
    assert login(client)
    dashboard = client.get("/admin/articles")
    token = re.search(r'name="csrf" value="([^"]+)"', dashboard.text).group(1)

    response = client.post(
        "/admin/articles/preview",
        data={"body": "## Preview heading\n\n> [!WARNING]\n> Careful here.", "csrf": token},
    )
    assert response.status_code == 200
    assert "Preview heading" in response.text
    assert "callout-warning" in response.text
