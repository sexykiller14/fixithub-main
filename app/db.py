"""Database engine, session handling and full-text search setup."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import NoSuchTableError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

log = logging.getLogger(__name__)

_is_sqlite = settings.database_url.startswith("sqlite")

engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 15} if _is_sqlite else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _record) -> None:  # pragma: no cover
    """Enable WAL + foreign keys for SQLite connections."""
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for scripts and background jobs."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_all() -> None:
    """Create any missing tables, then add any missing columns.

    ``create_all`` on its own only ever creates whole tables. A column added to
    a model afterwards is invisible to an existing database, so the app then
    fails on the first query that selects it. This project has no migration
    tool, so the additive cases are handled here: a column that is declared in
    a model but absent from the table is added with a sensible default.

    Only additive changes are made. Nothing is dropped, renamed or retyped,
    because doing that to a live database without a migration framework risks
    data loss. A column whose definition genuinely cannot be added by ALTER
    TABLE is reported rather than guessed at.
    """
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _existing_columns(conn, table_name: str) -> set[str]:
    """Column names the live table already has.

    Read through SQLAlchemy's inspector rather than PRAGMA table_info, because
    PRAGMA is SQLite-only. The inspector speaks both dialects, which is what lets
    the same additive-migration loop run against Postgres on Vercel instead of
    silently skipping it.
    """
    try:
        return {col["name"] for col in inspect(conn).get_columns(table_name)}
    except (NoSuchTableError, SQLAlchemyError):
        # Table absent, or the connection cannot describe it. Either way there
        # is nothing to add to.
        return set()


def _add_missing_columns() -> None:
    """ALTER TABLE ... ADD COLUMN for every column a model declares and the
    table lacks.

    Runs on SQLite and Postgres alike. Only additive changes are made: nothing is
    dropped, renamed or retyped, so it is safe against a live database.
    """
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            existing = _existing_columns(conn, table.name)
            if not existing:
                # Freshly created by create_all, so it already has every column.
                continue
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = column.type.compile(dialect=conn.dialect)
                # A NOT NULL column can only be added with a default, otherwise
                # every existing row would violate it.
                default = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    rendered = column.default.arg
                    if isinstance(rendered, bool):
                        default = f" DEFAULT {1 if rendered else 0}"
                    elif isinstance(rendered, (int, float)):
                        default = f" DEFAULT {rendered}"
                    elif isinstance(rendered, str):
                        escaped = rendered.replace("'", "''")
                        default = f" DEFAULT '{escaped}'"
                log.info(
                    "Adding missing column %s.%s", table.name, column.name
                )
                conn.execute(
                    text(
                        f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                        f"{ddl}{default}"
                    )
                )
        conn.commit()


def fts_available() -> bool:
    """Check whether this SQLite build supports FTS5."""
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE VIRTUAL TABLE IF NOT EXISTS temp.fts_probe USING fts5(x)"))
            conn.execute(text("DROP TABLE IF EXISTS temp.fts_probe"))
        return True
    except Exception:
        return False


class ArticleSearch:
    """Full-text search over articles with a LIKE-based fallback.

    FTS5 is used when the SQLite build provides it (it gives ranking and
    prefix matching). Otherwise the same public API falls back to LIKE scans,
    which are slower but correct.
    """

    def __init__(self) -> None:
        self._fts_ready: bool | None = None

    @property
    def use_fts(self) -> bool:
        if self._fts_ready is None:
            self._fts_ready = fts_available()
            if not self._fts_ready:
                log.info("SQLite FTS5 unavailable; using LIKE fallback for search")
        return self._fts_ready

    def rebuild(self) -> None:
        """Rebuild the FTS index from the articles table."""
        if not self.use_fts:
            return
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS articles_fts"))
            conn.execute(
                text(
                    "CREATE VIRTUAL TABLE articles_fts USING fts5("
                    "title, summary, tags, category, body, content='articles', content_rowid='id')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO articles_fts(articles_fts) "
                    "VALUES('rebuild')"
                )
            )

    def query(self, term: str, limit: int = 20, category: str | None = None) -> list[tuple[int, float]]:
        """Return (article_id, rank) pairs, best match first."""
        cleaned = self._to_match_expression(term)
        if not cleaned:
            return []
        if self.use_fts:
            sql = text(
                "SELECT rowid, bm25(articles_fts, 10.0, 4.0, 6.0, 2.0, 1.0) AS rank "
                "FROM articles_fts WHERE articles_fts MATCH :match"
            )
            params: dict = {"match": cleaned, "limit": limit}
            sql_text = str(sql)
            if category:
                sql_text += " AND rowid IN (SELECT id FROM articles WHERE category = :category)"
                params["category"] = category
            sql_text += " ORDER BY rank LIMIT :limit"
            sql = text(sql_text)
            try:
                with engine.connect() as conn:
                    return [(int(r[0]), float(r[1])) for r in conn.execute(sql, params)]
            except Exception:
                log.warning("FTS query failed, falling back to LIKE", exc_info=True)
        return self._like_query(term, limit=limit, category=category)

    def _like_query(self, term: str, limit: int, category: str | None) -> list[tuple[int, float]]:
        like = f"%{term.lower()}%"
        sql = (
            "SELECT id, 0.0 AS rank FROM articles "
            "WHERE (lower(title) LIKE :like OR lower(summary) LIKE :like "
            "OR lower(cast(tags as text)) LIKE :like OR lower(body) LIKE :like "
            "OR lower(category) LIKE :like)"
        )
        params: dict = {"like": like}
        if category:
            sql += " AND category = :category"
            params["category"] = category
        sql += " ORDER BY is_featured DESC, view_count DESC LIMIT :limit"
        params["limit"] = limit
        with engine.connect() as conn:
            return [(int(r[0]), 0.0) for r in conn.execute(text(sql), params)]

    @staticmethod
    def _to_match_expression(term: str) -> str:
        """Turn user input into a safe FTS5 MATCH expression.

        Every token is stripped of FTS operators and quoted, so a user cannot
        inject column filters, NEAR expressions or boolean syntax.
        """
        tokens: list[str] = []
        for raw in term.replace('"', " ").split():
            cleaned = "".join(
                ch for ch in raw if ch.isalnum() or ch in "-_"
            ).strip("-_")
            if not cleaned:
                continue
            tokens.append(f'"{cleaned}"*' if len(cleaned) > 2 else f'"{cleaned}"')
        return " AND ".join(tokens)


search = ArticleSearch()


def seed_if_empty() -> None:
    """Populate articles and stop codes if the database is empty (e.g. cold start on Vercel)."""
    from sqlalchemy import func, select
    from .models import Article
    from .services.content import load_all_articles, render_article
    from .services.stopcodes import load_stop_codes_file, sync_stop_codes

    try:
        with session_scope() as db:
            count = db.scalar(select(func.count(Article.id))) or 0
            if count > 0:
                return

            log.info("Database is empty; automatically seeding content...")
            sources = load_all_articles()
            for source in sources:
                rendered = render_article(source.body)
                article = Article(
                    slug=source.slug,
                    title=source.title,
                    category=source.category,
                    tags=source.tags,
                    difficulty=source.difficulty,
                    os_version=source.os_version,
                    summary=source.summary,
                    body=source.body,
                    reading_time=rendered.reading_time,
                    source_path=source.source_path,
                    is_featured=source.featured,
                    status="draft" if source.draft else "published",
                )
                db.add(article)

            seeds = load_stop_codes_file()
            sync_stop_codes(db, seeds)

        search.rebuild()
        log.info("Automatic database seeding finished (%d articles).", len(sources))
    except Exception:
        log.exception("Automatic database seeding encountered an error")
