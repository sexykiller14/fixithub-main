"""Admin panel: password-protected CRUD for articles and stop codes."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile

import yaml
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

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
    create_session_token,
    generate_csrf,
    hash_password,
    load_admin_hash,
    login_locked_out,
    record_login_failure,
    save_admin_hash,
    set_session_cookie,
    valid_csrf,
    verify_password,
)
from ..services.content import load_article_file, slug_from_filename
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


def admin_context(request: Request, db: Session, **extra):
    return build_context(
        request,
        db,
        nav_open="admin",
        csrf=csrf_token(request),
        categories=CATEGORIES,
        difficulty_labels=DIFFICULTY_LABELS,
        counts=total_counts(db),
        **extra,
    )


# ------------------------------------------------------------------- login


LOGIN_CSRF_COOKIE = "fixithub_login_csrf"


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
    identifier = request.client.host if request.client else "unknown"

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
        return back("", "Incorrect password.", code=401)

    clear_login_failures(identifier)
    token = create_session_token()
    response = RedirectResponse("/admin/dashboard", status_code=303)
    set_session_cookie(response, token)
    response.delete_cookie(LOGIN_CSRF_COOKIE, path="/")
    return response


@router.get("/admin/reissue-csrf", name="admin_reissue_csrf")
def admin_reissue_csrf(request: Request):
    """Hand out a fresh login CSRF token, for when a form sits open too long."""
    token = _mint_login_csrf()
    response = Response(status_code=204)
    _set_login_csrf_cookie(response, token)
    response.headers["X-CSRF-Token"] = token
    return response


# --------------------------------------------------------------- dashboard


@router.get("/admin/dashboard", name="admin_dashboard")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    stats = {
        "articles": db.query(Article).count(),
        "stop_codes": db.query(StopCode).count(),
        "feedback": feedback_summary(db),
        "searches": db.query(SearchQuery).count(),
        "dumps": db.query(DumpUpload).count(),
        "apps": db.query(AppDownload).count(),
        "users": db.query(User).count(),
        "comments_pending": db.scalar(
            select(func.count())
            .select_from(Comment)
            .where(Comment.status == Comment.STATUS_PENDING)
        )
        or 0,
        "feedback_rows": db.query(Feedback).count(),
        "questions_pending": db.scalar(
            select(func.count())
            .select_from(Question)
            .where(Question.status == Question.STATUS_NEW)
        )
        or 0,
        "questions_total": db.query(Question).count(),
    }

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
def admin_logout(request: Request, csrf: str = Form("", max_length=200)):
    if not guard_csrf(request, csrf):
        return RedirectResponse("/admin", status_code=303)
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
        db.delete(row)
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
        db.delete(row)
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

    row.title = title.strip()
    row.body = body.strip()
    row.link_url = link_url.strip()
    row.enabled = bool(enabled)
    db.commit()
    return RedirectResponse("/admin/announcement?saved=1", status_code=303)


@router.get("/admin/backup", name="admin_backup")
def admin_backup(request: Request, db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    import io
    import zipfile

    from ..db import engine

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # SQLite needs a backup copy rather than reading the live file.
        import sqlite3

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        try:
            # Connect URI form is required so SQLite can open the file in
            # backup mode rather than as a WAL follower.
            db_path = str(engine.url).replace("sqlite:///", "")
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

    raw = file.file.read()
    if not raw:
        return _forbidden(request, db, "Upload a backup zip.")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        return _forbidden(request, db, "That file is not a valid zip.")

    names = zf.namelist()
    if "fixithub.db" not in names:
        return _forbidden(request, db, "That zip does not contain a database.")

    # Snapshot the live files first. The download URL is returned in the
    # response so the admin can recover from a bad restore.
    import tempfile

    snapshot_dir = Path(tempfile.mkdtemp(prefix="fixithub-restore-snapshot-"))
    snapshot = snapshot_dir / "backup-before-restore.zip"
    with zipfile.ZipFile(snapshot, "w") as out:
        import sqlite3

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp.close()
        try:
            db_path = str(engine.url).replace("sqlite:///", "")
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
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

    # Close the live database, swap the files, then let the engine reconnect.
    engine.dispose()
    tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp_db.close()
    tmp_path = Path(tmp_db.name)
    try:
        with open(tmp_path, "wb") as out:
            out.write(zf.read("fixithub.db"))

        db_path = Path(str(engine.url).replace("sqlite:///", ""))
        os.replace(tmp_path, db_path)

        if "admin.json" in names:
            with open(ADMIN_HASH_FILE, "wb") as out:
                out.write(zf.read("admin.json"))

        # Re-open the engine on the new file so the next request works.
        create_all()
    except Exception as exc:  # noqa: BLE001
        log.exception("Restore failed")
        return _forbidden(request, db, f"Restore failed: {exc}")

    return render(
        request,
        "admin_restore_done.html",
        admin_context(
            request,
            db,
            snapshot_filename=snapshot.name,
        ),
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
    from pathlib import Path

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
        # Per-day view rows reference the article, so clear them first.
        db.execute(delete(ArticleView).where(ArticleView.article_id == article.id))
        db.delete(article)
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
        db.delete(code)
        db.commit()

    return RedirectResponse("/admin/stop-codes?deleted=1", status_code=303)


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
    context = admin_context(
        request,
        db,
        apps=rows,
        app_categories=APP_CATEGORIES,
        max_app_mb=MAX_APP_BYTES // 1024 // 1024,
        allowed_suffixes=", ".join(ALLOWED_SUFFIXES),
    )
    return render(request, "admin_apps.html", context)


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
    db.commit()

    _index_after_write(db)
    return RedirectResponse(f"/admin/apps?saved={clean_slug}", status_code=303)


# ------------------------------------------------------------- moderation


@router.get("/admin/comments", name="admin_comments")
def admin_comments(request: Request, status_filter: str = "", db: Session = Depends(get_db)):
    if not require_auth(request):
        return RedirectResponse("/admin", status_code=303)

    wanted = status_filter if status_filter in Comment.STATUSES else ""

    query = select(Comment).order_by(desc(Comment.created_at)).limit(200)
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
        db.delete(comment)
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

        delete_user(db, user)

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
        apps.remove_stored(record.filename)
        # Remove the screenshot too, or it is orphaned on disk forever.
        apps.remove_stored_image(record.screenshot_filename or "")
        db.delete(record)
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
