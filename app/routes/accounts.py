"""Reader accounts: sign up, sign in, verification and password reset."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import USER_SESSION_COOKIE, settings
from ..models import Comment
from ..db import get_db
from ..deps import build_context, total_counts
from ..models import User
from ..rate_limit import SlidingWindowLimiter, enforce
from ..security import valid_reader_csrf
from ..services import accounts
from ..templates import render

log = logging.getLogger(__name__)

router = APIRouter()

SESSION_COOKIE = USER_SESSION_COOKIE

# Signing in is the interesting target for credential stuffing, so it is held
# tighter than the general feedback bucket.
signin_limiter = SlidingWindowLimiter(10, 300)
signup_limiter = SlidingWindowLimiter(5, 3600)

MAX_EMAIL = 254


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": "lax",
        "path": "/",
    }


def _set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(accounts.SESSION_TTL.total_seconds()),
        **_cookie_kwargs(),
    )


def signed_in_reader(request: Request, db: Session) -> User | None:
    """The signed-in reader, or None.

    Named apart from the service helper of similar purpose, which takes
    (db, raw_token). Two same-named helpers with swapped arguments is a trap.
    """
    return accounts.current_user(db, request.cookies.get(SESSION_COOKIE))


def require_user(request: Request, db: Session) -> User | None:
    """Signed-in reader, or a redirect to the sign-in page."""
    user = signed_in_reader(request, db)
    if user is None:
        return None
    return user


def redirect_to_login(request: Request) -> RedirectResponse:
    """Send an anonymous visitor to sign in, remembering where they were."""
    target = str(request.url).split("?")[0]
    nxt = request.url.query
    suffix = f"?next={nxt}" if nxt else ""
    return RedirectResponse(f"/login?next={target}{suffix}", status_code=303)


def redirect_if_signed_in(request: Request, db: Session) -> RedirectResponse | None:
    if signed_in_reader(request, db) is not None:
        return RedirectResponse("/account", status_code=303)
    return None


def _page(request: Request, db: Session, template: str, *, code: int = 200, **extra):
    context = build_context(
        request,
        db,
        nav_open="",
        current_user=signed_in_reader(request, db),
        registration_open=settings.allow_registration,
        smtp_configured=accounts.smtp_configured(),
        counts=total_counts(db),
        **extra,
    )
    return render(request, template, context, status_code=code)


# ------------------------------------------------------------- sign up


@router.get("/signup", name="signup")
def signup_form(request: Request, db: Session = Depends(get_db)):
    existing = redirect_if_signed_in(request, db)
    if existing is not None:
        return existing

    if not settings.allow_registration:
        return _page(
            request,
            db,
            "account_closed.html",
            code=403,
            error_title="Registration is closed",
            error_message=(
                "This site is not accepting new accounts right now. Everything "
                "on it is readable without one."
            ),
        )

    return _page(request, db, "signup.html", next=request.query_params.get("next", ""))


@router.post("/signup", name="signup_post")
def signup_post(
    request: Request,
    email: str = Form("", max_length=MAX_EMAIL),
    password: str = Form("", max_length=accounts.MAX_PASSWORD),
    confirm: str = Form("", max_length=accounts.MAX_PASSWORD),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    limited = enforce(
        request,
        signup_limiter,
        prefix="signup",
        message="Too many accounts created from this connection. Try again later.",
    )
    if limited is not None:
        return limited

    if not settings.allow_registration:
        return _page(
            request,
            db,
            "account_closed.html",
            code=403,
            error_title="Registration is closed",
            error_message="New accounts are not being accepted right now.",
        )

    if not valid_reader_csrf(request, csrf):
        return _page(
            request,
            db,
            "signup.html",
            code=400,
            error_message="Your form expired. Please try again.",
            email=email,
        )

    if password != confirm:
        return _page(
            request,
            db,
            "signup.html",
            code=400,
            error_message="The two passwords did not match.",
            email=email,
        )

    try:
        user, token = accounts.create_user(db, email, password)
    except accounts.AccountError as exc:
        return _page(
            request, db, "signup.html", code=400, error_message=str(exc), email=email
        )

    sent = accounts.send_verification_email(user, token.raw)
    if not sent:
        # Not fatal. The account exists and the admin can verify it by hand, so
        # saying so is more useful than reporting a failure the reader cannot
        # act on.
        log.warning("Verification email not sent for user %s (SMTP unconfigured)", user.id)

    # Sign them straight in. They still cannot download until verified, but
    # making them confirm a password first is needless friction.
    session = accounts.start_session(db, user)
    response = RedirectResponse(f"/account?verify={'sent' if sent else 'pending'}", status_code=303)
    _set_session_cookie(response, session.raw)
    return response


# ---------------------------------------------------------------- sign in


@router.get("/login", name="login")
def login_form(request: Request, db: Session = Depends(get_db)):
    existing = redirect_if_signed_in(request, db)
    if existing is not None:
        return existing
    return _page(
        request, db, "login.html", next=request.query_params.get("next", "")
    )


@router.post("/login", name="login_post")
def login_post(
    request: Request,
    email: str = Form("", max_length=MAX_EMAIL),
    password: str = Form("", max_length=accounts.MAX_PASSWORD),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    limited = enforce(
        request,
        signin_limiter,
        prefix="signin",
        message="Too many sign-in attempts. Wait a few minutes and try again.",
    )
    if limited is not None:
        return limited

    if not valid_reader_csrf(request, csrf):
        return _page(
            request,
            db,
            "login.html",
            code=400,
            error_message="Your form expired. Please try again.",
            next=request.query_params.get("next", ""),
        )

    user = accounts.check_password(db, email, password)
    if user is None:
        # One message for both an unknown address and a wrong password, so the
        # form cannot be used to find out which addresses have accounts.
        return _page(
            request,
            db,
            "login.html",
            code=401,
            error_message="That email address and password do not match an account.",
        )

    session = accounts.start_session(db, user)
    response = RedirectResponse("/account", status_code=303)
    _set_session_cookie(response, session.raw)
    return response


@router.get("/logout", name="logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """End the session on the server as well as clearing the cookie.

    A GET is deliberate: it matches the other wizard-style GET actions in this
    app, and the only effect is discarding the visitor's own session.
    """
    accounts.end_session(db, request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# ------------------------------------------------------------- verify


@router.get("/verify/{token}", name="verify")
def verify(request: Request, token: str, db: Session = Depends(get_db)):
    token = token[:200]
    ok = accounts.verify_email(db, token)
    if ok:
        return _page(
            request,
            db,
            "verify.html",
            verified=True,
        )
    return _page(
        request,
        db,
        "verify.html",
        code=400,
        verified=False,
    )


# -------------------------------------------------------------- account


@router.get("/account", name="account")
def account_page(request: Request, db: Session = Depends(get_db)):
    user = signed_in_reader(request, db)
    if user is None:
        return redirect_to_login(request)

    comment_count = db.scalar(
        select(func.count()).select_from(Comment).where(Comment.user_id == user.id)
    )

    return _page(
        request,
        db,
        "account.html",
        account=user,
        comment_count=comment_count or 0,
    )


@router.post("/account/delete", name="account_delete")
def account_delete(
    request: Request,
    confirm: str = Form("", max_length=40),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    """Delete the account and everything written under it.

    This is the deletion right promised on the privacy page, so it removes the
    comments rather than anonymising them.
    """
    user = signed_in_reader(request, db)
    if user is None:
        return redirect_to_login(request)

    if not valid_reader_csrf(request, csrf):
        return _page(
            request,
            db,
            "account.html",
            code=403,
            account=user,
            comment_count=0,
            error_message="Your session expired. Please try again.",
        )

    if confirm.strip().upper() != "DELETE":
        return _page(
            request,
            db,
            "account.html",
            code=400,
            account=user,
            comment_count=0,
            error_message="Type DELETE in the box to confirm.",
        )

    accounts.end_session(db, request.cookies.get(SESSION_COOKIE))
    accounts.delete_user(db, user)

    response = RedirectResponse("/account/deleted", status_code=303)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/account/deleted", name="account_deleted")
def account_deleted(request: Request, db: Session = Depends(get_db)):
    return _page(request, db, "account_deleted.html")