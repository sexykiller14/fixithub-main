"""BSOD stop code lookup and the minidump analyzer."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import build_context, total_counts
from ..models import Article, DumpUpload, StopCode
from ..rate_limit import enforce, tool_limiter
from ..services import minidump as dump
from ..services import stopcodes as sc
from ..services.search import record_feedback
from ..security import client_ip
from ..templates import render

router = APIRouter()

# Read the upload in chunks so a large or lying Content-Length cannot exhaust memory.
CHUNK = 64 * 1024

# Sub-paths under /bsod that must never be treated as a stop code name.
RESERVED_BSOD_PATHS = {"lookup", "analyze", "feedback"}


@router.get("/bsod", name="bsod_index")
def bsod_index(request: Request, db: Session = Depends(get_db)):
    all_codes = sc.all_stop_codes(db)
    letters = sorted({code.name[0] for code in all_codes})
    context = build_context(
        request,
        db,
        nav_open="bsod",
        stop_codes=all_codes,
        letters=letters,
        counts=total_counts(db),
    )
    return render(request, "bsod_index.html", context)


@router.get("/bsod/lookup", name="bsod_lookup")
def bsod_lookup(
    request: Request,
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
):
    term = q.strip()
    found = sc.lookup(db, term) if len(term) >= 2 else None

    if found is not None:
        found.view_count += 1
        db.commit()
        return _render_stop_code(request, db, found)

    context = build_context(
        request,
        db,
        nav_open="bsod",
        q=term,
        suggestions=sc.search(db, term, limit=12) if len(term) >= 2 else [],
        counts=total_counts(db),
    )
    return render(request, "bsod_lookup.html", context)


@router.get("/bsod/analyze", name="bsod_analyze")
def analyze_form(request: Request, db: Session = Depends(get_db)):
    return render(
        request,
        "bsod_analyze.html",
        build_context(
            request,
            db,
            nav_open="bsod",
            max_upload_mb=settings.max_upload_bytes // 1024 // 1024,
            counts=total_counts(db),
        ),
    )


@router.get("/bsod/{name}", name="bsod_detail")
def bsod_detail(request: Request, name: str, db: Session = Depends(get_db)):
    # Reject oversized input and anything containing path or query characters
    # before touching the database.
    if len(name) > 120 or any(ch in name for ch in "/\\.?&#"):
        return _not_found(request, db, name[:60])

    # Reserved sub-paths have their own routes; this one is a fallback only.
    if name.lower() in RESERVED_BSOD_PATHS:
        return _not_found(request, db, name)

    found = db.scalar(
        select(StopCode).where(func.upper(StopCode.name) == sc.normalise_query(name))
    )
    if found is None:
        return _not_found(request, db, name)

    found.view_count += 1
    db.commit()
    return _render_stop_code(request, db, found)


def _not_found(request: Request, db: Session, name: str):
    return render(
        request,
        "404.html",
        build_context(
            request,
            db,
            nav_open="bsod",
            robots="noindex, nofollow",
            status_code=404,
            error_title="Stop code not found",
            error_message=(
                f"We do not have a guide for '{name}'. "
                "Try the lookup with its hex value instead."
            ),
        ),
        status_code=404,
    )


def _render_stop_code(request: Request, db: Session, code: StopCode):
    related = []
    for slug in code.related_slugs or []:
        article = db.scalar(select(Article).where(Article.slug == slug))
        if article is not None:
            related.append(article)

    siblings = list(
        db.execute(
            select(StopCode)
            .where(
                StopCode.id != code.id,
                StopCode.code_uint.between(
                    max(0, code.code_uint - 0x30), code.code_uint + 0x30
                ),
            )
            .order_by(StopCode.code_uint)
            .limit(6)
        ).scalars()
    )

    context = build_context(
        request,
        db,
        nav_open="bsod",
        code=code,
        related=related,
        siblings=siblings,
        counts=total_counts(db),
    )
    return render(request, "bsod_detail.html", context)


@router.post("/bsod/{name}/feedback", name="bsod_feedback")
def bsod_feedback(
    request: Request,
    name: str,
    helpful: bool = Query(False),
    comment: str = Query("", max_length=500),
    db: Session = Depends(get_db),
):
    from fastapi.responses import RedirectResponse

    from ..rate_limit import feedback_limiter

    limited = enforce(
        request,
        feedback_limiter,
        prefix="feedback",
        message="Too many submissions. Please try again shortly.",
    )
    if limited is not None:
        return limited

    code = db.scalar(select(StopCode).where(func.upper(StopCode.name) == sc.normalise_query(name)))
    if code is not None:
        record_feedback(db, "stop_code", code.id, bool(helpful), comment, client_ip(request))
    return RedirectResponse(f"/bsod/{name}?thanks=1", status_code=303)


# ---------------------------------------------------------------------------
# Minidump analyzer
# ---------------------------------------------------------------------------


@router.post("/bsod/analyze", name="bsod_analyze_post")
async def analyze_upload(
    request: Request,
    dump_file: UploadFile = File(..., alias="dump_file"),
    db: Session = Depends(get_db),
):
    limited = enforce(
        request,
        tool_limiter,
        prefix="dump",
        message=(
            "Rate limit reached for minidump uploads. "
            "Please wait before uploading another file."
        ),
    )
    if limited is not None:
        return limited

    # Reject oversized files on the declared length before reading anything.
    if dump_file.size and dump_file.size > settings.max_upload_bytes:
        return _analysis_error(
            request,
            db,
            f"That file is {dump_file.size / 1024 / 1024:.1f} MB. "
            f"The limit is {settings.max_upload_bytes // 1024 // 1024} MB.",
        )

    try:
        filename = dump_file.filename or "upload.dmp"
        size = dump_file.size or 0

        buffer = bytearray()
        total = 0
        while True:
            chunk = await dump_file.read(CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.max_upload_bytes:
                # Stop reading as soon as the cap is passed.
                return _analysis_error(
                    request,
                    db,
                    f"That file is larger than the "
                    f"{settings.max_upload_bytes // 1024 // 1024} MB limit.",
                )
            buffer.extend(chunk)

        data = bytes(buffer)
        size = len(data)
    finally:
        await dump_file.close()

    try:
        analysis = await asyncio.to_thread(
            dump.analyse, data, filename, settings.max_upload_bytes
        )
    except dump.DumpError as exc:
        db.add(
            DumpUpload(
                filename=(filename or "upload.dmp")[:260],
                size_bytes=size,
                signature="",
                bugcheck_code="",
                parsed_ok=False,
                message=str(exc)[:400],
            )
        )
        db.commit()
        return _analysis_error(request, db, str(exc))
    except Exception as exc:  # noqa: BLE001 - never leak a parser traceback
        db.add(
            DumpUpload(
                filename=(filename or "upload.dmp")[:260],
                size_bytes=size,
                signature="",
                bugcheck_code="",
                parsed_ok=False,
                message=f"Parser error: {type(exc).__name__}"[:400],
            )
        )
        db.commit()
        return _analysis_error(
            request,
            db,
            "The file has a valid dump signature but could not be parsed. "
            "If it is a kernel dump rather than a small minidump, open it in "
            "WinDbg instead.",
        )

    bugcheck = analysis.bugcheck
    db.add(
        DumpUpload(
            filename=analysis.filename,
            size_bytes=analysis.size_bytes,
            signature=analysis.signature,
            bugcheck_code=bugcheck.hex_code if bugcheck else "",
            parsed_ok=bugcheck is not None,
            message="; ".join(analysis.notes)[:400],
            os_build=bugcheck.os_build if bugcheck else "",
        )
    )
    db.commit()

    matched = None
    if bugcheck is not None:
        matched = db.scalar(select(StopCode).where(StopCode.code_uint == bugcheck.code))

    related = []
    if matched is not None:
        for slug in matched.related_slugs or []:
            article = db.scalar(select(Article).where(Article.slug == slug))
            if article is not None:
                related.append(article)
    else:
        related = list(
            db.execute(
                select(Article).order_by(Article.is_featured.desc()).limit(3)
            ).scalars()
        )

    context = build_context(
        request,
        db,
        nav_open="bsod",
        robots="noindex, nofollow",
        analysis=analysis,
        matched=matched,
        related=related,
        max_upload_mb=settings.max_upload_bytes // 1024 // 1024,
        counts=total_counts(db),
    )
    return render(request, "bsod_result.html", context)


def _analysis_error(request: Request, db: Session, message: str):
    return render(
        request,
        "bsod_analyze.html",
        build_context(
            request,
            db,
            nav_open="bsod",
            robots="noindex, nofollow",
            analysis_error=message,
            max_upload_mb=settings.max_upload_bytes // 1024 // 1024,
            counts=total_counts(db),
        ),
        status_code=400,
    )


@router.get("/api/dump/validate", name="dump_validate")
def dump_validate(request: Request):
    """Report the limits, so the UI can state them without hard-coding values."""
    return {
        "ok": True,
        "max_bytes": settings.max_upload_bytes,
        "max_mb": settings.max_upload_bytes // 1024 // 1024,
        "signatures": ["PMDMP", "PAGEDU", "PAGE", "FULL"],
    }
