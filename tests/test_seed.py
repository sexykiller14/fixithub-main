"""seed.py behaviour, which has no coverage of its own.

seed.py is the first thing anyone runs against a new database, so its failure
modes matter more than usual: they are the first error a deploy produces.

Each test runs seed.py as a subprocess. Importing it in-process would mean
re-importing app.config and every app module so the database URL took effect,
which leaves half a second set of modules in sys.modules for later tests to
trip over. A subprocess gets its own interpreter and cannot leak anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "seed.py"


@pytest.fixture
def unseeded(tmp_path):
    """A database URL pointing at a file that does not exist yet.

    Deliberately not the suite's scratch database: --check has to cope with a
    database that was never seeded, which is exactly the state a fresh deploy
    is in.
    """
    return f"sqlite:///{(tmp_path / 'unseeded.db').as_posix()}"


def run_seed(url: str, *args: str, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "FIXITHUB_DATABASE_URL": url,
        "FIXITHUB_SECRET_KEY": "seed-pytest-secret",
        "FIXITHUB_ADMIN_PASSWORD": "seed-pytest-password",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SEED), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=300,
    )


def test_check_on_an_unseeded_database_reports_zero_rather_than_raising(unseeded):
    """--check must answer, not traceback.

    Counting rows against a table that was never created raised
    OperationalError: no such table: articles. This is the first command an
    operator runs when a fresh deploy looks empty, so it has to say "nothing
    loaded yet" instead of printing a stack trace.
    """
    result = run_seed(unseeded, "--check")

    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "articles   0" in result.stdout, result.stdout
    assert "stop codes 0" in result.stdout, result.stdout


def test_check_after_seeding_reports_the_content(unseeded):
    """The ordinary path still works: seed, then check."""
    seeded = run_seed(unseeded, "--rebuild-search")
    assert seeded.returncode == 0, seeded.stderr

    result = run_seed(unseeded, "--check")

    assert result.returncode == 0, result.stderr
    # Counted from the content folder rather than hardcoded, so adding an
    # article does not have to be matched with an edit here.
    expected = len(
        [p for p in (ROOT / "content").rglob("*.md") if not p.name.startswith("_")]
    )
    assert f"articles   {expected}" in result.stdout, result.stdout


def test_check_is_repeatable(unseeded):
    """Creating the schema up front must stay idempotent across runs."""
    for _ in range(3):
        result = run_seed(unseeded, "--check")
        assert result.returncode == 0, result.stderr


def test_seeding_twice_does_not_duplicate_articles(unseeded):
    """seed.py documents itself as safe to run repeatedly. Check that it is.

    Seeded twice against the same database, the article count must be unchanged
    and equal to the number of markdown files. A second run that appended
    rather than upserting would double it.
    """
    expected = len(
        [p for p in (ROOT / "content").rglob("*.md") if not p.name.startswith("_")]
    )

    assert run_seed(unseeded).returncode == 0
    first = run_seed(unseeded, "--check")
    assert f"articles   {expected}" in first.stdout, first.stdout

    assert run_seed(unseeded).returncode == 0
    second = run_seed(unseeded, "--check")

    assert f"articles   {expected}" in second.stdout, second.stdout


def test_set_admin_password_refuses_a_short_password(unseeded):
    """The length floor is enforced, and reported rather than raising."""
    result = run_seed(unseeded, "--no-content", "--set-admin-password", "short")

    assert result.returncode == 1
    assert "at least 8 characters" in result.stdout, result.stdout