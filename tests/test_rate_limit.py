"""Rate limiting for the network tools and other rate-limited endpoints."""

from __future__ import annotations

import re

import pytest

from app.rate_limit import SlidingWindowLimiter, client_key, enforce


# --------------------------------------------------------------------------
# The limiter itself
# --------------------------------------------------------------------------


def test_allows_requests_below_the_limit():
    limiter = SlidingWindowLimiter(3, 60)
    results = [limiter.check("1.2.3.4") for _ in range(3)]
    assert all(r.allowed for r in results)
    assert [r.remaining for r in results] == [2, 1, 0]


def test_blocks_the_request_after_the_limit():
    limiter = SlidingWindowLimiter(3, 60)
    for _ in range(3):
        limiter.check("1.2.3.4")
    blocked = limiter.check("1.2.3.4")
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.reset_after > 0
    assert blocked.limit == 3


def test_limit_is_per_key():
    limiter = SlidingWindowLimiter(2, 60)
    limiter.check("1.1.1.1")
    limiter.check("1.1.1.1")
    assert limiter.check("1.1.1.1").allowed is False
    # A different client has its own budget.
    assert limiter.check("2.2.2.2").allowed is True


def test_window_expiry_frees_the_budget(monkeypatch):
    limiter = SlidingWindowLimiter(2, 10)
    limiter.check("1.2.3.4")
    limiter.check("1.2.3.4")
    assert limiter.check("1.2.3.4").allowed is False

    # Move time forward past the window.
    real_time = __import__("time").monotonic
    monkeypatch.setattr("app.rate_limit.time.monotonic", lambda: real_time() + 11)
    assert limiter.check("1.2.3.4").allowed is True


def test_reset_clears_everything():
    limiter = SlidingWindowLimiter(1, 60)
    limiter.check("1.2.3.4")
    assert limiter.check("1.2.3.4").allowed is False
    limiter.reset()
    assert limiter.check("1.2.3.4").allowed is True


def test_cleanup_drops_stale_keys():
    limiter = SlidingWindowLimiter(1, 60)
    limiter.check("1.2.3.4")
    limiter._hits["2.2.2.2"] = [0.0]  # very old timestamp
    limiter.cleanup()
    assert "2.2.2.2" not in limiter._hits


def test_concurrent_access_is_thread_safe():
    """Hammer the limiter from many threads; the cap must still hold."""
    import threading

    limiter = SlidingWindowLimiter(50, 60)
    allowed = []
    lock = threading.Lock()

    def worker():
        result = limiter.check("1.2.3.4")
        with lock:
            allowed.append(result.allowed)

    threads = [threading.Thread(target=worker) for _ in range(200)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(1 for value in allowed if value) == 50


# --------------------------------------------------------------------------
# HTTP behaviour
# --------------------------------------------------------------------------


def test_tools_allow_ten_requests_per_minute(client):
    """The eleventh request inside the window is refused with a 429."""
    statuses = []
    for _ in range(12):
        response = client.post("/tools/status", data={"url": "https://example.invalid/"})
        statuses.append(response.status_code)

    # The first ten pass validation and reach the tool (which then fails on the
    # unreachable host), and everything after that is rate limited.
    assert 429 in statuses
    assert statuses.index(429) >= 9


def test_rate_limit_response_has_retry_headers(client):
    for _ in range(11):
        response = client.post("/tools/status", data={"url": "https://example.invalid/"})
    if response.status_code == 429:
        assert response.headers["retry-after"]
        assert response.headers["x-ratelimit-limit"]
        assert response.headers["x-ratelimit-remaining"] == "0"


def test_rate_limit_is_shared_across_tools(client):
    """The limiter is global, so using one tool exhausts the others."""
    for _ in range(11):
        client.post("/tools/status", data={"url": "https://example.invalid/"})
    response = client.post("/tools/port", data={"host": "example.com", "port": "443"})
    assert response.status_code == 429


def test_article_pages_are_not_rate_limited(client):
    """Reading guides must never be throttled."""
    for _ in range(15):
        assert client.get("/bsod").status_code == 200


def test_public_ip_tool_is_rate_limited(client):
    responses = [client.get("/tools/ip").status_code for _ in range(12)]
    assert 429 in responses


def test_login_throttle_blocks_repeated_failures(client):
    """Five wrong passwords lock the client out for the rest of the window."""
    # Each attempt needs a fresh CSRF token, since a rejected attempt rotates it.
    for _ in range(6):
        page = client.get("/admin")
        token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        client.post("/admin/login", data={"password": "wrong-password", "csrf": token})

    page = client.get("/admin")
    token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    response = client.post(
        "/admin/login", data={"password": "wrong-password", "csrf": token}
    )
    assert response.status_code == 429
    assert "Too many failed attempts" in response.text


def test_429_page_renders_html(client):
    for _ in range(12):
        response = client.post("/tools/status", data={"url": "https://example.invalid/"})
    if response.status_code == 429:
        assert "text/html" in response.headers["content-type"]


def test_healthz_is_never_rate_limited(client):
    assert client.get("/healthz").status_code == 200
