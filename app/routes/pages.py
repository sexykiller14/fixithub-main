"""Home page, category listings and static pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import CATEGORIES
from ..db import get_db
from ..deps import build_context, category_counts, popular_articles, popular_stop_codes, recent_articles, total_counts
from ..models import Article
from ..services.wizards import list_wizards
from ..templates import render

router = APIRouter()


@router.get("/", name="home")
def home(request: Request, db: Session = Depends(get_db)):
    context = build_context(
        request,
        db,
        nav_open="home",
        category_counts=category_counts(db),
        popular=popular_articles(db, 6),
        recent=recent_articles(db, 6),
        popular_codes=popular_stop_codes(db, 6),
        wizards=list_wizards(),
        counts=total_counts(db),
    )
    return render(request, "home.html", context)


@router.get("/category/{slug}", name="category")
def category(request: Request, slug: str, db: Session = Depends(get_db)):
    if slug not in CATEGORIES:
        return RedirectResponse("/articles", status_code=301)

    articles = list(
        db.execute(
            select(Article)
            .where(Article.category == slug)
            .order_by(Article.is_featured.desc(), Article.title)
        ).scalars()
    )

    difficulties: dict[str, int] = {}
    for article in articles:
        difficulties[article.difficulty] = difficulties.get(article.difficulty, 0) + 1

    context = build_context(
        request,
        db,
        nav_open="articles",
        active_category=slug,
        category_meta=CATEGORIES[slug],
        articles=articles,
        difficulties=difficulties,
        category_counts=category_counts(db),
        counts=total_counts(db),
    )
    return render(request, "category.html", context)


@router.get("/about", name="about")
def about(request: Request, db: Session = Depends(get_db)):
    context = build_context(
        request,
        db,
        nav_open="",
        counts=total_counts(db),
        category_counts=category_counts(db),
    )
    return render(request, "about.html", context)


@router.get("/privacy", name="privacy")
def privacy(request: Request, db: Session = Depends(get_db)):
    """Privacy notice.

    Reachable without an account, because the point of it is that a reader can
    see exactly what signing up would involve before they sign up.
    """
    context = build_context(
        request,
        db,
        nav_open="",
        counts=total_counts(db),
        category_counts=category_counts(db),
    )
    return render(request, "privacy.html", context)
