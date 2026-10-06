"""Security helper tests.

The admin hash resolution is covered here rather than in the page tests because
it has a performance requirement that only shows up under a specific
combination of environment and files, which no page test sets up.
"""

from __future__ import annotations

import time

import pytest

from app import security
from app.security import (
    admin_configured,
    clear_login_failures,
    constant_time_equals,
    hash_password,
    load_admin_hash,
    login_locked_out,
    record_login_failure,
    verify_password,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    security._password_cache.clear()
    yield
    security._password_cache.clear()


@pytest.fixture
def no_hash_file(monkeypatch, tmp_path):
    """Pretend data/admin.json does not exist."""
    monkeypatch.setattr(security, "ADMIN_HASH_FILE", tmp_path / "absent.json")


def test_hash_and_verify_round_trip():
    stored = hash_password("correct-horse-battery")
    assert verify_password("correct-horse-battery", stored)
    assert not verify_password("wrong-password", stored)


def test_verify_rejects_empty_inputs():
    assert not verify_password("", hash_password("x"))
    assert not verify_password("x", "")
    assert not verify_password("x", "not-a-bcrypt-hash")


def test_plain_env_password_is_hashed_and_cached(monkeypatch, no_hash_file):
    """The plain-password env var must verify, and must only pay the bcrypt
    cost once. A fresh cloud deploy has neither a hash env var nor the file, so
    without the cache every page render would cost about 300ms."""
    monkeypatch.setattr(security.settings, "admin_password_hash", "")
    monkeypatch.setattr(security.settings, "admin_password", "deploy-password")

    started = time.perf_counter()
    first = load_admin_hash()
    first_cost = time.perf_counter() - started

    assert first.startswith("$2"), "expected a bcrypt hash"
    assert verify_password("deploy-password", first)
    assert not verify_password("nope", first)

    started = time.perf_counter()
    second = load_admin_hash()
    second_cost = time.perf_counter() - started

    # The cache must return the identical value, not a fresh hash, because a
    # second hash of the same password would also verify but would differ.
    assert second == first
    # bcrypt cost 12 takes roughly 300ms, so a cached read has to be far faster.
    assert second_cost < 0.05, f"cached read took {second_cost * 1000:.0f}ms"
    assert first_cost > second_cost


def test_cache_is_keyed_on_the_password(monkeypatch, no_hash_file):
    """Changing the password must not serve a stale cached hash."""
    monkeypatch.setattr(security.settings, "admin_password_hash", "")
    monkeypatch.setattr(security.settings, "admin_password", "first-password")
    first = load_admin_hash()

    monkeypatch.setattr(security.settings, "admin_password", "second-password")
    second = load_admin_hash()

    assert first != second
    assert verify_password("first-password", first)
    assert verify_password("second-password", second)
    assert not verify_password("first-password", second)


def test_explicit_hash_env_var_wins_over_everything(monkeypatch, tmp_path):
    monkeypatch.setattr(
        security.settings, "admin_password_hash", hash_password("from-env-hash")
    )
    monkeypatch.setattr(security.settings, "admin_password", "from-plain-env")
    assert verify_password("from-env-hash", load_admin_hash())


def test_unconfigured_when_nothing_is_set(monkeypatch, no_hash_file):
    monkeypatch.setattr(security.settings, "admin_password_hash", "")
    monkeypatch.setattr(security.settings, "admin_password", "")
    assert load_admin_hash() == ""
    assert not admin_configured()


def test_corrupt_hash_file_is_ignored(monkeypatch, tmp_path):
    bad = tmp_path / "admin.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(security, "ADMIN_HASH_FILE", bad)
    monkeypatch.setattr(security.settings, "admin_password_hash", "")
    monkeypatch.setattr(security.settings, "admin_password", "fallback-password")
    assert verify_password("fallback-password", load_admin_hash())


def test_login_lockout_after_repeated_failures():
    identifier = "203.0.113.7"
    clear_login_failures(identifier)
    assert not login_locked_out(identifier)[0]

    for _ in range(security.LOGIN_MAX_FAILURES):
        record_login_failure(identifier)

    locked, remaining = login_locked_out(identifier)
    assert locked
    assert 0 < remaining <= security.LOGIN_WINDOW
    clear_login_failures(identifier)
    assert not login_locked_out(identifier)[0]


def test_constant_time_equals():
    assert constant_time_equals("abc", "abc")
    assert not constant_time_equals("abc", "abd")
    assert not constant_time_equals("abc", "")
    assert constant_time_equals("", "")


def test_sanitise_ip_strips_unexpected_characters():
    """Only characters that can legitimately appear in an address survive, so a
    crafted header cannot inject anything into the rate-limit key."""
    # An injection attempt loses its header name, spaces and newlines, keeping
    # only the hex digits and punctuation that a real address uses.
    assert security._sanitise_ip("1.2.3.4\r\nX-Evil: 1") == "1.2.3.4-E:1"
    assert security._sanitise_ip("2001:db8::1") == "2001:db8::1"
    assert security._sanitise_ip("::ffff:192.0.2.1") == "::ffff:192.0.2.1"
    # Whatever goes in, the result is bounded and free of whitespace.
    assert len(security._sanitise_ip("a" * 500)) == 64
    for raw in ("1.2.3.4\n\r", "  1.2.3.4  ", "admin'; DROP TABLE--"):
        cleaned = security._sanitise_ip(raw)
        assert not any(ch.isspace() for ch in cleaned)
        assert len(cleaned) <= 64