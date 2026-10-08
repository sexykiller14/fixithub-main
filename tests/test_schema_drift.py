"""Additive schema repair, which now runs on Postgres as well as SQLite.

``create_all`` only ever creates whole tables, so a column added to a model
afterwards is invisible to a database that already exists. The app then fails on
the first query that selects it. This project has no migration tool, so
``_add_missing_columns`` fills the gap with ALTER TABLE ... ADD COLUMN.

That repair used to be gated behind ``if not _is_sqlite: return``, which meant a
Postgres deployment on Vercel silently skipped it. This file pins the behaviour
that made that gate wrong: the column set is read through SQLAlchemy's
inspector, so the same loop works against any dialect.

The tests run against the suite's scratch SQLite database. Dropping and
re-adding a real column is destructive, so the test uses its own table rather
than a model table that other files share.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Boolean, Column, Integer, Table, Text, text
from sqlalchemy.dialects import postgresql, sqlite

from app.db import _add_missing_columns, _default_literal, _existing_columns, engine
from app.models import Base


@pytest.fixture
def scratch_table():
    """A model-backed table, created and destroyed around each test.

    It has to be registered on ``Base.metadata``, because that is the only
    collection ``_add_missing_columns`` walks: a table created with raw SQL is
    invisible to the repair loop, so a test built that way would pass without
    exercising anything. Registering a throwaway Table keeps the test on the
    real code path without touching a table the rest of the suite shares.
    """
    name = "fixithub_drift_probe"
    # Declared on Base.metadata, because that is the collection the repair loop
    # walks. Registered only for the duration of the test and removed afterwards,
    # so it cannot leak into another test's create_all.
    Base.metadata._remove_table(name, None)
    probe = Table(
        name,
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("label", Text),
    )
    probe.create(bind=engine)
    try:
        yield name
    finally:
        Base.metadata._remove_table(name, None)
        with engine.begin() as conn:
            conn.execute(text(f'DROP TABLE IF EXISTS "{name}"'))


def test_existing_columns_reads_a_live_table(scratch_table):
    with engine.connect() as conn:
        columns = _existing_columns(conn, scratch_table)

    assert columns == {"id", "label"}


def test_existing_columns_is_empty_for_a_missing_table():
    """An absent table must not raise.

    ``create_all`` runs before this loop, so this is the defensive case: a table
    that cannot be described is treated as having no columns to reconcile.
    """
    with engine.connect() as conn:
        assert _existing_columns(conn, "fixithub_table_that_is_not_here") == set()


def test_a_dropped_column_is_added_back(scratch_table):
    """The behaviour the SQLite-only gate used to prevent on Postgres."""
    with engine.begin() as conn:
        conn.execute(text(f'ALTER TABLE "{scratch_table}" DROP COLUMN label'))

    with engine.connect() as conn:
        assert "label" not in _existing_columns(conn, scratch_table)

    _add_missing_columns()

    with engine.connect() as conn:
        assert "label" in _existing_columns(conn, scratch_table)


def test_the_repair_leaves_existing_columns_alone(scratch_table):
    """Repair is additive only. Nothing is dropped, renamed or retyped."""
    before_types = None
    with engine.connect() as conn:
        assert _existing_columns(conn, scratch_table) == {"id", "label"}
        before_types = {
            row[1]: row[2]
            for row in conn.execute(text(f'PRAGMA table_info("{scratch_table}")'))
        }

    _add_missing_columns()

    with engine.connect() as conn:
        after_types = {
            row[1]: row[2]
            for row in conn.execute(text(f'PRAGMA table_info("{scratch_table}")'))
        }

    assert after_types == before_types


def test_a_boolean_default_is_spelled_for_the_dialect():
    """A Boolean default must be 1/0 on SQLite and true/false on Postgres.

    The repair used to emit DEFAULT 1 for every dialect. SQLite accepts that
    for a BOOLEAN column; Postgres rejects it with "column is of type boolean
    but default expression is of type integer", so adding any missing Boolean
    column on a Postgres deploy raised and the app could not start.
    """
    for value in (True, False):
        column = Column("flag", Boolean, default=value)

        assert _default_literal(column, sqlite.dialect()) == f" DEFAULT {1 if value else 0}"
        assert _default_literal(column, postgresql.dialect()) == f" DEFAULT {'true' if value else 'false'}"


def test_the_generated_statement_is_valid_postgres():
    """The clause has to compose into DDL Postgres actually accepts."""
    column = Column("flag", Boolean, default=True)
    ddl = column.type.compile(dialect=postgresql.dialect())
    statement = f'ALTER TABLE "probe" ADD COLUMN "flag" {ddl}{_default_literal(column, postgresql.dialect())}'

    assert statement == 'ALTER TABLE "probe" ADD COLUMN "flag" BOOLEAN DEFAULT true'


def test_non_boolean_defaults_are_unchanged():
    """The fix is scoped to booleans; other types must behave as before."""
    assert _default_literal(Column("n", Integer, default=7), postgresql.dialect()) == " DEFAULT 7"
    assert (
        _default_literal(Column("s", Text, default="it's"), postgresql.dialect())
        == " DEFAULT 'it''s'"
    )
    assert _default_literal(Column("x", Text), postgresql.dialect()) == ""


def test_the_repair_is_idempotent(scratch_table):
    """Running twice must be safe, since create_all runs on every cold start."""
    _add_missing_columns()
    with engine.connect() as conn:
        first = _existing_columns(conn, scratch_table)

    _add_missing_columns()
    with engine.connect() as conn:
        second = _existing_columns(conn, scratch_table)

    assert first == second