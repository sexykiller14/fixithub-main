"""Admin panel: password-protected CRUD for articles and stop codes."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import yaml
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session, joinedload

from ..config import CATEGORIES, CONTENT_DIR, DIFFICULTY_LABELS, settings
from ..db import create_all, engine, get_db, search
from ..deps import build_context, total_counts
from ..config import ADMIN_HASH_FILE
from ..rate_limit import enforce, password_limiter
from ..models import (
    AppDownload,
    Article,
    ArticleView,
    Comment,
    DumpUpload,
    Feedback,
    Question,
    SearchQuery,
    StopCode,
    User,
)
from ..services import apps
from ..services import audit, totp
from ..services.apps import (
    ALLOWED_IMAGE_SUFFIXES,
    ALLOWED_SUFFIXES,
    MAX_APP_BYTES,
    MAX_IMAGE_BYTES,
    AppUploadError,
)
from ..security import (
    CSRF_FIELD,
    SESSION_COOKIE,
    clear_login_failures,
    clear_session_cookie,
    client_ip,
    create_session_token,
    generate_csrf,
    hash_password,
    load_admin_hash,
    login_locked_out,
    record_login_failure,
    safe_link_url,
    save_admin_hash,
    set_session_cookie,
    valid_csrf,
    verify_password,
)
from ..services.content import load_article_file
from ..services.markdown import render as render_markdown
from ..services.search import feedback_summary, popular_searches, recent_feedback, zero_result_searches
from ..services.stopcodes import parse_code_hex
from ..templates import render

router = APIRouter()

log = logging.getLogger("fixithub.admin")


# ---------------------------------------------------------------- ads admin

MAX_BODY = 400_000

# An admin reply is read in the widget's status line, so it stays short. Longer
# answers belong in an article the reply can point at.
MAX_REPLY = 2000

# A backup archive holds the whole database. Read incrementally under this cap
# rather than buffering whatever the request sends.
MAX_RESTORE_BYTES = 200 * 1024 * 1024


def _read_capped(stream, limit: int) -> bytes | None:
    """Read at most limit bytes. Returns None if the stream is longer."""
    chunks: list[bytes] = []
    total = 0
    while True:
        block = stream.read(256 * 1024)
        if not block:
            break
        total += len(block)
        if total > limit:
            return None
        chunks.append(block)
    return b"".join(chunks)

# Which articles an uploaded app is most likely to sit beside.
APP_CATEGORIES = {
    "hardware": "Hardware",
    "network": "Network",
    "windows": "Windows",
    "drivers": "Drivers",
}


def current_session(request: Request):
    return request.cookies.get(SESSION_COOKIE)


def is_authenticated(request: Request) -> bool:
    from ..security import read_session_token

    return read_session_token(current_session(request)) is not None


def csrf_token(request: Request) -> str:
    token = current_session(request)
    return generate_csrf(token) if token else ""


def require_auth(request: Request) -> bool:
    return is_authenticated(request)


def guard_csrf(request: Request, submitted: str) -> bool:
    return valid_csrf(current_session(request), submitted)


def _sqlite_db_path() -> str | None:
    """The on-disk path of the SQLite file, or None on any other backend.

    engine.url.database is the path. str(engine.url) is not: SQLAlchemy
    percent-encodes the string form, so a Windows path arrives as
    "C%3A%5C...test.db" and every open() against it fails. Only SQLite has a
    file to find here, so a non-SQLite URL returns None and the backup and
    restore routes report that instead of writing to a garbage path.
    """
    url = engine.url
    if not url.drivername.startswith("sqlite"):
        return None
    database = url.database
    if not database or database == ":memory:":
        return None
    return str(database)


def admin_context(request: Request, db: Session, **extra):
    return build_context(
        request,
        db,
        nav_open="admin",
        csrf=csrf_token(request),
        categories=CATEGORIES,
        difficulty_labels=DIFFICULTY_LABELS,
        counts=total_counts(db),
        # Sidebar badges. setdefault rather than a merge: a route that passes
        # its own pending_comments still wins, and **extra after **badges would
        # otherwise be a duplicate-keyword TypeError.
        **{**_pending_counts(db), **extra},
    )


# The sidebar badges the two moderation queues. Two COUNT queries on every
# admin page, which is the cost of showing a count next to a nav link.
def _pending_counts(db: Session) -> dict:
    comments = db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(Comment.status == Comment.STATUS_PENDING)
    )
    questions = db.scalar(
        select(func.count())
        .select_from(Question)
        .where(Question.status == Question.STATUS_NEW)
    )
    return {"pending_comments": comments or 0, "pending_questions": questions or 0}


# ------------------------------------------------------------------- login


LOGIN_CSRF_COOKIE = "fixithub_login_csrf"

# Held between the password step and the second-factor step. Signed, so it
# cannot be forged, and short-lived, so an abandoned login cannot be resumed
# hours later. It carries no secrets: just which step has been completed and
# when.
PENDING_2FA_COOKIE = "fixithub_2fa_pending"
PENDING_2FA_MAX_AGE = 300  # 5 minutes to type a 6-digit code


def _mint_2fa_pending() -> str:
    from ..security import _serialiser

    return _serialiser.dumps({"stage": "2fa"}, salt="fixithub-2fa-pending")


def _has_valid_2fa_pending(request: Request) -> bool:
    from ..security import _serialiser

    cookie = request.cookies.get(PENDING_2FA_COOKIE)
    if not cookie:
        return False
    try:
        data = _serialiser.loads(cookie, salt="fixithub-2fa-pending", max_age=PENDING_2FA_MAX_AGE)
    except Exception:  # noqa: BLE001 - expired or forged
        return False
    return isinstance(data, dict) and data.get("stage") == "2fa"


def _mint_login_csrf() -> str:
    """Create a signed, short-lived CSRF token for the login form.

    The login form is reachable without a session, so its CSRF token lives in
    its own cookie rather than being derived from the admin session.
    """
    from ..security import _serialiser

    return _serialiser.dumps({"p": "login"}, salt="fixithub-login-csrf")


def _set_login_csrf_cookie(response, token: str) -> None:
    response.set_cookie(
        LOGIN_CSRF_COOKIE,
        token,
        max_age=1800,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def _login_csrf_valid(request: Request, submitted: str) -> bool:
    import hmac

    from ..security import _serialiser

    cookie = request.cookies.get(LOGIN_CSRF_COOKIE)
    if not cookie or not submitted:
        return False
    try:
        _serialiser.loads(cookie, salt="fixithub-login-csrf", max_age=1800)
    except Exception:  # noqa: BLE001 - expired or forged cookie
        return False
    # The token value is the cookie itself, so compare them directly.
    return hmac.compare_digest(cookie, submitted)


@router.get("/admin", name="admin_login")
def admin_login(request: Request, db: Session = Depends(get_db)):
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=303)

    stored = load_admin_hash()
    token = _mint_login_csrf()
    response = render(
        request,
        "admin_login.html",
        admin_context(
            request,
            db,
            error=(
                ""
                if stored
                else "No admin password is set. Run: python seed.py --set-admin-password"
            ),
            not_configured=not stored,
            login_error="",
            login_csrf=token,
        ),
    )
    _set_login_csrf_cookie(response, token)
    return response


@router.post("/admin/login", name="admin_login_post")
def admin_login_post(
    request: Request,
    password: str = Form("", max_length=200),
    csrf: str = Form("", max_length=400),
    db: Session = Depends(get_db),
):
    stored = load_admin_hash()
    # client_ip, not request.client.host: behind a reverse proxy the latter is
    # the proxy's address, so every admin and every attacker would share one
    # lockout bucket. client_ip honours FIXITHUB_TRUST_PROXY like every other
    # rate-limited path in the app.
    identifier = client_ip(request)

    def back(error: str, login_error: str = "", code: int = 200):
        token = _mint_login_csrf()
        response = render(
            request,
            "admin_login.html",
            admin_context(
                request,
                db,
                error=error,
                not_configured=not stored,
                login_error=login_error,
                login_csrf=token,
            ),
            status_code=code,
        )
        _set_login_csrf_cookie(response, token)
        return response

    locked, retry_after = login_locked_out(identifier)
    if locked:
        return back(
            f"Too many failed attempts. Try again in {retry_after} seconds.",
            code=429,
        )

    if not _login_csrf_valid(request, csrf):
        return back("Your login form expired. Please try again.", code=400)

    if not stored:
        return back(
            "No admin password is configured. "
            "Run: python seed.py --set-admin-password",
            code=401,
        )

    if not verify_password(password, stored):
        record_login_failure(identifier)
        audit.record(
            db,
            "auth.login_failed",
            ip_hash=audit.hash_ip(identifier),
            detail=f"password rejected for {identifier}",
            commit=False,
        )
        db.commit()
        return back("", "Incorrect password.", code=401)

    clear_login_failures(identifier)

    # Second factor, if one is enrolled. The password has already been checked
    # at this point, so the pending cookie is only ever set after a correct
    # password - it is the "half authenticated" state, not a bypass.
    if _two_factor_required():
        response = RedirectResponse("/admin/login/2fa", status_code=303)
        response.set_cookie(
            PENDING_2FA_COOKIE,
            _mint_2fa_pending(),
            max_age=PENDING_2FA_MAX_AGE,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )
        response.delete_cookie(LOGIN_CSRF_COOKIE, path="/")
        return response

    return _complete_login(request, db, identifier)


def _two_factor_required() -> bool:
    """Whether the admin must supply a second factor to sign in."""
    if settings.disable_2fa:
        return False
    return totp.is_enrolled()


def _complete_login(request: Request, db: Session, identifier: str):
    """Issue the session cookie and record the sign-in."""
    token = create_session_token()
    response = RedirectResponse("/admin/dashboard", status_code=303)
    set_session_cookie(response, token)
    response.delete_cookie(LOGIN_CSRF_COOKIE, path="/")
    response.delete_cookie(PENDING_2FA_COOKIE, path="/")
    audit.record(
        db,
        "auth.login",
        ip_hash=audit.hash_ip(identifier),
        detail=f"signed in from {identifier}",
    )
    return response


@router.get("/admin/login/2fa", name="admin_login_2fa")
def admin_login_2fa(request: Request, db: Session = Depends(get_db)):
    """The second step of a two-factor sign-in."""
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=303)
    if not _has_valid_2fa_pending(request):
        return RedirectResponse("/admin", status_code=303)

    context = admin_context(
        request,
        db,
        login_error="",
        need_2fa=True,
        recovery_left=totp.remaining_recovery_codes(),
        login_csrf=_mint_login_csrf(),
    )
    response = render(request, "admin_login_2fa.html", context)
    _set_login_csrf_cookie(response, context["login_csrf"])
    return response


@router.post("/admin/login/2fa", name="admin_login_2fa_post")
def admin_login_2fa_post(
    request: Request,
    code: str = Form("", max_length=32),
    csrf: str = Form("", max_length=400),
    db: Session = Depends(get_db),
):
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=303)
    if not _has_valid_2fa_pending(request):
        return RedirectResponse("/admin", status_code=303)

    identifier = client_ip(request)

    def back(message: str, code_status: int = 401):
        fresh = _mint_login_csrf()
        response = render(
            request,
            "admin_login_2fa.html",
            admin_context(
                request,
                db,
                login_error=message,
                need_2fa=True,
                recovery_left=totp.remaining_recovery_codes(),
                login_csrf=fresh,
            ),
            status_code=code_status,
        )
        _set_login_csrf_cookie(response, fresh)
        return response

    # The pending cookie is only set after a correct password, but a bad code is
    # still a guess, so it is throttled on the same counter as the password.
    locked, retry_after = login_locked_out(identifier)
    if locked:
        return back(f"Too many attempts. Try again in {retry_after} seconds.", code_status=429)

    if not _login_csrf_valid(request, csrf):
        return back("Your form expired. Please try again.", code_status=400)

    secret = totp._load().get("secret", "")
    if not secret:
        return RedirectResponse("/admin", status_code=303)

    if totp.verify(secret, code):
        clear_login_failures(identifier)
        return _complete_login(request, db, identifier)

    if totp.consume_recovery_code(code):
        clear_login_failures(identifier)
        response = _complete_login(request, db, identifier)
        audit.record(
            db,
            "auth.2fa.recovery_used",
            ip_hash=audit.hash_ip(identifier),
            detail=f"recovery code used, {totp.remaining_recovery_codes()} left",
        )
        return response

    record_login_failure(identifier)
    audit.record(
        db,
        "auth.login_failed",
        ip_hash=audit.hash_ip(identifier),
        detail=f"second factor rejected for {identifier}",
    )
    return back("That code is not valid.", code_status=401)


@router.get("/admin/reissue-csrf", name="admin_reissue_csrf")
def admin_reissue_csrf(request: Request):
    """Hand out a fresh login CSRF token, for when a form sits open too long."""
    token = _mint_login_csrf()
    response = Response(status_code=204)
    _set_login_csrf_cookie(response, token)
    response.headers["X-CSRF-Token"] = token
    return response


# ------------------------------------------------------- dashboard analytics


def _daily_series(db: Session, days: int = 30) -> list[dict]:
    """Views and searches per day for the last N days, oldest first.

    One grouped query per series rather than one per day, and every day in the
    window is returned including the ones with no rows, so the chart has a
    continuous x-axis instead of gaps that look like missing data.

    ArticleView.view_date is stored as a YYYY-MM-DD string, which SQLite groups
    and sorts correctly as text. SearchQuery.created_at is a real timestamp and
    is grouped by date() in SQLite.
    """
    from datetime import timedelta

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days - 1)
    window = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]

    view_rows = dict(
        db.execute(
            select(ArticleView.view_date, func.sum(ArticleView.views))
            .where(ArticleView.view_date >= start.isoformat())
            .group_by(ArticleView.view_date)
        ).all()
    )

    search_rows = dict(
        db.execute(
            select(
                func.date(SearchQuery.created_at).label("day"),
                func.count(SearchQuery.id),
            )
            .where(SearchQuery.created_at >= start.isoformat())
            .group_by("day")
        ).all()
    )

    points = [
        {
            "day": day,
            "label": day[5:],
            "views": int(view_rows.get(day) or 0),
            "searches": int(search_rows.get(day) or 0),
        }
        for day in window
    ]

    # Totals travel with the series so the card can state a number next to the
    # shape. A window of all zeros would render a flat line that says nothing,
    # which is why the template checks these before drawing anything.
    return {
        "points": points,
        "total_views": sum(point["views"] for point in points),
        "total_searches": sum(point["searches"] for point in points),
        "days": days,
    }


# --------------------------------------------------------------- dashboard


@router.get("/admin/dashboard", name="admin_dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    stats = {
        "articles": db.query(Article).count(),
        "stop_codes": db.query(StopCode).count(),
        "feedback": feedback_summary(db),
        "dumps": db.query(DumpUpload).count(),
        "apps": db.query(AppDownload).count(),
        "users": db.query(User).count(),
        "comments_pending": db.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.status == Comment.STATUS_PENDING)
        )
        or 0,
        "questions_pending": db.scalar(
            select(func.count())
            .select_from(Question)
            .where(Question.status == Question.STATUS_NEW)
        )
        or 0,
        "questions_total": db.query(Question).count(),
    }

    series = _daily_series(db, days=30)

    articles = list(
        db.execute(select(Article).order_by(desc(Article.updated_at)).limit(10)).scalars()
    )
    codes = list(
        db.execute(select(StopCode).order_by(desc(StopCode.view_count)).limit(10)).scalars()
    )
    uploads = list(
        db.execute(
            select(DumpUpload).order_by(desc(DumpUpload.created_at)).limit(10)
        ).scalars()
    )
    # Unanswered questions first, so the dashboard can reply without a detour.
    open_questions = list(
        db.execute(
            select(Question)
            .where(Question.status == Question.STATUS_NEW)
            .order_by(desc(Question.created_at))
            .limit(5)
        ).scalars()
    )

    context = admin_context(
        request,
        db,
        stats=stats,
        series=series,
        articles=articles,
        stop_codes=codes,
        uploads=uploads,
        popular=popular_searches(db, 15),
        no_results=zero_result_searches(db, 10),
        feedback=recent_feedback(db, 15),
        open_questions=open_questions,
        # Only the pending count, so the moderation link can be badged.
        pending_comments=stats["comments_pending"],
        pending_questions=stats["questions_pending"],
    )
    return render(request, "admin_dashboard.html", context)


@router.post("/admin/logout", name="admin_logout")
def admin_logout(
    request: Request,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    # Every other mutating admin route checks the session first. Logging out
    # does not need it, since the CSRF token is derived from the very cookie
    # being cleared and an unauthenticated caller has none to present, but the
    # check is here so this route is not the one exception to the pattern.
    if not require_auth(request) or not guard_csrf(request, csrf):
        return RedirectResponse("/admin", status_code=303)
    audit.record(
        db,
        "auth.logout",
        ip_hash=audit.hash_ip(client_ip(request)),
        detail=f"signed out from {client_ip(request)}",
    )
    response = RedirectResponse("/admin", status_code=303)
    clear_session_cookie(response)
    return response


# ----------------------------------------------------------------- ads admin


def _ads_settings(db: Session):
    """The singleton ad settings row, creating it on first read."""
    from ..models import AdSettings

    row = db.query(AdSettings).first()
    if row is None:
        row = AdSettings()
        db.add(row)
        db.commit()
    return row


@router.get("/admin/ads", name="admin_ads")
def admin_ads(
    request: Request,
    edit: str = "",
    saved: str = "",
    unit_saved: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    from ..models import AdUnit
    from ..services.ads import DEVICES, FORMATS, PLACEMENTS, SHOW_ON

    settings_row = _ads_settings(db)
    editing = None
    if edit.isdigit():
        editing = db.get(AdUnit, int(edit))

    context = admin_context(
        request,
        db,
        ad_settings=settings_row,
        ad_units=list(db.query(AdUnit).order_by(AdUnit.created_at).all()),
        editing_unit=editing,
        formats=FORMATS,
        placements=PLACEMENTS,
        show_on_options=SHOW_ON,
        devices=DEVICES,
        saved=saved,
        unit_saved=unit_saved,
        error=error,
    )
    return render(request, "admin_ads.html", context)


@router.post("/admin/ads/settings", name="admin_ads_settings")
def admin_ads_settings(
    request: Request,
    enabled: str = Form(""),
    auto_ads: str = Form(""),
    publisher_id: str = Form("", max_length=200),
    ads_txt: str = Form("", max_length=4000),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..services.ads import validate_ad_settings

    row = _ads_settings(db)
    try:
        clean = validate_ad_settings(
            enabled=bool(enabled),
            publisher_id=publisher_id,
            auto_ads=bool(auto_ads),
            ads_txt=ads_txt,
        )
    except ValueError as exc:
        return RedirectResponse(f"/admin/ads?error={str(exc)}", status_code=303)

    audit.record(
        db,
        "ad.settings",
        detail=f"enabled={clean['enabled']}, publisher_id set={bool(clean['publisher_id'])}",
        commit=False,
    )
    row.enabled = clean["enabled"]
    row.publisher_id = clean["publisher_id"]
    row.auto_ads = clean["auto_ads"]
    row.ads_txt = clean["ads_txt"]
    db.commit()

    return RedirectResponse("/admin/ads?saved=1", status_code=303)


@router.post("/admin/ads/unit/save", name="admin_ads_unit_save")
def admin_ads_unit_save(
    request: Request,
    id: str = Form(""),
    label: str = Form("", max_length=120),
    slot_id: str = Form("", max_length=30),
    format: str = Form("auto", max_length=20),
    placement: str = Form("below-content", max_length=30),
    nth_paragraph: str = Form("2", max_length=10),
    layout_key: str = Form("", max_length=50),
    show_on: str = Form("all", max_length=20),
    selected_paths: str = Form("", max_length=500),
    device: str = Form("both", max_length=10),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..models import AdUnit
    from ..services.ads import validate_unit

    try:
        clean = validate_unit(
            label=label,
            slot_id=slot_id,
            format=format,
            placement=placement,
            nth_paragraph=nth_paragraph,
            layout_key=layout_key,
            show_on=show_on,
            selected_paths=selected_paths,
            device=device,
        )
    except ValueError as exc:
        return RedirectResponse(f"/admin/ads?error={str(exc)}", status_code=303)

    if id.isdigit():
        row = db.get(AdUnit, int(id))
        if row is None:
            return RedirectResponse("/admin/ads?error=Unit+not+found", status_code=303)
    else:
        row = AdUnit()
        # A freshly created unit should be live. The toggle from the list is the
        # way to disable it, not the save form.
        row.enabled = True
        db.add(row)

    for key, value in clean.items():
        setattr(row, key, value)
    audit.record(
        db,
        "ad.unit.save",
        target_type="adunit",
        target_id=row.id,
        detail=f"slot {clean['slot_id']}, placement {clean['placement']}, show_on {clean['show_on']}",
        ip_hash=audit.hash_ip(client_ip(request)),
        commit=False,
    )
    db.commit()

    return RedirectResponse("/admin/ads?unit_saved=1", status_code=303)


@router.post("/admin/ads/unit/{unit_id}/toggle", name="admin_ads_unit_toggle")
def admin_ads_unit_toggle(
    request: Request,
    unit_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..models import AdUnit

    row = db.get(AdUnit, unit_id)
    if row is not None:
        row.enabled = not row.enabled
        audit.record(
            db,
            "ad.unit.toggle",
            target_type="adunit",
            target_id=unit_id,
            detail=f"slot {row.slot_id} turned {'on' if row.enabled else 'off'}",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()
    return RedirectResponse("/admin/ads", status_code=303)


@router.post("/admin/ads/unit/{unit_id}/delete", name="admin_ads_unit_delete")
def admin_ads_unit_delete(
    request: Request,
    unit_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..models import AdUnit

    row = db.get(AdUnit, unit_id)
    if row is not None:
        slot = row.slot_id
        db.delete(row)
        audit.record(
            db,
            "ad.unit.delete",
            target_type="adunit",
            target_id=unit_id,
            detail=f"slot {slot} removed",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()
    return RedirectResponse("/admin/ads", status_code=303)


# --------------------------------------------------------- more admin tools


# Paths that are always present, used to offer a dropdown in the SEO override
# form without forcing the admin to type one by hand.
_PUBLIC_PATHS = [
    "/", "/articles", "/bsod", "/bsod/analyze", "/wizards", "/tools",
    "/tools/dns", "/tools/port", "/tools/status", "/tools/latency",
    "/tools/ip", "/drivers", "/hardware", "/scripts", "/apps",
    "/privacy", "/about",
]


@router.get("/admin/seo", name="admin_seo")
def admin_seo(
    request: Request,
    saved: str = "",
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    from ..models import SeoOverride, SiteSeoSettings

    overrides = db.query(SeoOverride).order_by(SeoOverride.path).all()
    settings_row = db.query(SiteSeoSettings).first()
    if settings_row is None:
        settings_row = SiteSeoSettings()
        db.add(settings_row)
        db.commit()

    context = admin_context(
        request,
        db,
        seo_overrides=overrides,
        seo_settings=settings_row,
        paths=_PUBLIC_PATHS,
        saved=saved,
    )
    return render(request, "admin_seo.html", context)


@router.post("/admin/seo", name="admin_seo_save")
def admin_seo_save(
    request: Request,
    path: str = Form("", max_length=400),
    title: str = Form("", max_length=250),
    description: str = Form("", max_length=600),
    og_image: str = Form("", max_length=600),
    sitemap_priority: str = Form("", max_length=10),
    sitemap_changefreq: str = Form("", max_length=20),
    default_changefreq: str = Form("monthly", max_length=20),
    default_priority: str = Form("0.5", max_length=10),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..models import SeoOverride, SiteSeoSettings

    path = path.strip()
    if not path.startswith("/") or " " in path or len(path) > 400:
        return _forbidden(request, db, "Enter a valid page path.")

    row = db.query(SeoOverride).filter(SeoOverride.path == path).first()
    if row is None:
        row = SeoOverride(path=path)
        db.add(row)

    row.title = title.strip()
    row.description = description.strip()
    row.og_image = og_image.strip()
    row.sitemap_priority = sitemap_priority.strip()
    row.sitemap_changefreq = sitemap_changefreq.strip()

    site_row = db.query(SiteSeoSettings).first()
    if site_row is None:
        site_row = SiteSeoSettings()
        db.add(site_row)
    site_row.default_changefreq = default_changefreq.strip() or "monthly"
    site_row.default_priority = default_priority.strip() or "0.5"

    audit.record(db, "seo.save", target_type="path", target_id=row.path, detail="override written", commit=False)
    db.commit()
    return RedirectResponse("/admin/seo?saved=1", status_code=303)


@router.post("/admin/seo/{override_id}/delete", name="admin_seo_delete")
def admin_seo_delete(
    request: Request,
    override_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..models import SeoOverride

    row = db.get(SeoOverride, override_id)
    if row is not None:
        path = row.path
        db.delete(row)
        audit.record(
            db,
            "seo.delete",
            target_type="path",
            target_id=path,
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()
    return RedirectResponse("/admin/seo", status_code=303)


@router.get("/admin/emails", name="admin_emails")
def admin_emails(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    from ..models import EmailLog

    rows = (
        db.query(EmailLog)
        .order_by(desc(EmailLog.created_at))
        .limit(100)
        .all()
    )
    context = admin_context(request, db, emails=rows)
    return render(request, "admin_emails.html", context)


@router.get("/admin/announcement", name="admin_announcement")
def admin_announcement(request: Request, saved: str = "", db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    from ..models import Announcement

    row = db.query(Announcement).order_by(desc(Announcement.id)).first()
    if row is None:
        row = Announcement()
        db.add(row)
        db.commit()

    context = admin_context(request, db, announcement=row, saved=saved)
    return render(request, "admin_announcement.html", context)


@router.post("/admin/announcement/save", name="admin_announcement_save")
def admin_announcement_save(
    request: Request,
    title: str = Form("", max_length=200),
    body: str = Form("", max_length=2000),
    link_url: str = Form("", max_length=600),
    enabled: str = Form(""),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    from ..models import Announcement

    row = db.query(Announcement).order_by(desc(Announcement.id)).first()
    if row is None:
        row = Announcement()
        db.add(row)

    # The link is rendered into an href on every public page, so a scheme
    # outside http/https/mailto is refused rather than stored. An empty
    # field is fine, meaning "no link".
    if link_url.strip() and not safe_link_url(link_url):
        return _forbidden(request, db, "The link must start with http://, https://, mailto: or /.")
    link_url = safe_link_url(link_url)

    row.title = title.strip()
    row.body = body.strip()
    row.link_url = link_url
    row.enabled = bool(enabled)
    audit.record(
        db,
        "announcement.save",
        target_type="banner",
        target_id=row.id,
        detail=f"enabled={bool(enabled)}",
        commit=False,
    )
    db.commit()
    return RedirectResponse("/admin/announcement?saved=1", status_code=303)


@router.get("/admin/backup", name="admin_backup")
def admin_backup(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    import io
    import zipfile

    db_path = _sqlite_db_path()
    if db_path is None:
        return _forbidden(request, db, "Backup needs a SQLite file. This deployment uses another database.")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # SQLite needs a backup copy rather than reading the live file.
        import sqlite3

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        try:
            # Connect URI form is required so SQLite can open the file in
            # backup mode rather than as a WAL follower.
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            dst = sqlite3.connect(tmp.name)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            with open(tmp.name, "rb") as f:
                zf.writestr("fixithub.db", f.read())
        finally:
            os.unlink(tmp.name)

        admin_json = ADMIN_HASH_FILE
        if admin_json.is_file():
            zf.writestr("admin.json", admin_json.read_bytes())

    buf.seek(0)
    # Recorded because a backup that leaves the machine is a copy of the admin
    # password hash and every reader address in one file.
    audit.record(
        db,
        "backup.created",
        detail="database and admin.json written to a zip",
        ip_hash=audit.hash_ip(client_ip(request)),
    )
    headers = {"Content-Disposition": f'attachment; filename="fixithub-backup-{datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")}.zip"'}
    return Response(buf.getvalue(), media_type="application/zip", headers=headers)


@router.get("/admin/restore", name="admin_restore_page")
def admin_restore_page(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    context = admin_context(request, db)
    return render(request, "admin_restore.html", context)


@router.post("/admin/restore", name="admin_restore")
def admin_restore(
    request: Request,
    file: UploadFile = File(...),
    confirm: str = Form("", max_length=50),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    if confirm.strip() != "RESTORE":
        return _forbidden(request, db, 'Type RESTORE to confirm replacing the database.')

    import io
    import zipfile

    # Read the archive incrementally under a cap. Reading it whole would let a
    # single request buffer as much memory as it liked.
    raw = _read_capped(file.file, MAX_RESTORE_BYTES)
    if raw is None:
        return _forbidden(
            request,
            db,
            f"That archive is larger than the {MAX_RESTORE_BYTES // 1024 // 1024} MB limit.",
        )
    if not raw:
        return _forbidden(request, db, "Upload a backup zip.")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return _forbidden(request, db, "That file is not a valid zip.")

    names = zf.namelist()
    if "fixithub.db" not in names:
        return _forbidden(request, db, "That zip does not contain a database.")

    live_db_path = _sqlite_db_path()
    if live_db_path is None:
        return _forbidden(request, db, "Restore needs a SQLite file. This deployment uses another database.")

    # Snapshot the live files first, into a directory the admin can download
    # them back from. The restore replaces the live database in place, so
    # without this the previous state is unrecoverable.
    snapshot_dir = Path(tempfile.mkdtemp(prefix="fixithub-restore-snapshot-"))
    snapshot = snapshot_dir / "backup-before-restore.zip"
    with zipfile.ZipFile(snapshot, "w") as out:
        import sqlite3

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        try:
            src = sqlite3.connect(f"file:{live_db_path}?mode=ro", uri=True)
            dst = sqlite3.connect(tmp.name)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            with open(tmp.name, "rb") as f:
                out.writestr("fixithub.db", f.read())
        finally:
            os.unlink(tmp.name)
        if ADMIN_HASH_FILE.is_file():
            out.writestr("admin.json", ADMIN_HASH_FILE.read_bytes())

    # Close the live database, swap the file, then let the engine reconnect.
    engine.dispose()
    tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp_db.close()
    tmp_path = Path(tmp_db.name)
    # The session is about to be invalidated: the restored database carries its
    # own password_changed_at history, so this connection's cookie may stop
    # verifying. Written with a short-lived separate session for that reason.
    try:
        with open(tmp_path, "wb") as out:
            out.write(zf.read("fixithub.db"))

        os.replace(tmp_path, Path(live_db_path))

        # admin.json is deliberately left alone. A backup taken before a
        # password change carries the old hash, and writing it back would both
        # roll the password back and invalidate every current session cookie -
        # locking the admin out of the panel they are standing in.

        # Re-open the engine on the new file so the next request works.
        create_all()
    except Exception as exc:  # noqa: BLE001
        log.exception("Restore failed")
        return _forbidden(request, db, f"Restore failed: {exc}")

    _record_after_restore(request, snapshot.name)

    return render(
        request,
        "admin_restore_done.html",
        admin_context(
            request,
            db,
            snapshot_filename=snapshot.name,
            snapshot_download=f"/admin/restore/snapshot/{snapshot_dir.name}",
        ),
    )


def _record_after_restore(request: Request, snapshot_name: str) -> None:
    """Write the audit row for a completed restore.

    On a fresh session rather than the request's: the restore has just replaced
    the database file, so the request's session and identity map may be stale,
    and the failure that would cause must not be able to lose the audit trail.
    """
    from ..db import SessionLocal

    try:
        with SessionLocal() as fresh:
            audit.record(
                fresh,
                "restore.performed",
                detail=f"database replaced; pre-restore snapshot {snapshot_name}",
                ip_hash=audit.hash_ip(client_ip(request)),
            )
    except Exception:  # noqa: BLE001 - never fail a restore over a log row
        log.exception("Could not write the restore audit row")


@router.get("/admin/restore/snapshot/{directory}", name="admin_restore_snapshot")
def admin_restore_snapshot(request: Request, directory: str, db: Session = Depends(get_db)):
    """Download the snapshot taken just before a restore.

    The snapshot lives in a temp directory the admin cannot otherwise reach, so
    without this route the safety net the handler takes is unreachable and the
    only copy of the pre-restore state is on a disk they do not control.
    """
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    # Both parts are matched against fixed patterns, so no separator, dot or
    # drive letter can appear and the resolved path stays inside the temp dir.
    if not re.fullmatch(r"fixithub-restore-snapshot-[a-zA-Z0-9_]+", directory or ""):
        return _forbidden(request, db, "That is not a restore snapshot.")

    path = Path(tempfile.gettempdir()) / directory / "backup-before-restore.zip"
    if not path.is_file():
        return _forbidden(request, db, "That snapshot is no longer available.")

    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"fixithub-before-restore-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.zip",
    )


@router.get("/admin/links", name="admin_links")
def admin_links(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    from ..services.content import load_all_articles

    rows = []
    try:
        import httpx

        seen: set[str] = set()
        for source in load_all_articles():
            for match in re.finditer(r'https?://[^\s)\]]+', source.body):
                url = match.group(0).rstrip(".,;")
                if url in seen:
                    continue
                seen.add(url)
                if len(seen) > 50:
                    break
                try:
                    with httpx.Client(timeout=5.0, follow_redirects=True) as client:
                        response = client.head(url)
                        # Some servers reject HEAD, so retry with GET.
                        if response.status_code in (403, 405):
                            response = client.get(url, headers={"Range": "bytes=0-0"})
                        status = response.status_code
                except Exception:
                    status = 0
                rows.append({"url": url, "status": status, "source": source.slug})
            if len(seen) > 50:
                break
    except ImportError:
        rows = []
    except Exception:
        rows = []

    context = admin_context(request, db, links=rows)
    return render(request, "admin_links.html", context)


@router.get("/admin/articles/{slug}/analytics", name="admin_article_analytics")
def admin_article_analytics(request: Request, slug: str, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    article = db.scalar(select(Article).where(Article.slug == slug))
    if article is None:
        return RedirectResponse("/admin/articles", status_code=303)

    views = (
        db.query(ArticleView)
        .filter(ArticleView.article_id == article.id)
        .order_by(ArticleView.view_date.desc())
        .limit(30)
        .all()
    )
    context = admin_context(request, db, article=article, views=views)
    return render(request, "admin_article_analytics.html", context)


# ---------------------------------------------------------- change password


# Matches the reader rule in services/accounts.py, not a stricter one. A password
# box that is easier to satisfy than the rest of the site's would be odd, and
# validate_password already documents why length is preferred over composition
# rules: "Password1!" is barely better than a dictionary word.
MIN_ADMIN_PASSWORD = 10

# bcrypt only reads the first 72 bytes of a password. A higher cap would
# advertise length the stored hash does not actually have.
MAX_ADMIN_PASSWORD_BYTES = 72

# The same refusals as validate_password, minus the email rule, which cannot
# apply to a single shared admin login.
EASY_PASSWORDS = {"password123", "1234567890", "qwertyuiop", "letmein1234", "administrator"}


def _check_new_password(password: str, confirm: str, stored_hash: str) -> str | None:
    """Return a refusal message, or None when the new password is acceptable."""
    if password != confirm:
        return "The new password and the confirmation do not match."

    length = len(password)
    if length < MIN_ADMIN_PASSWORD:
        return (
            f"Use at least {MIN_ADMIN_PASSWORD} characters. Longer is stronger and "
            "easier to remember than a short one full of symbols."
        )
    if len(password.encode("utf-8")) > MAX_ADMIN_PASSWORD_BYTES:
        return (
            f"Keep it under {MAX_ADMIN_PASSWORD_BYTES} bytes. Anything longer is "
            "truncated by bcrypt, so the extra characters add nothing."
        )
    if password.lower() in EASY_PASSWORDS:
        return "That password is too easy to guess. Try a phrase instead."

    # Asked "is this secretly the password I already have?". Checked against the
    # stored hash rather than by comparing the two strings, which also catches a
    # new password that differs only past byte 72.
    if verify_password(password, stored_hash):
        return "The new password is the same as the current one."

    return None


@router.get("/admin/change-password", name="admin_change_password")
def admin_change_password_form(
    request: Request,
    notice: str = "",
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    context = admin_context(
        request,
        db,
        notice=notice,
        error="",
        # Shown on the page so the admin is not left guessing why a change they
        # made from the web is being ignored.
        hash_pinned=bool(settings.admin_password_hash),
    )
    return render(request, "admin_change_password.html", context)


@router.post("/admin/change-password", name="admin_change_password_post")
def admin_change_password_post(
    request: Request,
    current_password: str = Form("", max_length=200),
    new_password: str = Form("", max_length=200),
    confirm_password: str = Form("", max_length=200),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    limited = enforce(
        request,
        password_limiter,
        prefix="change-password",
        message="Too many attempts. Wait a few minutes before trying again.",
    )
    if limited is not None:
        return limited

    def back(error: str, code: int = 200):
        """Re-render the form. Never echoes a submitted password back."""
        context = admin_context(
            request,
            db,
            notice="",
            error=error,
            hash_pinned=bool(settings.admin_password_hash),
        )
        return render(request, "admin_change_password.html", context, status_code=code)

    # load_admin_hash checks this env var before the saved file, so a hash
    # written here would never be used. Refusing beats reporting a success that
    # silently does not take effect.
    if settings.admin_password_hash:
        return back(
            "This deployment sets FIXITHUB_ADMIN_PASSWORD_HASH, which takes "
            "priority over the saved file. Change it in the environment instead.",
            code=400,
        )

    stored_hash = load_admin_hash()
    if not stored_hash:
        return back(
            "No admin password is configured. Run: python seed.py --set-admin-password",
            code=400,
        )

    if not verify_password(current_password or "", stored_hash):
        return back("Your current password is not correct.", code=400)

    refusal = _check_new_password(
        new_password or "", confirm_password or "", stored_hash
    )
    if refusal is not None:
        return back(refusal, code=400)

    changed_at = datetime.now(timezone.utc).timestamp()
    try:
        save_admin_hash(hash_password(new_password), password_changed_at=changed_at)
    except OSError:
        # A read-only or full volume. Saying it worked would be a lie, and the
        # admin would keep using a password they believed they had changed.
        log.exception("Could not write the admin password hash")
        return back(
            "The new password could not be saved. Check that the data directory "
            "is writable, then try again.",
            code=500,
        )

    # The old cookies are now invalid. Issue a fresh one so the admin who made
    # the change stays signed in and everyone else is signed out.
    audit.record(
        db,
        "password.changed",
        detail=f"password rotated at {int(changed_at)}; other sessions invalidated",
        ip_hash=audit.hash_ip(client_ip(request)),
        commit=False,
    )
    db.commit()
    response = RedirectResponse("/admin/change-password?notice=changed", status_code=303)
    set_session_cookie(response, create_session_token())
    return response


# ---------------------------------------------------------------- articles


@router.get("/admin/articles", name="admin_articles")
def admin_articles(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    rows = list(
        db.execute(select(Article).order_by(Article.category, func.lower(Article.title))).scalars()
    )
    context = admin_context(request, db, articles=rows)
    return render(request, "admin_articles.html", context)


def _article_path(slug: str) -> str | None:
    """Resolve a slug to a file inside /content, refusing anything else."""
    if not slug or len(slug) > 180:
        return None
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        return None
    matches = list(CONTENT_DIR.rglob(f"{slug}.md"))
    if not matches:
        return None
    resolved = matches[0].resolve()
    try:
        resolved.relative_to(CONTENT_DIR.resolve())
    except ValueError:
        return None
    return str(resolved)


@router.get("/admin/articles/new", name="admin_article_new")
def admin_article_new(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    return render(
        request,
        "admin_article_form.html",
        admin_context(
            request,
            db,
            article=None,
            rendered=None,
            mode="new",
            default_category="windows",
        ),
    )


@router.get("/admin/articles/{slug}/edit", name="admin_article_edit")
def admin_article_edit(request: Request, slug: str, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    article = db.scalar(select(Article).where(Article.slug == slug))
    if article is None:
        return render(
            request,
            "404.html",
            admin_context(
                request,
                db,
                robots="noindex, nofollow",
                status_code=404,
                error_title="Article not found",
                error_message=f"No article exists with the slug '{slug}'.",
            ),
            status_code=404,
        )

    return render(
        request,
        "admin_article_form.html",
        admin_context(
            request,
            db,
            article=article,
            rendered=None,
            mode="edit",
            default_category=article.category,
        ),
    )


def _index_after_write(db: Session) -> None:
    """Rebuild the search index so a new or edited article is findable."""
    search.rebuild()
    db.commit()


@router.post("/admin/articles/save", name="admin_article_save")
def admin_article_save(
    request: Request,
    slug: str = Form("", max_length=200),
    title: str = Form("", max_length=250),
    category: str = Form("windows", max_length=50),
    tags: str = Form("", max_length=500),
    difficulty: str = Form("easy", max_length=20),
    os_version: str = Form("Windows 10/11", max_length=60),
    summary: str = Form("", max_length=600),
    featured: str = Form("", max_length=4),
    body: str = Form("", max_length=MAX_BODY),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired. Please sign in again.")

    clean_slug = slug.strip().lower()
    clean_title = title.strip()
    clean_category = category.strip().lower()
    clean_difficulty = difficulty.strip().lower()

    errors: list[str] = []
    if not clean_title:
        errors.append("A title is required.")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", clean_slug):
        errors.append("Slug must be lowercase letters, numbers and hyphens only.")
    if clean_category not in CATEGORIES:
        errors.append("Choose a valid category.")
    if clean_difficulty not in DIFFICULTY_LABELS:
        errors.append("Choose a valid difficulty.")
    if len(body.strip()) < 50:
        errors.append("The article body needs at least 50 characters.")

    existing = db.scalar(select(Article).where(Article.slug == clean_slug))
    original_path = _article_path(clean_slug) if existing else None

    if errors:
        return render(
            request,
            "admin_article_form.html",
            admin_context(
                request,
                db,
                article={
                    "slug": clean_slug,
                    "title": clean_title,
                    "category": clean_category,
                    "tags": [t.strip() for t in tags.split(",") if t.strip()],
                    "difficulty": clean_difficulty,
                    "os_version": os_version,
                    "summary": summary,
                    "is_featured": featured == "on",
                    "body": body,
                    "id": existing.id if existing else None,
                },
                rendered=None,
                mode="edit" if existing else "new",
                default_category=clean_category,
                form_errors=errors,
            ),
            status_code=400,
        )

    tag_list = [t.strip() for t in re.split(r"[,;]", tags) if t.strip()][:25]
    rendered = render_markdown(body)

    # The markdown files in /content stay the source of truth.
    frontmatter = {
        "title": clean_title,
        "category": clean_category,
        "tags": tag_list,
        "difficulty": clean_difficulty,
        "os_version": os_version.strip() or "Windows 10/11",
        "featured": featured == "on",
    }
    frontmatter_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    markdown_text = f"---\n{frontmatter_text}---\n\n{body.strip()}\n"

    if original_path:
        path = original_path
    else:
        path = str(CONTENT_DIR / f"{clean_slug}.md")

    # Back up the existing file before overwriting it.
    if original_path:
        shutil.copy2(original_path, original_path + ".bak")

    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown_text)

    # Reload from disk so the stored values match the file exactly.
    reloaded = load_article_file(Path(path))
    if reloaded is None:
        return _forbidden(request, db, "The article could not be written. Check the folder permissions.")

    if existing is None:
        existing = Article(slug=clean_slug)
        db.add(existing)
    existing.title = reloaded.title
    existing.category = reloaded.category
    existing.tags = reloaded.tags
    existing.difficulty = reloaded.difficulty
    existing.os_version = reloaded.os_version
    existing.is_featured = reloaded.featured
    existing.summary = summary.strip() or rendered.summary
    existing.body = reloaded.body
    existing.reading_time = rendered.reading_time
    existing.source_path = reloaded.source_path
    existing.status = "draft" if reloaded.draft else "published"
    audit.record(
        db,
        "article.save",
        target_type="article",
        target_id=clean_slug,
        detail=f"title: {reloaded.title}",
        ip_hash=audit.hash_ip(client_ip(request)),
        commit=False,
    )
    db.commit()

    _index_after_write(db)
    return RedirectResponse(f"/admin/articles?saved={clean_slug}", status_code=303)


@router.post("/admin/articles/{slug}/delete", name="admin_article_delete")
def admin_article_delete(
    request: Request,
    slug: str,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    article = db.scalar(select(Article).where(Article.slug == slug))
    if article is not None:
        title = article.title
        # Per-day view rows reference the article, so clear them first.
        db.execute(delete(ArticleView).where(ArticleView.article_id == article.id))
        db.delete(article)
        audit.record(
            db,
            "article.delete",
            target_type="article",
            target_id=slug,
            detail=f"removed '{title}' and its markdown file",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    path = _article_path(slug)
    if path:
        import os

        os.remove(path)
        backup = path + ".bak"
        if os.path.exists(backup):
            os.remove(backup)

    _index_after_write(db)
    return RedirectResponse("/admin/articles?deleted=1", status_code=303)


@router.post("/admin/articles/preview", name="admin_article_preview")
def admin_article_preview(
    request: Request,
    body: str = Form("", max_length=MAX_BODY),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    rendered = render_markdown(body)
    return render(
        request,
        "admin_preview.html",
        admin_context(request, db, rendered=rendered, toc=rendered.toc),
    )


# -------------------------------------------------------------- stop codes


@router.get("/admin/stop-codes", name="admin_stop_codes")
def admin_stop_codes(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    rows = list(db.execute(select(StopCode).order_by(StopCode.code_uint)).scalars())
    context = admin_context(request, db, stop_codes=rows)
    return render(request, "admin_stop_codes.html", context)


@router.get("/admin/stop-codes/new", name="admin_stop_code_new")
def admin_stop_code_new(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    return render(
        request,
        "admin_stop_code_form.html",
        admin_context(request, db, code=None, mode="new", default_difficulty="moderate"),
    )


@router.get("/admin/stop-codes/{name}/edit", name="admin_stop_code_edit")
def admin_stop_code_edit(request: Request, name: str, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    from ..services.stopcodes import normalise_query

    code = db.scalar(select(StopCode).where(func.upper(StopCode.name) == normalise_query(name)))
    if code is None:
        return render(
            request,
            "404.html",
            admin_context(
                request,
                db,
                robots="noindex, nofollow",
                status_code=404,
                error_title="Stop code not found",
                error_message=f"No stop code named '{name}' exists.",
            ),
            status_code=404,
        )

    return render(
        request,
        "admin_stop_code_form.html",
        admin_context(request, db, code=code, mode="edit", default_difficulty=code.difficulty),
    )


def _lines(raw: str) -> list[str]:
    """Split a textarea into a clean list, one item per non-empty line."""
    items: list[str] = []
    for line in re.split(r"[\r\n]+", raw or ""):
        cleaned = line.strip().lstrip("-* ").strip()
        if cleaned:
            items.append(cleaned[:600])
    return items[:30]


@router.post("/admin/stop-codes/save", name="admin_stop_code_save")
def admin_stop_code_save(
    request: Request,
    code_hex: str = Form("", max_length=20),
    name: str = Form("", max_length=120),
    meaning: str = Form("", max_length=4000),
    causes: str = Form("", max_length=MAX_BODY),
    fix_steps: str = Form("", max_length=MAX_BODY),
    difficulty: str = Form("moderate", max_length=20),
    when_to_call_pro: str = Form("", max_length=4000),
    related_slugs: str = Form("", max_length=1000),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    errors: list[str] = []
    clean_name = name.strip().upper().replace(" ", "_").replace("-", "_")
    if not re.fullmatch(r"[A-Z0-9_]{3,120}", clean_name):
        errors.append("Name must be uppercase letters, numbers and underscores.")

    try:
        value = parse_code_hex(code_hex)
    except ValueError as exc:
        value = None
        errors.append(str(exc))

    if difficulty not in DIFFICULTY_LABELS:
        errors.append("Choose a valid difficulty.")

    cause_list = _lines(causes)
    step_list = _lines(fix_steps)
    if not cause_list:
        errors.append("Add at least one likely cause.")
    if len(step_list) < 2:
        errors.append("Add at least two ordered fix steps.")

    if value is not None:
        clash = db.scalar(select(StopCode).where(StopCode.code_uint == value))
        if clash is not None and (clean_name != clash.name or name.strip().upper() != clash.name):
            errors.append(f"Stop code 0x{value:08X} already exists as {clash.name}.")
        same_name = db.scalar(select(StopCode).where(func.upper(StopCode.name) == clean_name))
        if same_name is not None and value is not None and same_name.code_uint != value:
            errors.append(f"The name {clean_name} is already used by another code.")

    if errors:
        return render(
            request,
            "admin_stop_code_form.html",
            admin_context(
                request,
                db,
                code={
                    "code_hex": code_hex,
                    "name": clean_name,
                    "meaning": meaning,
                    "causes": cause_list,
                    "fix_steps": step_list,
                    "difficulty": difficulty,
                    "when_to_call_pro": when_to_call_pro,
                    "related_slugs": related_slugs,
                    "id": None,
                },
                mode="new",
                default_difficulty=difficulty,
                form_errors=errors,
            ),
            status_code=400,
        )

    record = db.scalar(select(StopCode).where(StopCode.code_uint == value))
    if record is None:
        record = StopCode(code_uint=value)
        db.add(record)

    record.code_hex = f"0x{value:08X}"
    record.name = clean_name
    record.meaning = meaning.strip()
    record.causes = cause_list
    record.fix_steps = step_list
    record.difficulty = difficulty
    record.when_to_call_pro = when_to_call_pro.strip()
    record.related_slugs = [
        s.strip() for s in re.split(r"[,;\s]+", related_slugs or "") if s.strip()
    ][:10]
    audit.record(
        db,
        "stopcode.save",
        target_type="stopcode",
        target_id=clean_name,
        detail=f"hex {record.code_hex}, {record.difficulty}",
        ip_hash=audit.hash_ip(client_ip(request)),
        commit=False,
    )
    db.commit()

    return RedirectResponse(f"/admin/stop-codes?saved={clean_name}", status_code=303)


@router.post("/admin/stop-codes/{name}/delete", name="admin_stop_code_delete")
def admin_stop_code_delete(
    request: Request,
    name: str,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    from ..services.stopcodes import normalise_query

    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    code = db.scalar(select(StopCode).where(func.upper(StopCode.name) == normalise_query(name)))
    if code is not None:
        label = code.name
        db.delete(code)
        audit.record(
            db,
            "stopcode.delete",
            target_type="stopcode",
            target_id=label,
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/stop-codes?deleted=1", status_code=303)


# ------------------------------------------------------------ two-factor

# The secret under enrolment is held in a signed cookie rather than on disk, so
# an abandoned setup leaves nothing behind and a half-finished enrolment cannot
# lock the admin out.
PENDING_SECRET_COOKIE = "fixithub_2fa_secret"
PENDING_SECRET_MAX_AGE = 900  # 15 minutes to scan and type a code


def _mint_pending_secret(secret: str) -> str:
    from ..security import _serialiser

    return _serialiser.dumps({"secret": secret}, salt="fixithub-2fa-secret")


def _read_pending_secret(request: Request) -> str:
    from ..security import _serialiser

    cookie = request.cookies.get(PENDING_SECRET_COOKIE)
    if not cookie:
        return ""
    try:
        data = _serialiser.loads(
            cookie, salt="fixithub-2fa-secret", max_age=PENDING_SECRET_MAX_AGE
        )
    except Exception:  # noqa: BLE001 - expired or forged
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("secret") or "")


@router.get("/admin/two-factor", name="admin_two_factor")
def admin_two_factor(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    pending = _read_pending_secret(request)
    enrolled_at = ""
    if totp.is_enrolled():
        enrolled_at = datetime.fromtimestamp(
            totp._load().get("enabled_at") or 0, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")

    return render(
        request,
        "admin_two_factor.html",
        admin_context(
            request,
            db,
            enrolled=totp.is_enrolled(),
            enrolled_at=enrolled_at,
            recovery_left=totp.remaining_recovery_codes(),
            pending_secret=pending,
            pending_uri=totp.provisioning_uri(pending) if pending else "",
            disabled_by_env=settings.disable_2fa,
            new_codes=request.query_params.get("codes", "").split(",") if request.query_params.get("codes") else [],
        ),
    )


@router.post("/admin/two-factor/start", name="admin_two_factor_start")
def admin_two_factor_start(request: Request, csrf: str = Form("", max_length=200), db: Session = Depends(get_db)):
    """Mint a secret and show it. Nothing is stored until it is confirmed."""
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    secret = totp.generate_secret()
    audit.record(db, "auth.2fa.enrol", detail="enrolment started")
    response = RedirectResponse("/admin/two-factor", status_code=303)
    response.set_cookie(
        PENDING_SECRET_COOKIE,
        _mint_pending_secret(secret),
        max_age=PENDING_SECRET_MAX_AGE,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/admin/two-factor/confirm", name="admin_two_factor_confirm")
def admin_two_factor_confirm(
    request: Request,
    secret: str = Form("", max_length=64),
    code: str = Form("", max_length=6),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    # The posted secret is ignored in favour of the signed cookie, so a
    # tampered form field cannot enrol a secret of the attacker's choosing.
    pending = _read_pending_secret(request)
    if not pending:
        return _forbidden(request, db, "That setup link expired. Start again.")

    if not totp.verify(pending, code):
        return _forbidden(request, db, "That code did not match. Check your app and try again.")

    codes = totp.generate_recovery_codes()
    totp.save(pending, codes)
    audit.record(db, "auth.2fa.enabled", detail=f"{len(codes)} recovery codes issued")

    response = RedirectResponse(
        f"/admin/two-factor?codes={','.join(codes)}",
        status_code=303,
    )
    response.delete_cookie(PENDING_SECRET_COOKIE, path="/")
    return response


@router.post("/admin/two-factor/discard", name="admin_two_factor_discard")
def admin_two_factor_discard(request: Request, csrf: str = Form("", max_length=200), db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    response = RedirectResponse("/admin/two-factor", status_code=303)
    response.delete_cookie(PENDING_SECRET_COOKIE, path="/")
    return response


@router.post("/admin/two-factor/disable", name="admin_two_factor_disable")
def admin_two_factor_disable(
    request: Request,
    password: str = Form("", max_length=200),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    """Turn the second factor off. Requires the password again.

    An authenticated session alone is not enough: this is the one control that
    weakens authentication, so a stolen session cookie should not be able to
    use it without also knowing the password.
    """
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    stored = load_admin_hash()
    if not verify_password(password, stored):
        limited = enforce(request, password_limiter, prefix="disable-2fa")
        if limited is not None:
            return limited
        return _forbidden(request, db, "That password is not correct.")

    totp.clear()
    audit.record(db, "auth.2fa.disabled", detail="two-factor turned off by the admin")
    response = RedirectResponse("/admin/two-factor", status_code=303)
    response.delete_cookie(PENDING_SECRET_COOKIE, path="/")
    return response


@router.post("/admin/two-factor/recovery-codes", name="admin_two_factor_recovery_codes")
def admin_two_factor_recovery_codes(
    request: Request, csrf: str = Form("", max_length=200), db: Session = Depends(get_db)
):
    """Replace the recovery codes. The secret is unchanged."""
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    secret = totp._load().get("secret", "")
    if not secret:
        return _forbidden(request, db, "Two-factor is not set up.")

    codes = totp.generate_recovery_codes()
    totp.save(secret, codes)
    audit.record(db, "auth.2fa.enrol", detail=f"{len(codes)} replacement recovery codes issued")
    return RedirectResponse(f"/admin/two-factor?codes={','.join(codes)}", status_code=303)


# ---------------------------------------------------------------- audit log


@router.get("/admin/audit", name="admin_audit")
def admin_audit(request: Request, action: str = "", db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    wanted = action if action in audit.ACTIONS else ""
    context = admin_context(
        request,
        db,
        entries=audit.recent(db, limit=200, action=wanted),
        action_counts=audit.counts_by_action(db),
        active_action=wanted,
        action_labels=audit.ACTIONS,
    )
    return render(request, "admin_audit.html", context)


# --------------------------------------------------------- uploaded apps


def _app_form_context(
    request: Request,
    db: Session,
    *,
    app,
    mode: str,
    form_errors: list[str] | None = None,
    notice: str = "",
):
    return admin_context(
        request,
        db,
        app=app,
        mode=mode,
        form_errors=form_errors or [],
        notice=notice,
        app_categories=APP_CATEGORIES,
        max_app_mb=MAX_APP_BYTES // 1024 // 1024,
        allowed_suffixes=", ".join(ALLOWED_SUFFIXES),
        max_image_mb=MAX_IMAGE_BYTES // 1024 // 1024,
        allowed_image_suffixes=", ".join(ALLOWED_IMAGE_SUFFIXES),
    )


@router.get("/admin/apps", name="admin_apps")
def admin_apps(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    rows = list(db.execute(select(AppDownload).order_by(AppDownload.updated_at.desc())).scalars())

    # The checksum check reads and SHA-256s a whole file per row, up to 50 MB
    # each. Doing that inside the template meant every page view hashed every
    # uploaded binary, so it is computed here once per app and cached on the
    # request-scoped row copy rather than recomputed per column.
    listings = []
    for row in rows:
        item = _AppListing(row)
        item.integrity = row.integrity_ok()
        listings.append(item)

    context = admin_context(
        request,
        db,
        apps=listings,
        app_categories=APP_CATEGORIES,
        max_app_mb=MAX_APP_BYTES // 1024 // 1024,
        allowed_suffixes=", ".join(ALLOWED_SUFFIXES),
    )
    return render(request, "admin_apps.html", context)


class _AppListing:
    """A view row that carries the integrity result alongside the columns.

    Jinja resolves an attribute before an item of the same name, so
    ``row.integrity`` finds this attribute and never reaches the property. The
    template is what used to call integrity_ok() itself, once per row, on every
    render.
    """

    __slots__ = ("_row", "integrity")

    def __init__(self, row):
        self._row = row
        self.integrity = None

    def __getattr__(self, name):
        return getattr(self._row, name)


@router.get("/admin/apps/new", name="admin_app_new")
def admin_app_new(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    blank = {
        "slug": "",
        "title": "",
        "summary": "",
        "version": "",
        "vendor": "",
        "vendor_url": "",
        "purpose": "",
        "category": "hardware",
        "warnings_text": "",
        "is_published": False,
        "filename": "",
        "size_display": "",
        "sha256": "",
        "id": None,
    }
    return render(
        request,
        "admin_app_form.html",
        _app_form_context(request, db, app=blank, mode="new"),
    )


@router.get("/admin/apps/{slug}/edit", name="admin_app_edit")
def admin_app_edit(request: Request, slug: str, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    record = db.scalar(select(AppDownload).where(AppDownload.slug == slug.lower()))
    if record is None:
        return render(
            request,
            "404.html",
            admin_context(
                request,
                db,
                robots="noindex, nofollow",
                status_code=404,
                error_title="Upload not found",
                error_message=f"No upload named '{slug}' exists.",
            ),
            status_code=404,
        )

    app = dict(record.to_dict())
    app["warnings_text"] = "\n".join(record.warnings or [])
    app["is_published"] = record.is_published
    app["size_display"] = record.size_display
    app["download_count"] = record.download_count

    return render(
        request,
        "admin_app_form.html",
        _app_form_context(request, db, app=app, mode="edit"),
    )


@router.post("/admin/apps/save", name="admin_app_save")
async def admin_app_save(
    request: Request,
    slug: str = Form("", max_length=80),
    title: str = Form("", max_length=160),
    summary: str = Form("", max_length=2000),
    purpose: str = Form("", max_length=MAX_BODY),
    version: str = Form("", max_length=40),
    vendor: str = Form("", max_length=120),
    vendor_url: str = Form("", max_length=400),
    category: str = Form("hardware", max_length=50),
    warnings_text: str = Form("", max_length=MAX_BODY),
    is_published: str = Form(""),
    csrf: str = Form("", max_length=200),
    binary: UploadFile | None = File(None),
    screenshot: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    errors: list[str] = []

    try:
        clean_slug = apps.clean_slug(slug)
    except AppUploadError as exc:
        clean_slug = (slug or "").strip().lower()
        errors.append(str(exc))

    if not title.strip():
        errors.append("A title is required.")
    if not summary.strip():
        errors.append("A short summary is required, so visitors know what this is.")
    if category not in APP_CATEGORIES:
        errors.append("Choose a valid category.")

    existing = db.scalar(select(AppDownload).where(AppDownload.slug == clean_slug))

    # An existing record may be edited without re-uploading. The metadata is
    # still validated, but the file is untouched unless a new one arrives.
    upload: apps.ValidatedUpload | None = None
    if binary is not None and (binary.filename or "").strip():
        client_name = binary.filename or ""
        chunks: list[bytes] = []
        total = 0
        try:
            while True:
                block = await binary.read(256 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_APP_BYTES:
                    errors.append(
                        f"That file is larger than the "
                        f"{MAX_APP_BYTES // 1024 // 1024} MB limit."
                    )
                    break
                chunks.append(block)
        finally:
            await binary.close()

        if not errors:
            try:
                upload = apps.store_upload(clean_slug, client_name, chunks)
            except AppUploadError as exc:
                errors.append(str(exc))
        elif chunks:
            # Over the cap while streaming, so nothing was written. Drop what
            # was buffered rather than holding it any longer.
            chunks.clear()

    # The screenshot is optional and handled separately from the binary, so a
    # missing one is never an error. A present but invalid one is, because
    # silently ignoring it would leave the admin thinking it saved.
    image_upload: apps.ValidatedUpload | None = None
    if screenshot is not None and (screenshot.filename or "").strip():
        image_chunks: list[bytes] = []
        image_total = 0
        try:
            while True:
                block = await screenshot.read(256 * 1024)
                if not block:
                    break
                image_total += len(block)
                if image_total > MAX_IMAGE_BYTES:
                    errors.append(
                        f"That screenshot is larger than the "
                        f"{MAX_IMAGE_BYTES // 1024 // 1024} MB limit."
                    )
                    break
                image_chunks.append(block)
        finally:
            await screenshot.close()

        if not errors:
            try:
                image_upload = apps.store_image(
                    clean_slug, screenshot.filename or "", image_chunks
                )
            except AppUploadError as exc:
                errors.append(str(exc))
        elif image_chunks:
            image_chunks.clear()

    if errors:
        app = {
            "slug": slug,
            "title": title,
            "summary": summary,
            "purpose": purpose,
            "version": version,
            "vendor": vendor,
            "vendor_url": vendor_url,
            "category": category,
            "warnings_text": warnings_text,
            "is_published": bool(is_published),
            "filename": existing.filename if existing else "",
            "size_display": existing.size_display if existing else "",
            "sha256": existing.sha256 if existing else "",
            "id": existing.id if existing else None,
        }
        return render(
            request,
            "admin_app_form.html",
            _app_form_context(request, db, app=app, mode="edit" if existing else "new", form_errors=errors),
            status_code=400,
        )

    # A new record with no file would be a dead download, so require one.
    if existing is None and upload is None:
        message = "Choose a file to upload."
        app = {
            "slug": slug,
            "title": title,
            "summary": summary,
            "purpose": purpose,
            "version": version,
            "vendor": vendor,
            "vendor_url": vendor_url,
            "category": category,
            "warnings_text": warnings_text,
            "is_published": bool(is_published),
            "filename": "",
            "size_display": "",
            "sha256": "",
            "id": None,
        }
        return render(
            request,
            "admin_app_form.html",
            _app_form_context(request, db, app=app, mode="new", form_errors=[message]),
            status_code=400,
        )

    if upload is not None and existing is not None and existing.filename != upload.filename:
        # Replacing a file of a different type leaves the old one orphaned.
        apps.remove_stored(existing.filename)

    record = existing or AppDownload(slug=clean_slug, filename=upload.filename if upload else "")
    if upload is not None:
        record.filename = upload.filename
        record.size_bytes = upload.size
        record.sha256 = upload.sha256

    # Swap in the new screenshot only once it validated, so a failed image
    # leaves the previously working one in place rather than clearing it.
    if image_upload is not None:
        previous = (existing.screenshot_filename if existing else "") or ""
        if previous and previous != image_upload.filename:
            apps.remove_stored_image(previous)
        record.screenshot_filename = image_upload.filename

    record.title = title.strip()
    record.summary = summary.strip()
    record.purpose = purpose.strip()
    record.version = version.strip()
    record.vendor = vendor.strip()
    record.vendor_url = vendor_url.strip()
    record.category = category
    record.warnings = _lines(warnings_text)
    record.is_published = bool(is_published)

    if record.id is None:
        db.add(record)
    audit.record(
        db,
        "app.save",
        target_type="app",
        target_id=clean_slug,
        detail=(
            f"'{title.strip()}' v{record.version or '-'}, "
            f"published={bool(is_published)}, file={'replaced' if upload else 'unchanged'}"
        ),
        ip_hash=audit.hash_ip(client_ip(request)),
        commit=False,
    )
    db.commit()

    _index_after_write(db)
    return RedirectResponse(f"/admin/apps?saved={clean_slug}", status_code=303)


# ------------------------------------------------------------- moderation


@router.get("/admin/comments", name="admin_comments")
def admin_comments(request: Request, status_filter: str = "", db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    wanted = status_filter if status_filter in Comment.STATUSES else ""

    # joinedload on Comment.user: the template prints the author's address on
    # every row, and a lazy relationship there is one SELECT per comment, so
    # the 200-row page issued 200 extra queries.
    query = select(Comment).options(joinedload(Comment.user)).order_by(desc(Comment.created_at)).limit(200)
    if wanted:
        query = query.where(Comment.status == wanted)

    rows = list(db.execute(query).scalars())

    counts = {
        state: db.scalar(
            select(func.count()).select_from(Comment).where(Comment.status == state)
        )
        or 0
        for state in Comment.STATUSES
    }

    context = admin_context(
        request,
        db,
        comments=rows,
        comment_counts=counts,
        active_status=wanted,
        total_users=db.query(User).count(),
        unverified_users=db.scalar(
            select(func.count()).select_from(User).where(User.is_verified.is_(False))
        )
        or 0,
    )
    return render(request, "admin_comments.html", context)


@router.post("/admin/comments/{comment_id}/moderate", name="admin_comment_moderate")
def admin_comment_moderate(
    request: Request,
    comment_id: int,
    action: str = Form("", max_length=20),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    mapping = {
        "approve": Comment.STATUS_APPROVED,
        "reject": Comment.STATUS_REJECTED,
        "pending": Comment.STATUS_PENDING,
    }
    new_status = mapping.get(action)
    if new_status is None:
        return _forbidden(request, db, "Unknown moderation action.")

    comment = db.get(Comment, comment_id)
    if comment is not None:
        comment.status = new_status
        comment.moderated_at = datetime.now(timezone.utc)
        comment.moderated_by = session_id(request)
        audit.record(
            db,
            {"approve": "comment.approve", "reject": "comment.reject"}.get(action, "comment.approve"),
            target_type="comment",
            target_id=comment.id,
            detail=f"status set to {new_status}",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/comments", status_code=303)


@router.post("/admin/comments/{comment_id}/delete", name="admin_comment_delete")
def admin_comment_delete(
    request: Request,
    comment_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    comment = db.get(Comment, comment_id)
    if comment is not None:
        author = comment.user.email if comment.user else "deleted user"
        db.delete(comment)
        audit.record(
            db,
            "comment.delete",
            target_type="comment",
            target_id=comment_id,
            detail=f"comment by {author} removed",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/comments", status_code=303)


# ----------------------------------------------------------------- questions


@router.get("/admin/questions", name="admin_questions")
def admin_questions(request: Request, status_filter: str = "", db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    wanted = status_filter if status_filter in Question.STATUSES else ""

    query = select(Question).order_by(desc(Question.created_at)).limit(200)
    if wanted:
        query = query.where(Question.status == wanted)

    rows = list(db.execute(query).scalars())

    counts = {
        state: db.scalar(
            select(func.count()).select_from(Question).where(Question.status == state)
        )
        or 0
        for state in Question.STATUSES
    }

    context = admin_context(
        request,
        db,
        questions=rows,
        question_counts=counts,
        active_status=wanted,
    )
    return render(request, "admin_questions.html", context)


@router.post("/admin/questions/{question_id}/reply", name="admin_question_reply")
def admin_question_reply(
    request: Request,
    question_id: int,
    reply: str = Form("", max_length=MAX_REPLY),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    """Answer a question. Plain text, so it can never carry markup."""
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    clean = (reply or "").strip()
    if not clean:
        return _forbidden(request, db, "Write a reply before saving.")

    question = db.get(Question, question_id)
    if question is not None:
        question.reply = clean
        question.status = Question.STATUS_ANSWERED
        question.replied_at = datetime.now(timezone.utc)
        question.replied_by = session_id(request)
        # The prompt is recorded, not the reply: an audit log is not the place
        # to keep a second copy of what was said to a visitor.
        audit.record(
            db,
            "question.reply",
            target_type="question",
            target_id=question_id,
            detail=f"answered: {question.prompt[:120]}",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/questions", status_code=303)


@router.post("/admin/questions/{question_id}/reopen", name="admin_question_reopen")
def admin_question_reopen(
    request: Request,
    question_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    """Put an answered question back in the queue, for a reply that missed."""
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    question = db.get(Question, question_id)
    if question is not None:
        question.status = Question.STATUS_NEW
        audit.record(
            db,
            "question.reopen",
            target_type="question",
            target_id=question_id,
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/questions", status_code=303)


@router.post("/admin/questions/{question_id}/delete", name="admin_question_delete")
def admin_question_delete(
    request: Request,
    question_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    question = db.get(Question, question_id)
    if question is not None:
        db.delete(question)
        audit.record(
            db,
            "question.delete",
            target_type="question",
            target_id=question_id,
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/questions", status_code=303)


@router.post("/admin/users/{user_id}/delete", name="admin_user_delete")
def admin_user_delete(
    request: Request,
    user_id: int,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    """Remove a reader and everything they wrote.

    The privacy notice promises a reader can ask for deletion. This is the admin
    side of that promise, for when a request arrives by email.
    """
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    user = db.get(User, user_id)
    if user is not None:
        from ..services.accounts import delete_user

        address = user.email
        delete_user(db, user)
        # Recorded after the delete, because delete_user commits. The address
        # is kept: an erasure request needs an audit note saying it happened.
        audit.record(
            db,
            "user.delete",
            target_type="user",
            target_id=user_id,
            detail=f"reader {address} and their comments removed",
            ip_hash=audit.hash_ip(client_ip(request)),
        )

    return RedirectResponse("/admin/comments", status_code=303)


def session_id(request: Request) -> int | None:
    """Best-effort identity of the admin, for the moderation log."""
    token = current_session(request)
    if not token:
        return None
    from ..security import read_session_token

    admin = read_session_token(token)
    return 1 if admin else None


@router.post("/admin/apps/{slug}/delete", name="admin_app_delete")
def admin_app_delete(
    request: Request,
    slug: str,
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)
    if not guard_csrf(request, csrf):
        return _forbidden(request, db, "Your session expired.")

    record = db.scalar(select(AppDownload).where(AppDownload.slug == slug.lower()))
    if record is not None:
        title = record.title
        downloads = record.download_count
        apps.remove_stored(record.filename)
        # Remove the screenshot too, or it is orphaned on disk forever.
        apps.remove_stored_image(record.screenshot_filename or "")
        db.delete(record)
        audit.record(
            db,
            "app.delete",
            target_type="app",
            target_id=record.slug,
            detail=f"removed '{title}' and its file ({downloads} downloads)",
            ip_hash=audit.hash_ip(client_ip(request)),
            commit=False,
        )
        db.commit()

    return RedirectResponse("/admin/apps?deleted=1", status_code=303)


def _forbidden(request: Request, db: Session, message: str):
    return render(
        request,
        "error.html",
        admin_context(
            request,
            db,
            status_code=403,
            error_title="Request rejected",
            error_message=message,
        ),
        status_code=403,
    )
