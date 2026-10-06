"""Article listing, detail pages and helpfulness feedback."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import CATEGORIES, USER_SESSION_COOKIE, settings
from ..db import get_db
from ..deps import build_context, category_counts, total_counts
from ..models import Article, ArticleView
from ..rate_limit import enforce, feedback_limiter
from ..security import client_ip
from ..services.accounts import current_user
from ..services.content import load_all_articles, related_by_tags
from ..services.search import record_feedback
from ..services.markdown import render as render_markdown
from ..templates import render

router = APIRouter()


def record_view(db: Session, article: Article) -> None:
    """Record a view in the per-day counter and bump the lifetime total."""
    today = date.today().isoformat()
    row = db.scalar(
        select(ArticleView).where(
            ArticleView.article_id == article.id, ArticleView.view_date == today
        )
    )
    if row is None:
        db.add(ArticleView(article_id=article.id, view_date=today, views=1))
    else:
        row.views += 1
    article.view_count += 1
    db.commit()


@router.get("/articles", name="articles")
def articles_index(
    request: Request,
    q: str = Query("", max_length=200),
    category: str = Query("", max_length=50),
    difficulty: str = Query("", max_length=20),
    db: Session = Depends(get_db),
):
    term = q.strip()
    if term:
        # A keyword filter narrows the full result set rather than paging it.
        from ..services.search import search_articles

        found, _ = search_articles(db, term, category=category if category in CATEGORIES else None, limit=200)
        if difficulty in {"easy", "moderate", "hard", "advanced"}:
            found = [a for a in found if a.difficulty == difficulty]
        rows = found
    else:
        query = select(Article)
        if category in CATEGORIES:
            query = query.where(Article.category == category)
        if difficulty in {"easy", "moderate", "hard", "advanced"}:
            query = query.where(Article.difficulty == difficulty)
        rows = list(
            db.execute(
                query.order_by(
                    Article.is_featured.desc(), func.lower(Article.title)
                )
            ).scalars()
        )

    counts: dict[str, int] = {}
    for article in db.execute(select(Article.category)).all():
        counts[article[0]] = counts.get(article[0], 0) + 1

    difficulty_counts: dict[str, int] = {}
    for value, amount in db.execute(
        select(Article.difficulty, func.count(Article.id)).group_by(Article.difficulty)
    ):
        difficulty_counts[value] = amount

    context = build_context(
        request,
        db,
        nav_open="articles",
        articles=rows,
        active_category=category if category in CATEGORIES else "",
        active_difficulty=difficulty,
        q=term,
        category_counts=counts,
        difficulty_counts=difficulty_counts,
        counts=total_counts(db),
    )
    return render(request, "articles.html", context)


@router.get("/articles/{slug}", name="article_detail")
def article_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    article = db.scalar(select(Article).where(Article.slug == slug))
    if article is None:
        return render(
            request,
            "404.html",
            build_context(
                request,
                db,
                nav_open="articles",
                status_code=404,
                error_title="Article not found",
                error_message=f"No article exists with the name '{slug}'.",
            ),
            status_code=404,
        )

    record_view(db, article)

    rendered = render_markdown(article.body)

    # A unit placed "inside-content" is injected at the Nth paragraph rather
    # than stacked under the article, which is the point of that placement.
    from ..services.ads import inject_inside_content

    ads_config = None
    try:
        from ..db import SessionLocal
        from ..models import AdSettings, AdUnit
        from ..services.ads import render_unit, push_script, unit_matches_page

        with SessionLocal() as db2:
            cfg = db2.query(AdSettings).first()
            if cfg is not None and cfg.enabled and cfg.publisher_id:
                ads_config = cfg
                inside_units = (
                    db2.query(AdUnit)
                    .filter(AdUnit.enabled.is_(True), AdUnit.placement == "inside-content")
                    .order_by(AdUnit.created_at)
                    .all()
                )
                for unit in inside_units:
                    if unit_matches_page(unit, request.url.path, False, True):
                        rendered.html = inject_inside_content(
                            rendered.html,
                            render_unit(unit, cfg.publisher_id) + push_script(unit),
                            unit.nth_paragraph,
                        )
    except Exception:  # noqa: BLE001 - a broken ad config must not lose the article
        pass

    pool = [source for source in load_all_articles()]
    stub = _stub_from_row(article)
    related = related_by_tags(stub, pool, limit=4)
    related_rows = []
    for item in related:
        row = db.scalar(select(Article).where(Article.slug == item.slug))
        if row is not None:
            related_rows.append(row)
    if not related_rows:
        related_rows = list(
            db.execute(
                select(Article)
                .where(Article.category == article.category, Article.id != article.id)
                .order_by(Article.view_count.desc())
                .limit(4)
            ).scalars()
        )

    from .comments import TARGET_ARTICLE, comment_context

    context = build_context(
        request,
        db,
        nav_open="articles",
        article=article,
        rendered=rendered,
        toc=rendered.toc,
        related=related_rows,
        category_meta=CATEGORIES.get(article.category, CATEGORIES["windows"]),
        counts=total_counts(db),
        current_user=current_user(db, request.cookies.get(USER_SESSION_COOKIE)),
        registration_open=settings.allow_registration,
        **comment_context(request, db, TARGET_ARTICLE, article.id),
    )
    return render(request, "article.html", context)


def _stub_from_row(article: Article):
    """Adapt a database row into the shape related_by_tags expects."""
    from ..services.content import ArticleSource

    return ArticleSource(
        slug=article.slug,
        title=article.title,
        category=article.category,
        summary=article.summary,
        tags=article.tags or [],
        difficulty=article.difficulty,
        os_version=article.os_version,
        featured=article.is_featured,
        body=article.body,
    )


@router.post("/articles/{slug}/feedback", name="article_feedback")
def article_feedback(
    request: Request,
    slug: str,
    helpful: bool = Form(False),
    comment: str = Form("", max_length=500),
    db: Session = Depends(get_db),
):
    limited = enforce(
        request,
        feedback_limiter,
        prefix="feedback",
        message="Too many feedback submissions. Please try again in a few minutes.",
    )
    if limited is not None:
        return limited

    article = db.scalar(select(Article).where(Article.slug == slug))
    if article is None:
        return RedirectResponse("/articles", status_code=303)

    record_feedback(db, "article", article.id, bool(helpful), comment, client_ip(request))
    return RedirectResponse(f"/articles/{slug}?thanks=1", status_code=303)
