"""Two-factor authentication on the admin sign-in.

The property that matters is that the password alone stops being enough. These
tests walk the real flow: enrol, sign in with password + code, reject a wrong
code, reject a missing second step, and confirm a recovery code works exactly
once. They also check the escape hatches, because a second factor that can
lock the sole admin out of their own site is a worse outcome than no second
factor at all.
"""

import re

import pytest

from app.services import totp

from tests.conftest import make_csrf

TWO_FACTOR_URL = "/admin/two-factor"


@pytest.fixture
def enrolled(monkeypatch, tmp_path):
    """An enrolled secret in a temporary data directory, plus that secret."""
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)
    secret = totp.generate_secret()
    totp.save(secret, totp.generate_recovery_codes(5))
    return secret


def _login(client, password="test-admin-password"):
    page = client.get("/admin")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text).group(1)
    return client.post(
        "/admin/login",
        data={"password": password, "csrf": token},
        follow_redirects=False,
    )


def test_a_password_alone_is_not_enough_when_enrolled(client, enrolled):
    """The whole point: no session without the code."""
    response = _login(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login/2fa", (
        "the password alone signed the admin straight in"
    )

    # And no cookie was issued.
    page = client.get("/admin/dashboard", follow_redirects=False)
    assert page.status_code in (303, 307), "the dashboard is reachable without a session"


def test_the_second_step_grants_the_session(client, enrolled):
    _login(client)
    code = totp.code_at(enrolled)

    step = client.get("/admin/login/2fa")
    assert step.status_code == 200
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)

    done = client.post("/admin/login/2fa", data={"code": code, "csrf": token}, follow_redirects=False)
    assert done.status_code == 303
    assert done.headers["location"] == "/admin/dashboard"

    dash = client.get("/admin/dashboard")
    assert dash.status_code == 200, "the session did not take"


def test_a_wrong_code_does_not_grant_the_session(client, enrolled):
    _login(client)
    step = client.get("/admin/login/2fa")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)

    wrong = "000000" if totp.code_at(enrolled) != "000000" else "111111"
    response = client.post(
        "/admin/login/2fa", data={"code": wrong, "csrf": token}, follow_redirects=False
    )
    assert response.status_code == 401
    assert client.get("/admin/dashboard", follow_redirects=False).status_code in (303, 307)


def test_the_second_step_cannot_be_skipped(client, enrolled):
    """Reaching /admin/login/2fa without the pending cookie must not work."""
    direct = client.get("/admin/login/2fa", follow_redirects=False)
    assert direct.status_code == 303, "the second step was reachable with no password"

    post = client.post(
        "/admin/login/2fa",
        data={"code": totp.code_at(enrolled), "csrf": "x"},
        follow_redirects=False,
    )
    assert post.status_code == 303
    assert client.get("/admin/dashboard", follow_redirects=False).status_code in (303, 307)


def test_the_pending_cookie_is_required_and_forged_ones_fail(client, enrolled):
    _login(client)
    step = client.get("/admin/login/2fa")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)

    # Replace the pending cookie with a forgery.
    client.cookies.set("fixithub_2fa_pending", "forged.value.not-a-real-signature")
    response = client.post(
        "/admin/login/2fa",
        data={"code": totp.code_at(enrolled), "csrf": token},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert client.get("/admin/dashboard", follow_redirects=False).status_code in (303, 307)


def test_a_recovery_code_works_once(client, enrolled):
    codes = totp._load()["recovery_hashes"]
    # The plaintext codes are gone from storage, so re-read them by regenerating
    # a known one: instead, save a known set for this test.
    known = totp.generate_recovery_codes(3)
    totp.save(enrolled, known)

    _login(client)
    step = client.get("/admin/login/2fa")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)

    first = client.post(
        "/admin/login/2fa", data={"code": known[0], "csrf": token}, follow_redirects=False
    )
    assert first.status_code == 303
    assert first.headers["location"] == "/admin/dashboard"
    assert codes is not None


def test_a_recovery_code_is_single_use(client, enrolled):
    known = totp.generate_recovery_codes(3)
    totp.save(enrolled, known)

    _login(client)
    step = client.get("/admin/login/2fa")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)
    client.post("/admin/login/2fa", data={"code": known[0], "csrf": token}, follow_redirects=False)
    client.post("/admin/logout", data={"csrf": make_csrf(client)}, follow_redirects=False)

    # Try the same code again.
    _login(client)
    step = client.get("/admin/login/2fa")
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)
    client.post("/admin/login/2fa", data={"code": known[0], "csrf": token}, follow_redirects=False)
    assert client.get("/admin/dashboard", follow_redirects=False).status_code in (303, 307)


def test_guessing_codes_is_throttled(client, enrolled):
    """A second factor must not become an unlimited guessing oracle."""
    _login(client)
    for _ in range(8):
        step = client.get("/admin/login/2fa")
        token = re.search(r'name="csrf"[^>]*value="([^"]+)"', step.text).group(1)
        response = client.post(
            "/admin/login/2fa", data={"code": "000000", "csrf": token}, follow_redirects=False
        )
        if response.status_code == 429:
            break
    assert response.status_code == 429, "the second factor was never rate limited"


def test_no_enrolment_means_no_second_step(client, monkeypatch, tmp_path):
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)
    response = _login(client)
    assert response.headers["location"] == "/admin/dashboard"


def test_the_escape_hatch_disables_the_check(client, enrolled, monkeypatch):
    """FIXITHUB_DISABLE_2FA is the way back in when a device is lost."""
    from app.config import settings

    monkeypatch.setattr(settings, "disable_2fa", True)
    response = _login(client)
    assert response.headers["location"] == "/admin/dashboard"


# --------------------------------------------------------------------------
# Enrolment, which needs an existing session
# --------------------------------------------------------------------------


def test_the_setup_page_needs_a_login(client):
    assert client.get(TWO_FACTOR_URL, follow_redirects=False).status_code in (303, 307)


@pytest.mark.usefixtures("admin_client")
def test_enrolment_only_takes_effect_after_confirmation(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)

    page = admin_client.get(TWO_FACTOR_URL)
    assert page.status_code == 200
    assert "Nothing is set up yet" in page.text

    csrf = make_csrf(admin_client)
    started = admin_client.post(
        f"{TWO_FACTOR_URL}/start", data={"csrf": csrf}, follow_redirects=True
    )
    assert started.status_code == 200
    assert "Scan this" in started.text, "the secret was not shown"

    # Not enrolled yet: a half-finished setup must not lock anyone out.
    assert not totp.is_enrolled()


@pytest.mark.usefixtures("admin_client")
def test_confirming_with_the_right_code_enrols(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)

    csrf = make_csrf(admin_client)
    page = admin_client.post(f"{TWO_FACTOR_URL}/start", data={"csrf": csrf}, follow_redirects=True).text
    secret = re.search(r'([A-Z2-7]{32})', page).group(1)

    token = make_csrf(admin_client)
    confirmed = admin_client.post(
        f"{TWO_FACTOR_URL}/confirm",
        data={"secret": "IGNORED", "code": totp.code_at(secret), "csrf": token},
        follow_redirects=True,
    )
    assert "Save these recovery codes" in confirmed.text, "the recovery codes were not shown"
    assert totp.is_enrolled()


@pytest.mark.usefixtures("admin_client")
def test_a_wrong_confirmation_code_does_not_enrol(admin_client, monkeypatch, tmp_path):
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)

    csrf = make_csrf(admin_client)
    page = admin_client.post(f"{TWO_FACTOR_URL}/start", data={"csrf": csrf}, follow_redirects=True).text
    secret = re.search(r'([A-Z2-7]{32})', page).group(1)

    token = make_csrf(admin_client)
    good = totp.code_at(secret)
    admin_client.post(
        f"{TWO_FACTOR_URL}/confirm",
        data={"secret": secret, "code": "000000" if good != "000000" else "111111", "csrf": token},
        follow_redirects=True,
    )
    assert not totp.is_enrolled(), "a wrong code turned the second factor on"


@pytest.mark.usefixtures("admin_client")
def test_the_posted_secret_is_ignored_in_favour_of_the_signed_cookie(
    admin_client, monkeypatch, tmp_path
):
    """A tampered form field must not enrol an attacker-chosen secret."""
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)

    csrf = make_csrf(admin_client)
    page = admin_client.post(f"{TWO_FACTOR_URL}/start", data={"csrf": csrf}, follow_redirects=True).text
    real_secret = re.search(r'([A-Z2-7]{32})', page).group(1)

    attack_secret = totp.generate_secret()
    token = make_csrf(admin_client)
    # Code matches the ATTACKER's secret, not the one shown to the admin.
    admin_client.post(
        f"{TWO_FACTOR_URL}/confirm",
        data={"secret": attack_secret, "code": totp.code_at(attack_secret), "csrf": token},
        follow_redirects=True,
    )
    assert not totp.is_enrolled(), "an attacker-supplied secret was enrolled"
    assert totp._load().get("secret") != attack_secret
    assert real_secret


@pytest.mark.usefixtures("admin_client")
def test_disabling_needs_the_password_again(admin_client, monkeypatch, tmp_path):
    """A stolen session cookie must not be able to weaken authentication."""
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)
    secret = totp.generate_secret()
    totp.save(secret, totp.generate_recovery_codes())

    csrf = make_csrf(admin_client)
    refused = admin_client.post(
        f"{TWO_FACTOR_URL}/disable",
        data={"password": "wrong-password", "csrf": csrf},
        follow_redirects=True,
    )
    assert totp.is_enrolled(), "two-factor was disabled without the password"

    allowed = admin_client.post(
        f"{TWO_FACTOR_URL}/disable",
        data={"password": "test-admin-password", "csrf": make_csrf(admin_client)},
        follow_redirects=True,
    )
    assert not totp.is_enrolled(), "the correct password did not disable two-factor"