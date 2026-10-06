"""Site search across articles and stop codes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import build_context, total_counts
from ..services.search import combined_search
from ..templates import render

router = APIRouter()

MAX_SUGGESTIONS = 8


@router.get("/search", name="search")
def search(
    request: Request,
    q: str = Query("", max_length=200),
    db: Session = Depends(get_db),
):
    term = q.strip()
    results: dict = {"query": term, "articles": [], "stop_codes": [], "total": 0}
    error = ""

    if term:
        if len(term) < 2:
            error = "Enter at least two characters."
        else:
            results = combined_search(db, term, limit=25)

    context = build_context(
        request,
        db,
        nav_open="",
        robots="noindex, follow",
        q=term,
        results=results,
        search_error=error,
        counts=total_counts(db),
    )
    return render(request, "search.html", context)


@router.get("/api/search/suggest", name="search_suggest")
def suggest(
    request: Request,
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
):
    """Typeahead suggestions for the search box."""
    from ..services.search import search_articles, search_stop_codes

    term = q.strip()
    if len(term) < 2:
        return {"ok": True, "suggestions": []}

    articles, _ = search_articles(db, term, limit=MAX_SUGGESTIONS)
    codes = search_stop_codes(db, term, limit=MAX_SUGGESTIONS)

    suggestions = [
        {
            "type": "stop_code",
            "label": f"{code.name} ({code.short_hex})",
            "url": f"/bsod/{code.name}",
        }
        for code in codes
    ]
    suggestions.extend(
        {
            "type": "article",
            "label": article.title,
            "url": f"/articles/{article.slug}",
        }
        for article in articles
    )
    return {"ok": True, "suggestions": suggestions[:MAX_SUGGESTIONS * 2]}
