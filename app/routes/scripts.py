"""Downloadable diagnostic scripts: listing, detail pages and downloads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import build_context, total_counts
from ..models import Article
from ..services.scripts_catalog import get_script, list_scripts, script_path
from ..templates import render

router = APIRouter()


@router.get("/scripts", name="scripts_index")
def scripts_index(request: Request, db: Session = Depends(get_db)):
    context = build_context(
        request,
        db,
        nav_open="scripts",
        scripts=list_scripts(),
        counts=total_counts(db),
    )
    return render(request, "scripts_index.html", context)


@router.get("/scripts/{slug}", name="script_detail")
def script_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    entry = get_script(slug)
    if entry is None:
        return render(
            request,
            "404.html",
            build_context(
                request,
                db,
                nav_open="scripts",
                robots="noindex, nofollow",
                status_code=404,
                error_title="Script not found",
                error_message=f"No diagnostic script exists with the name '{slug}'.",
            ),
            status_code=404,
        )

    related = []
    for article_slug in entry.info.related_slugs:
        article = db.scalar(select(Article).where(Article.slug == article_slug))
        if article is not None:
            related.append(article)

    context = build_context(
        request,
        db,
        nav_open="scripts",
        script=entry.info,
        source=entry.source,
        how_to_run=entry.info.how_to_run(),
        related=related,
        counts=total_counts(db),
    )
    return render(request, "script_detail.html", context)


@router.get("/scripts/{slug}/download")
def script_download(request: Request, slug: str):
    entry = get_script(slug)
    if entry is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Script not found")

    path = script_path(slug)
    if path is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Script file missing")

    # Sent as an attachment with a plain content type so browsers save rather
    # than execute it. Nothing on the server ever runs a downloaded script.
    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename=entry.info.filename,
        headers={
            "Content-Disposition": f'attachment; filename="{entry.info.filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=3600",
        },
    )
