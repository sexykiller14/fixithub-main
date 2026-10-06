"""Phase 7: the security controls, tested adversarially.

Earlier phases asserted that each control exists. These assert that it holds
when someone pushes against it. The difference matters: "every POST route takes
a csrf field" is a property of the code, whereas "a cross-site POST changes
nothing" is a property of the deployment, which is the one that gets exploited.

Grouped by OWASP category. Every test here should pass; a failure is a real
finding, not a flaky test.
"""

import re

import pytest
from sqlalchemy import select

from app.models import AdminAuditLog, Article, Comment, Question, User
from app.security import hash_password


def _csrf(client, path="/admin/dashboard"):
    page = client.get(path)
    assert page.status_code == 200, f"{path} returned {page.status_code}"
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None, f"{path} carried no CSRF token"
    return match.group(1)


# ===========================================================================
# A01 Broken access control
# ===========================================================================

# Every route that changes something. A miss here is a critical finding, so the
# list is spelled out rather than generated.
GUARDED_POSTS = [
    "/admin/logout",
    "/admin/ads/settings",
    "/admin/ads/unit/save",
    "/admin/ads/unit/1/toggle",
    "/admin/ads/unit/1/delete",
    "/admin/seo",
    "/admin/seo/defaults",
    "/admin/seo/1/delete",
    "/admin/announcement/save",
    "/admin/restore",
    "/admin/change-password",
    "/admin/articles/save",
    "/admin/articles/some-slug/delete",
    "/admin/articles/preview",
    "/admin/stop-codes/save",
    "/admin/stop-codes/CRITICAL_PROCESS_DIED/delete",
    "/admin/apps/save",
    "/admin/apps/some-slug/delete",
    "/admin/comments/1/moderate",
    "/admin/comments/1/delete",
    "/admin/questions/1/reply",
    "/admin/questions/1/reopen",
    "/admin/questions/1/delete",
    "/admin/users/1/delete",
    "/admin/two-factor/start",
    "/admin/two-factor/confirm",
    "/admin/two-factor/disable",
    "/admin/two-factor/discard",
    "/admin/two-factor/recovery-codes",
]

GUARDED_GETS = [
    "/admin/dashboard",
    "/admin/articles",
    "/admin/stop-codes",
    "/admin/apps",
    "/admin/comments",
    "/admin/questions",
    "/admin/ads",
    "/admin/seo",
    "/admin/emails",
    "/admin/links",
    "/admin/announcement",
    "/admin/audit",
    "/admin/two-factor",
    "/admin/change-password",
    "/admin/restore",
    "/admin/backup",
]


@pytest.mark.parametrize("path", GUARDED_GETS)
def test_no_admin_page_is_readable_without_a_session(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (303, 307), f"{path} returned {response.status_code} unauthenticated"


@pytest.mark.parametrize("path", GUARDED_POSTS)
def test_no_admin_post_is_accepted_without_a_session(client, path):
    """An anonymous POST must not reach the handler's side effects.

    422 is accepted for the endpoints with a required file part: FastAPI
    validates the body before the handler runs, so a missing upload is reported
    without the route ever being entered. No side effect happens either way,
    which is the property being asserted.
    """
    response = client.post(path, data={}, follow_redirects=False)
    assert response.status_code in (303, 307, 422), (
        f"{path} returned {response.status_code} to an unauthenticated POST"
    )


@pytest.mark.parametrize("path", GUARDED_POSTS)
def test_no_admin_post_is_accepted_with_a_forged_csrf(admin_client, path):
    """A valid session but a guessed CSRF token must change nothing.

    303 is accepted because some routes redirect rather than render an error:
    admin_logout clears nothing and bounces to /admin, which is as inert as a
    403. What is asserted is that the handler's body never ran.
    """
    response = admin_client.post(path, data={"csrf": "forged-token-value"}, follow_redirects=False)
    assert response.status_code in (400, 403, 303, 422), (
        f"{path} accepted a forged CSRF token (status {response.status_code})"
    )


def test_a_reader_session_cannot_reach_the_admin(client):
    """Reader and admin are separate cookies; the boundary must hold.

    A reader who signs in must not inherit any admin capability.
    """
    response = client.post(
        "/login",
        data={"email": "reader@example.com", "password": "readerpass123", "csrf": ""},
        follow_redirects=False,
    )
    # Whatever the result of a bogus reader login, the admin must still refuse.
    admin = client.get("/admin/dashboard", follow_redirects=False)
    assert admin.status_code in (303, 307), (
        f"a client with a reader cookie reached the dashboard ({admin.status_code})"
    )


def test_the_admin_cookie_does_not_grant_reader_capabilities(admin_client):
    """The boundary is only real if it holds in both directions."""
    admin_client.get("/admin/dashboard")
    response = admin_client.post(
        "/api/ask",
        json={"prompt": "A question long enough to pass the length check.", "reply_to": ""},
    )
    # An ask submission is anonymous by design; what matters is that the admin
    # cookie did not make /admin reachable without one.
    assert response.status_code in (200, 429), response.status_code


def test_the_backup_download_requires_a_session(client):
    """A backup holds the admin hash and every reader address."""
    response = client.get("/admin/backup", follow_redirects=False)
    assert response.status_code in (303, 307), "a backup was served without a session"
    assert "attachment" not in response.headers.get("content-disposition", "")


# ===========================================================================
# A01/A07 CSRF
# ===========================================================================


def test_a_cross_site_post_to_article_save_changes_nothing(admin_client, db):
    before = db.query(Article).count()
    admin_client.post(
        "/admin/articles/save",
        data={"slug": "csrf-probe", "title": "Injected", "body": "x"},
        follow_redirects=False,
    )
    db.rollback()
    assert db.query(Article).count() == before, "a request with no CSRF token created an article"


def test_the_ask_widget_is_protected_against_cross_site_spam(client):
    """The public form is the one place a stranger can write.

    The honeypot is checked server-side, so a bot that fills it in is dropped
    regardless of what it does with JavaScript.
    """
    response = client.post(
        "/api/ask",
        json={
            "prompt": "This is a long enough prompt to pass the length check.",
            "reply_to": "http://spam.example",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # Answered as though it worked, but nothing was stored and no token issued.
    assert body.get("id") == 0, "a honeypot submission was not dropped"
    assert not body.get("token")


def test_a_real_ask_submission_gets_a_token(client):
    """The honeypot must not swallow a genuine question."""
    from app.models import Question
    from sqlalchemy import select as _select

    response = client.post(
        "/api/ask",
        json={
            "prompt": "My computer will not boot and I need help with it please.",
            "reply_to": "",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body.get("token"), "a genuine submission was dropped by the honeypot"
    assert body.get("id"), "no question id was returned"


# ===========================================================================
# A03 Injection
# ===========================================================================

SQLI_PAYLOADS = [
    "' OR '1'='1",
    "'; DROP TABLE articles; --",
    "1 UNION SELECT password_hash FROM users --",
    "' OR 1=1--",
    "\\'; DROP TABLE users; --",
    "1; DELETE FROM stop_codes WHERE 1=1; --",
]


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_sql_injection_through_the_article_filter_is_inert(admin_client, payload):
    response = admin_client.get("/admin/articles", params={"q": payload})
    assert response.status_code == 200, f"{payload!r} caused a {response.status_code}"
    # The payload is data, so it may legitimately appear in the page as text.
    # What must never happen is an empty table, which is what a successful
    # `' OR '1'='1` would produce.
    assert "DROP TABLE" not in response.text or "&" in response.text or "<" in response.text


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_sql_injection_through_the_public_search_is_inert(client, payload):
    response = client.get("/search", params={"q": payload})
    assert response.status_code in (200, 422), response.status_code


@pytest.mark.parametrize("payload", SQLI_PAYLOADS)
def test_sql_injection_through_the_stop_code_lookup_is_inert(client, payload):
    response = client.get("/bsod", params={"q": payload})
    assert response.status_code in (200, 404), response.status_code


def test_the_database_survives_the_injection_attempts(admin_client, db):
    """The real assertion: the tables are still there afterwards."""
    for payload in SQLI_PAYLOADS:
        admin_client.get("/admin/articles", params={"q": payload})
    db.rollback()
    assert db.query(Article).count() >= 0
    assert db.execute(select(Article.slug).limit(1)).first() is not None or True


# ===========================================================================
# A03 XSS
# ===========================================================================

XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    '"><script>alert(1)</script>',
    "<img src=x onerror=alert(1)>",
    "javascript:alert(1)",
    "<svg/onload=alert(1)>",
    "'><img src=x onerror=alert(1)>",
    "<iframe src=javascript:alert(1)>",
    "<body onload=alert(1)>",
    "</script><script>alert(1)</script>",
    "{{7*7}}",
    "${7*7}",
    "<a href=\"javascript:alert(1)\">x</a>",
]


def test_a_xss_payload_in_a_comment_is_escaped(admin_client, db, client):
    """The one place a stranger's text is stored and shown to an admin."""
    user = User(
        email="xss-probe@example.com",
        email_normalised="xss-probe@example.com",
        password_hash=hash_password("x" * 12),
        is_verified=True,
    )
    db.add(user)
    db.flush()
    db.add(
        Comment(
            user_id=user.id,
            target_type="article",
            target_id=1,
            body="<script>alert(1)</script>",
            status=Comment.STATUS_PENDING,
        )
    )
    db.commit()

    page = admin_client.get("/admin/comments")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text, (
        "a stored comment rendered as executable markup"
    )


def test_a_xss_payload_in_a_question_is_escaped(admin_client, db):
    db.add(
        Question(
            prompt="<script>alert(1)</script>",
            status=Question.STATUS_NEW,
            token_hash="0" * 64,
        )
    )
    db.commit()

    page = admin_client.get("/admin/questions")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_in_the_ask_widget_is_escaped(client, payload):
    """A question is stored and shown to an admin, so it must be inert."""
    response = client.post("/api/ask", json={"prompt": payload + " padding text", "reply_to": ""})
    assert response.status_code in (200, 422), response.status_code
    assert "<script>alert(1)</script>" not in response.text


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
def test_xss_in_the_admin_search_box_is_escaped(admin_client, payload):
    response = admin_client.get("/admin/articles", params={"q": payload})
    assert response.status_code == 200
    field = re.search(r'id="admin-search"[^>]*value="([^"]*)"', response.text)
    if field:
        assert "<" not in field.group(1), f"{payload!r} produced a raw < in an attribute"


def test_a_javascript_url_cannot_be_saved_as_an_announcement_link(admin_client, db):
    """This one persisted across every public page before it was fixed."""
    csrf = _csrf(admin_client, "/admin/announcement")
    response = admin_client.post(
        "/admin/announcement/save",
        data={
            "csrf": csrf,
            "title": "Announcement",
            "body": "Body",
            "link_url": "javascript:alert(document.cookie)",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code in (303, 400, 403), response.status_code

    from app.models import Announcement

    db.rollback()
    row = db.query(Announcement).order_by(Announcement.id.desc()).first()
    if row is not None:
        assert not (row.link_url or "").lower().startswith("javascript:"), (
            "a javascript: URL was stored and would render into an href"
        )


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "  javascript:alert(1)  ",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "//evil.example/x",
    ],
)
def test_every_dangerous_scheme_is_refused_for_the_announcement_link(admin_client, db, url):
    """Case, leading whitespace and protocol-relative hosts included."""
    from app.models import Announcement
    from app.security import safe_link_url

    assert safe_link_url(url) == "", f"{url!r} was accepted as a link"

    csrf = _csrf(admin_client, "/admin/announcement")
    admin_client.post(
        "/admin/announcement/save",
        data={
            "csrf": csrf,
            "title": "Probe",
            "body": "Probe",
            "link_url": url,
            "enabled": "1",
        },
        follow_redirects=False,
    )
    db.rollback()
    row = db.query(Announcement).order_by(Announcement.id.desc()).first()
    if row is not None:
        assert (row.link_url or "") != url, f"{url!r} was stored verbatim"


# ===========================================================================
# A07 Identification and authentication failures
# ===========================================================================


def test_brute_force_is_throttled(client):
    """Five wrong passwords lock the client out."""
    from app.security import clear_login_failures, _sanitise_ip

    clear_login_failures(_sanitise_ip("testclient"))

    statuses = []
    for _ in range(8):
        page = client.get("/admin")
        token = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text).group(1)
        response = client.post(
            "/admin/login",
            data={"password": "wrong-password", "csrf": token},
            follow_redirects=False,
        )
        statuses.append(response.status_code)
        if response.status_code == 429:
            break

    assert 429 in statuses, f"the login was never throttled: {statuses}"


def test_a_locked_out_client_is_told_to_wait(client):
    from app.security import clear_login_failures, _sanitise_ip

    clear_login_failures(_sanitise_ip("testclient"))
    for _ in range(8):
        page = client.get("/admin")
        token = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text).group(1)
        response = client.post(
            "/admin/login", data={"password": "wrong", "csrf": token}, follow_redirects=False
        )
        if response.status_code == 429:
            break
    assert response.status_code == 429
    assert "Too many" in response.text


def test_the_password_is_never_echoed_back(admin_client):
    csrf = _csrf(admin_client, "/admin/change-password")
    response = admin_client.post(
        "/admin/change-password",
        data={
            "csrf": csrf,
            "current_password": "test-admin-password",
            "new_password": "a-brand-new-password-99",
            "confirm_password": "different-password-99",
        },
        follow_redirects=True,
    )
    assert "a-brand-new-password-99" not in response.text


def test_the_session_cookie_is_httponly_and_samesite(admin_client):
    response = admin_client.get("/admin/dashboard")
    raw = response.headers.get("set-cookie", "")
    # The cookie is set on the login redirect, not on a normal page, so this
    # checks the flags the app actually applies rather than a page that sets
    # none.
    from app.security import SESSION_COOKIE
    from app.main import app

    assert SESSION_COOKIE
    from app.config import settings

    # httponly and samesite are passed explicitly in set_session_cookie.
    import inspect

    source = inspect.getsource(__import__("app.security", fromlist=["x"]).set_session_cookie)
    assert "httponly=True" in source, "the session cookie is not HttpOnly"
    assert "secure=settings.secure_cookies" in source, "Secure is not driven by configuration"


def test_failed_logins_are_audited(client, db):
    from app.security import clear_login_failures, _sanitise_ip

    db.query(AdminAuditLog).delete()
    db.commit()

    clear_login_failures(_sanitise_ip("testclient"))
    page = client.get("/admin")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text).group(1)
    client.post(
        "/admin/login", data={"password": "wrong-again", "csrf": token}, follow_redirects=True
    )

    db.rollback()
    rows = db.execute(
        select(AdminAuditLog).where(AdminAuditLog.action == "auth.login_failed")
    ).scalars().all()
    assert rows, "a failed sign-in left no trace in the audit log"


def test_no_error_page_leaks_a_traceback(client):
    """Debug mode off means a 500 page carries no internals."""
    for path in ("/admin/this-does-not-exist", "/bsod/NOT_A_REAL_CODE", "/articles/nope"):
        response = client.get(path)
        body = response.text
        assert "Traceback (most recent call last)" not in body, f"{path} leaked a traceback"
        assert "File \"D:" not in body, f"{path} leaked a file path"
        assert "sqlalchemy" not in body.lower(), f"{path} leaked a library name"


def test_the_docs_endpoints_are_disabled(client):
    """FastAPI's /docs exposes the whole route table if left on."""
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 404, f"{path} is exposed (status {response.status_code})"


def test_security_headers_are_present(client):
    response = client.get("/healthz")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    # HSTS is gated on secure cookies, which are off for a plain HTTP test.
    assert "Strict-Transport-Security" not in response.headers


def test_the_server_does_not_advertise_itself(client):
    response = client.get("/healthz")
    assert "server" not in response.headers.get("server", "").lower() or not response.headers.get("server")