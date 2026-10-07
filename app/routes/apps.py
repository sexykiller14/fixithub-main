"""Public pages for admin-uploaded application binaries."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import USER_SESSION_COOKIE, settings
from ..db import get_db
from ..deps import build_context, total_counts
from ..models import AppDownload, Article
from ..services.accounts import current_user
from ..services.apps import (
    file_present,
    image_content_type,
    read_binary,
    read_image,
    stored_path,
)
from ..templates import render

from .accounts import redirect_to_login
from .comments import TARGET_APP, comment_context

log = logging.getLogger(__name__)

router = APIRouter()


def _local_path_for_image(filename: str):
    """The on-disk path for a screenshot, or None when storage is remote.

    Separate from the bytes fetch above because a local screenshot can be
    streamed by path, and reading a 4 MB image into a lambda to serve it is
    wasteful when the file is already sitting on disk.
    """
    from ..services.apps import stored_image_path

    return stored_image_path(filename)

CATEGORIES_FOR_APPS = {
    "hardware": "Hardware",
    "network": "Network",
    "windows": "Windows",
    "drivers": "Drivers",
}


@router.get("/apps", name="apps_index")
def apps_index(request: Request, db: Session = Depends(get_db)):
    apps = list(
        db.execute(
            select(AppDownload)
            .where(AppDownload.is_published.is_(True))
            .order_by(AppDownload.category, AppDownload.title)
        ).scalars()
    )

    context = build_context(
        request,
        db,
        nav_open="apps",
        apps=apps,
        app_categories=CATEGORIES_FOR_APPS,
        counts=total_counts(db),
    )
    return render(request, "apps_index.html", context)


@router.get("/apps/{slug}", name="app_detail")
def app_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    app = db.scalar(
        select(AppDownload).where(
            AppDownload.slug == slug.lower(), AppDownload.is_published.is_(True)
        )
    )
    if app is None:
        return render(
            request,
            "404.html",
            build_context(
                request,
                db,
                nav_open="apps",
                robots="noindex, nofollow",
                status_code=404,
                error_title="Download not found",
                error_message=f"No published download named '{slug}' exists.",
            ),
            status_code=404,
        )

    # Recomputed so a file that changed on disk is reported here rather than
    # quietly handed to a visitor.
    integrity = app.integrity_ok()

    related = list(
        db.execute(
            select(Article)
            .where(Article.category == app.category)
            .order_by(Article.is_featured.desc(), Article.title)
            .limit(4)
        ).scalars()
    )

    # The service takes (db, raw_token); the route-level helper in
    # .accounts takes (request, db). Use the service form here.
    reader = current_user(db, request.cookies.get(USER_SESSION_COOKIE))

    context = build_context(
        request,
        db,
        nav_open="apps",
        app=app,
        integrity=integrity,
        file_present=file_present(app.filename),
        related=related,
        reader=reader,
        download_locked=reader is None or not reader.is_verified,
        registration_open=settings.allow_registration,
        counts=total_counts(db),
        **comment_context(request, db, TARGET_APP, app.id),
    )
    return render(request, "app_detail.html", context)


@router.get("/apps/{slug}/screenshot")
def app_screenshot(request: Request, slug: str, db: Session = Depends(get_db)):
    """Serve a tool's screenshot.

    Deliberately not a static file: /static is world-readable and these are
    uploaded by an admin, so they are gated the same way the binaries are. Only
    a published app has one served, and an unpublished or missing file is a
    plain 404 with no detail, so the route cannot be used to probe for slugs.
    """
    app = db.scalar(
        select(AppDownload).where(
            AppDownload.slug == slug.lower(), AppDownload.is_published.is_(True)
        )
    )
    if app is None or not app.has_screenshot:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not found")

    data: bytes | None = read_image(app.screenshot_filename)
    if data is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Not found")

    headers = {
        "X-Content-Type-Options": "nosniff",
        # The image is data, not a document. sandbox stops it being treated
        # as one even if a future upload somehow carried markup.
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "public, max-age=3600",
    }
    # Local files are streamed from disk rather than read into memory; only
    # remote storage has to buffer, because there is no path to hand over.
    local = _local_path_for_image(app.screenshot_filename)
    if local is not None:
        return FileResponse(
            path=local,
            media_type=image_content_type(app.screenshot_filename),
            headers=headers,
        )
    return Response(
        content=data,
        media_type=image_content_type(app.screenshot_filename),
        headers=headers,
    )


@router.get("/apps/{slug}/download")
def app_download(request: Request, slug: str, db: Session = Depends(get_db)):
    """Serve the binary. Requires a confirmed account.

    The visitor is sent to sign in rather than shown a refusal, and an
    unconfirmed account is told to check its email, so the reason is never a
    dead end. The vendor's own page stays reachable from the detail view, which
    is deliberately not behind the wall.
    """
    reader = current_user(db, request.cookies.get(USER_SESSION_COOKIE))
    if reader is None:
        return redirect_to_login(request)
    if not reader.is_verified:
        return RedirectResponse(f"/account?verify=needed", status_code=303)

    app = db.scalar(
        select(AppDownload).where(
            AppDownload.slug == slug.lower(), AppDownload.is_published.is_(True)
        )
    )
    if app is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Download not found")

    path = stored_path(app.filename)
    data: bytes | None = None
    if path is None:
        # No local path. Either the file is in remote storage, or it is not
        # there at all, and those are told apart by actually reading it.
        data = read_binary(app.filename)
        if data is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="File missing")

    # The whole point of recording a hash is to notice when the file no longer
    # matches, so refuse rather than serve something we cannot vouch for.
    if app.integrity_ok() is not True:
        log.error("Checksum mismatch or unverifiable for %s", app.slug)
        from fastapi import HTTPException

        raise HTTPException(
            status_code=409,
            detail="This file's checksum does not match what was recorded at upload",
        )

    app.download_count += 1
    db.commit()

    # Sent as an attachment with an opaque content type so the browser saves it.
    # A Content-Disposition of attachment is what stops any chance of the file
    # being rendered or executed in the context of this site.
    headers = {
        "Content-Disposition": f'attachment; filename="{app.filename}"',
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
        "Cache-Control": "public, max-age=3600",
        "X-Checksum-Sha256": app.sha256,
    }
    if path is not None:
        return FileResponse(
            path=path,
            media_type="application/octet-stream",
            filename=app.filename,
            headers=headers,
        )
    return Response(
        content=data or b"",
        media_type="application/octet-stream",
        headers=headers,
    )