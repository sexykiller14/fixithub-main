"""Shared template context helpers."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import (
    CATEGORIES,
    DIFFICULTY_LABELS,
    SITE_AUTHOR,
    SITE_DESCRIPTION,
    SITE_NAME,
    SITE_TAGLINE,
    SITE_URL,
    USER_SESSION_COOKIE,
)
from .models import Article, StopCode


def build_context(request: Request, db: Session, **extra) -> dict:
    """Common values every template needs."""
    from .config import settings
    from .security import reader_csrf

    categories = CATEGORIES
    context = {
        "request": request,
        # Every reader-facing form uses this. Seeded here because a first visit
        # has no session cookie, so the anchor has to be created before the
        # template can render a token that will match on submit.
        "csrf": reader_csrf(request),
        # Resolved here so the header can show account state on every page.
        # A route that passes its own current_user overrides this.
        "current_user": _signed_in_reader(request, db),
        "registration_open": settings.allow_registration,
        "site_name": SITE_NAME,
        "site_tagline": SITE_TAGLINE,
        "site_description": SITE_DESCRIPTION,
        "site_author": SITE_AUTHOR,
        "site_url": SITE_URL,
        "canonical_url": str(request.url).split("?")[0],
        "categories": categories,
        "category_names": {key: value["name"] for key, value in categories.items()},
        "difficulty_labels": DIFFICULTY_LABELS,
        "current_path": request.url.path,
        "nav_open": extra.pop("nav_open", ""),
        "footer_categories": categories,
    }
    context.update(extra)
    return context


def _signed_in_reader(request: Request, db: Session):
    """The signed-in reader, or None.

    Imported lazily because the accounts service imports from here indirectly,
    and a module-level import would be circular. The cost is one indexed lookup
    of a hashed token per page render.
    """
    from .services.accounts import current_user

    return current_user(db, request.cookies.get(USER_SESSION_COOKIE))


def category_counts(db: Session) -> dict[str, int]:
    """Article counts per category, for the home page cards."""
    counts: dict[str, int] = {key: 0 for key in CATEGORIES}
    rows = db.execute(select(Article.category)).all()
    for (category,) in rows:
        if category in counts:
            counts[category] += 1
    return counts


def popular_articles(db: Session, limit: int = 6) -> list[Article]:
    """Featured articles first, then most viewed."""
    from sqlalchemy import or_

    return list(
        db.execute(
            select(Article)
            .where(or_(Article.is_featured.is_(True), Article.view_count > 0))
            .order_by(Article.is_featured.desc(), Article.view_count.desc(), Article.title)
            .limit(limit)
        ).scalars()
    )


def recent_articles(db: Session, limit: int = 6) -> list[Article]:
    return list(
        db.execute(
            select(Article).order_by(Article.created_at.desc(), Article.id.desc()).limit(limit)
        ).scalars()
    )


def popular_stop_codes(db: Session, limit: int = 6) -> list[StopCode]:
    return list(
        db.execute(
            select(StopCode)
            .order_by(StopCode.view_count.desc(), StopCode.code_uint)
            .limit(limit)
        ).scalars()
    )


def total_counts(db: Session) -> dict[str, int]:
    from .security import admin_configured

    return {
        "articles": db.query(Article).count(),
        "stop_codes": db.query(StopCode).count(),
        "admin_configured": admin_configured(),
    }
