#!/usr/bin/env python
"""Seed the FixIT Hub database and set the admin password.

Usage
-----
    python seed.py                          # load articles and stop codes
    python seed.py --rebuild-search         # also rebuild the full-text index
    python seed.py --set-admin-password "pw"
    python seed.py --reset                  # drop everything and reload
    python seed.py --check                  # report what is in the database

Stop codes come from data/bsod_codes.json and articles from content/*.md.
Both are upserted, so running this repeatedly is safe.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

from app.config import DATA_DIR
from app.db import create_all, engine, search, session_scope
from app.models import Article, StopCode
from app.security import hash_password, save_admin_hash
from app.services.content import load_all_articles, render_article
from app.services.stopcodes import load_stop_codes_file, sync_stop_codes


def _log(message: str) -> None:
    print(f"  {message}")


def load_articles() -> int:
    """Upsert every markdown article into the database."""
    sources = load_all_articles()
    if not sources:
        _log("No articles found in content/")
        return 0

    written = 0
    with session_scope() as db:
        for source in sources:
            rendered = render_article(source.body)
            article = db.query(Article).filter(Article.slug == source.slug).first()
            if article is None:
                article = Article(slug=source.slug)
                db.add(article)
            article.title = source.title
            article.category = source.category
            article.tags = source.tags
            article.difficulty = source.difficulty
            article.os_version = source.os_version
            article.summary = source.summary
            article.body = source.body
            article.reading_time = rendered.reading_time
            article.source_path = source.source_path
            article.is_featured = source.featured
            article.status = "draft" if source.draft else "published"
            written += 1

    by_category: dict[str, int] = {}
    for source in sources:
        by_category[source.category] = by_category.get(source.category, 0) + 1
    detail = ", ".join(f"{count} {name}" for name, count in sorted(by_category.items()))
    _log(f"{written} articles ({detail})")
    return written


def load_stop_codes() -> int:
    """Upsert every stop code from the JSON data file."""
    seeds = load_stop_codes_file()
    with session_scope() as db:
        written = sync_stop_codes(db, seeds)
    _log(f"{written} stop codes")
    return written


def rebuild_search() -> None:
    search.rebuild()
    _log("Full-text search index rebuilt")


def reset_database() -> None:
    from app.models import Base

    _log("Dropping every table")
    Base.metadata.drop_all(bind=engine)
    _log("Recreating tables")
    create_all()


def set_admin_password(password: str | None) -> int:
    if password is None:
        try:
            password = getpass.getpass("New admin password: ")
            confirm = getpass.getpass("Confirm password: ")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return 1
        if password != confirm:
            _log("Passwords did not match.")
            return 1

    if not password or len(password) < 8:
        _log("Use at least 8 characters.")
        return 1

    # Guard against an env var silently overriding the stored hash later.
    if os.environ.get("FIXITHUB_ADMIN_PASSWORD_HASH"):
        _log(
            "Note: FIXITHUB_ADMIN_PASSWORD_HASH is set in this environment and "
            "takes priority over the saved file."
        )

    save_admin_hash(hash_password(password))
    _log(f"Admin password saved to {DATA_DIR / 'admin.json'} (bcrypt, cost 12)")
    return 0


def report() -> int:
    from sqlalchemy import func, select

    with session_scope() as db:
        articles = db.scalar(select(func.count(Article.id))) or 0
        codes = db.scalar(select(func.count(StopCode.id))) or 0

        by_category = dict(
            db.execute(select(Article.category, func.count(Article.id)).group_by(Article.category)).all()
        )
        by_difficulty = dict(
            db.execute(
                select(Article.difficulty, func.count(Article.id)).group_by(Article.difficulty)
            ).all()
        )

    print()
    print("Database contents")
    print("-----------------")
    _log(f"articles   {articles}")
    for name, count in sorted(by_category.items()):
        _log(f"  {name:<12} {count}")
    _log(f"stop codes {codes}")
    for name, count in sorted(by_difficulty.items()):
        _log(f"  {name:<12} {count}")

    from app.security import admin_configured

    _log(f"admin password {'configured' if admin_configured() else 'NOT set'}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed.py",
        description="Load FixIT Hub content into SQLite.",
    )
    parser.add_argument(
        "--set-admin-password",
        nargs="?",
        const="",
        metavar="PASSWORD",
        help="Hash and store the admin password. Omit the value to be prompted.",
    )
    parser.add_argument(
        "--rebuild-search",
        action="store_true",
        help="Rebuild the SQLite FTS5 index after loading.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables before loading. Destroys view counts and feedback.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print what is currently in the database, then exit.",
    )
    parser.add_argument(
        "--no-content",
        action="store_true",
        help="Only load stop codes, skip the markdown articles.",
    )

    args = parser.parse_args(argv)

    print()
    print("FixIT Hub - database seeding")
    print("-----------------------------")

    if args.check:
        return report()

    create_all()

    if args.reset:
        reset_database()

    if args.no_content:
        load_stop_codes()
    else:
        load_articles()
        load_stop_codes()

    if args.rebuild_search or not search.use_fts:
        rebuild_search()
    else:
        _log("Search index is kept in step automatically; use --rebuild-search to force a rebuild")

    if args.set_admin_password is not None:
        password = args.set_admin_password or None
        set_admin_password(password)

    return 0


if __name__ == "__main__":
    sys.exit(main())
