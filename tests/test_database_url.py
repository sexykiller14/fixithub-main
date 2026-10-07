"""Postgres URL handling, and the driver trap behind it.

The connection string is supplied by whoever deploys, so it arrives in whatever
shape the provider's dashboard happened to copy out. These tests pin the
normalisation to the driver the project actually installs.

The specific failure this guards against: ``requirements.txt`` allows
``sqlalchemy>=2.0.30``, and from SQLAlchemy 2.1 a bare ``postgresql://`` URL
resolves to psycopg 3 rather than psycopg2. Only ``psycopg2-binary`` is
installed, so ``create_engine`` raised ``ModuleNotFoundError: No module named
'psycopg'`` at import. On Vercel that is invisible until the first request, and
then the function simply does not boot.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.config import (
    _resolve_database_url,
    _with_explicit_driver,
    _with_sslmode,
)

# A Supabase connection-pooler string, copied from the dashboard verbatim.
SUPABASE_URL = (
    "postgresql://postgres.abcdefgh:pa%40ssword@aws-0-eu-west-1.pooler.supabase.com"
    ":6543/postgres?sslmode=require"
)


class TestDriverNormalisation:
    def test_bare_postgresql_scheme_gets_psycopg2(self):
        # The regression: a bare scheme used to reach SQLAlchemy's own default.
        assert _with_explicit_driver(
            "postgresql://u:p@host:6543/db"
        ) == "postgresql+psycopg2://u:p@host:6543/db"

    def test_legacy_postgres_scheme_gets_psycopg2(self):
        assert _with_explicit_driver(
            "postgres://u:p@host:6543/db"
        ) == "postgresql+psycopg2://u:p@host:6543/db"

    def test_a_pasted_supabase_url_works_unchanged(self):
        normalised = _with_explicit_driver(SUPABASE_URL)
        assert normalised.startswith("postgresql+psycopg2://")
        # The percent-encoded password and the pooler host must survive intact.
        assert "pa%40ssword" in normalised
        assert "aws-0-eu-west-1.pooler.supabase.com" in normalised
        assert normalised.endswith(":6543/postgres?sslmode=require")

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql+psycopg2://u:p@host/db",
            "postgresql+psycopg://u:p@host/db",
            "postgresql+pg8000://u:p@host/db",
        ],
    )
    def test_an_explicit_driver_is_never_overwritten(self, url):
        # Someone who installs psycopg 3 and says so must still get it.
        assert _with_explicit_driver(url) == url

    @pytest.mark.parametrize(
        "url",
        ["sqlite:///data/fixithub.db", "sqlite://", "mysql+pymysql://u:p@host/db"],
    )
    def test_non_postgres_urls_are_untouched(self, url):
        assert _with_explicit_driver(url) == url

    def test_normalisation_is_idempotent(self):
        once = _with_explicit_driver(SUPABASE_URL)
        assert _with_explicit_driver(once) == once

    def test_a_url_without_a_driver_suffix_is_not_mangled(self):
        # Guard against a prefix match running into the rest of the host.
        assert _with_explicit_driver("postgresql://x") == "postgresql+psycopg2://x"
        assert _with_explicit_driver("postgresql:/typo") == "postgresql:/typo"


class TestEngineConstruction:
    """The real regression: the engine has to build with what is installed."""

    def test_create_engine_succeeds_on_a_supabase_url(self):
        # create_engine does not connect, so this asserts the driver imports
        # and the pool is constructed without needing a live database.
        engine = create_engine(_with_explicit_driver(SUPABASE_URL), pool_pre_ping=True)
        assert engine.dialect.driver == "psycopg2"

    def test_no_sqlite_connect_args_leak_into_postgres(self):
        # app/db.py adds check_same_thread/timeout for SQLite only. If that
        # branch were keyed on anything but the resolved URL, psycopg2 would
        # reject the arguments instead of quietly ignoring them.
        engine = create_engine(_with_explicit_driver(SUPABASE_URL))
        _, kwargs = engine.dialect.create_connect_args(engine.url)
        assert "check_same_thread" not in kwargs
        assert "timeout" not in kwargs

    def test_pre_ping_is_preserved(self):
        # Serverless connections are cut between warm invocations; without this
        # the first request after a long gap fails on a stale socket.
        engine = create_engine(
            _with_explicit_driver(SUPABASE_URL), pool_pre_ping=True
        )
        assert engine.pool._pre_ping is True


class TestSslMode:
    """Managed Postgres requires TLS, and some providers omit the parameter."""

    def test_sslmode_is_added_to_a_bare_url(self):
        assert _with_sslmode("postgresql://u:p@host:6543/db") == (
            "postgresql://u:p@host:6543/db?sslmode=require"
        )

    def test_an_existing_sslmode_is_respected(self):
        # An operator who wrote sslmode=disable meant it.
        url = "postgresql://u:p@host:5432/db?sslmode=disable"
        assert _with_sslmode(url) == url

    def test_an_existing_ssl_parameter_is_respected(self):
        url = "postgresql://u:p@host:5432/db?ssl=1"
        assert _with_sslmode(url) == url

    def test_sslmode_is_appended_to_an_existing_query(self):
        url = "postgresql://u:p@host:6543/db?application_name=fixithub"
        assert _with_sslmode(url) == (
            "postgresql://u:p@host:6543/db?application_name=fixithub&sslmode=require"
        )

    def test_sqlite_is_never_given_sslmode(self):
        assert _with_sslmode("sqlite:///data/fixithub.db") == "sqlite:///data/fixithub.db"


class TestProviderInjectedVariables:
    """The Supabase/Neon Vercel Marketplace sets POSTGRES_URL, not ours.

    Without this, connecting Supabase in the Vercel dashboard looks successful
    while the app quietly keeps using SQLite in /tmp, because nothing maps the
    injected name onto FIXITHUB_DATABASE_URL.
    """

    @staticmethod
    def _clear(monkeypatch):
        for name in ("FIXITHUB_DATABASE_URL", "POSTGRES_URL", "DATABASE_URL"):
            monkeypatch.delenv(name, raising=False)
        # Siblings the app must never pick up, present as they are in the
        # dashboard after installing the integration.
        monkeypatch.setenv(
            "POSTGRES_URL_NON_POOLING",
            "postgresql://postgres.abcdefgh:pw@db.abcdefgh.supabase.co:5432/postgres",
        )
        monkeypatch.setenv(
            "POSTGRES_PRISMA_URL",
            "postgresql://postgres.abcdefgh:pw@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?pgbouncer=true&connection_limit=1",
        )

    def test_postgres_url_is_used_when_present(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("POSTGRES_URL", SUPABASE_URL)
        resolved = _resolve_database_url()
        assert resolved.startswith("postgresql+psycopg2://")
        assert "pooler.supabase.com:6543" in resolved

    def test_our_own_variable_wins_over_the_injected_one(self, monkeypatch):
        # An operator must always be able to override without touching the
        # integration's dashboard entry.
        self._clear(monkeypatch)
        monkeypatch.setenv("POSTGRES_URL", SUPABASE_URL)
        monkeypatch.setenv(
            "FIXITHUB_DATABASE_URL", "postgresql://u:p@other-host:5432/elsewhere"
        )
        assert "other-host" in _resolve_database_url()

    def test_database_url_is_a_second_choice(self, monkeypatch):
        self._clear(monkeypatch)
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@neon-host:5432/neondb")
        assert "neon-host" in _resolve_database_url()

    def test_the_non_pooling_sibling_is_never_used(self, monkeypatch):
        # Direct, IPv6-only, times out on Vercel.
        self._clear(monkeypatch)
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@neon-host:5432/neondb")
        resolved = _resolve_database_url()
        assert "db.abcdefgh.supabase.co" not in resolved

    def test_the_prisma_sibling_is_never_used(self, monkeypatch):
        # pgbouncer/connection_limit are Prisma's, not SQLAlchemy's.
        self._clear(monkeypatch)
        resolved = _resolve_database_url()
        assert "pgbouncer" not in resolved
        assert "connection_limit" not in resolved

    def test_sqlite_is_the_last_resort(self, monkeypatch):
        self._clear(monkeypatch)
        assert _resolve_database_url().startswith("sqlite:///")

    def test_an_injected_url_still_builds_an_engine(self, monkeypatch):
        # End to end: the Marketplace string, normalised, must reach a working
        # engine without anyone hand-editing it.
        self._clear(monkeypatch)
        monkeypatch.setenv("POSTGRES_URL", SUPABASE_URL)
        engine = create_engine(_resolve_database_url())
        assert engine.dialect.driver == "psycopg2"