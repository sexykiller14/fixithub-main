"""FastAPI application factory for FixIT Hub."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import SITE_DESCRIPTION, SITE_NAME, STATIC_DIR, settings
from .db import create_all

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("fixithub")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-XSS-Protection": "0",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}

# Sent only when the deployment is actually on HTTPS. Emitting HSTS over plain
# HTTP is meaningless at best and locks a developer out of http://localhost at
# worst, so it is gated on the same flag as the Secure cookie.
HSTS_HEADER = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "object-src 'none'"
)

# Stacked on top of CSP when ads are on. AdSense loads its own script from a
# Google domain and serves creatives from its own iframe domains, so the
# sources have to be allowlisted or none of the units will run. Kept out of the
# base policy so ads-off means zero third-party allowances.
AD_CSP_ADDITIONS = (
    " https://pagead2.googlesyndication.com"
    " https://www.googletagmanager.com"
    " https://www.google-analytics.com"
    " https://tpc.googlesyndication.com"
)
AD_IMG_SRC = " https://www.googlesyndication.com https://pagead2.googlesyndication.com https://googleads.g.doubleclick.net https://tpc.googlesyndication.com"
AD_FRAME_SRC = " https://googleads.g.doubleclick.net https://tpc.googlesyndication.com"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create tables on startup so a fresh clone runs without a manual step.

    Also refuses to start in production with an unset FIXITHUB_SECRET_KEY. The
    fallback is a random key per process, which looks like it works - the
    server boots, one admin signs in - and then silently breaks: every restart
    invalidates every session, and under multiple workers a cookie is rejected
    by whichever worker did not sign it. Failing here is louder and cheaper
    than an unexplained logout later.
    """
    if settings.secret_key_configured:
        log.info("%s started with a configured secret key", SITE_NAME)
    else:
        message = (
            "FIXITHUB_SECRET_KEY is not set. Sessions and CSRF tokens are signed "
            "with a key generated at startup, so they do not survive a restart "
            "and are rejected by other workers. Set FIXITHUB_SECRET_KEY to a "
            "long random value in production."
        )
        # Dev must keep working without ceremony: seed.py, the tests and a
        # first local run all rely on the generated key. Production should not
        # boot with it.
        if _is_production(settings):
            raise RuntimeError(message)
        log.warning("%s WARNING: %s", SITE_NAME, message)

    create_all()
    from .db import seed_if_empty

    seed_if_empty()
    log.info("%s started (debug=%s)", SITE_NAME, settings.debug)
    yield
    log.info("%s stopped", SITE_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=SITE_NAME,
        description=SITE_DESCRIPTION,
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Signed cookie session, used only for wizard progress and the admin login.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="fixithub_session",
        max_age=60 * 60 * 8,
        same_site="lax",
        https_only=settings.secure_cookies,
    )

    from .routes import (
        accounts,
        admin,
        apps,
        articles,
        ask,
        bsod,
        comments,
        drivers,
        hardware,
        pages,
        scripts,
        search,
        seo,
        tools,
        wizards,
    )

    for module in (
        pages.router,
        search.router,
        articles.router,
        bsod.router,
        wizards.router,
        tools.router,
        drivers.router,
        scripts.router,
        hardware.router,
        apps.router,
        accounts.router,
        comments.router,
        ask.router,
        admin.router,
        seo.router,
    ):
        app.include_router(module)

    install_middleware(app)
    install_handlers(app)
    return app


def _build_csp() -> str:
    """The CSP for the current request state.

    When ads are enabled, the Google domains AdSense needs are appended. Reading
    the row here means flipping ads on takes effect without a restart.
    """
    from .db import SessionLocal
    from .models import AdSettings

    try:
        with SessionLocal() as db:
            row = db.query(AdSettings).first()
            if row is not None and row.enabled and row.publisher_id:
                csp = CSP
                # Easiest way to append: rebuild the string rather than tracking
                # which directives need which additions.
                csp = csp.replace(
                    "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com",
                    f"script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com{AD_CSP_ADDITIONS}",
                )
                csp = csp.replace("img-src 'self' data:", f"img-src 'self' data:{AD_IMG_SRC}")
                csp = csp.replace("connect-src 'self'", f"connect-src 'self'{AD_CSP_ADDITIONS}")
                csp = csp.replace(
                    "object-src 'none'",
                    f"object-src 'none'; frame-src 'self'{AD_FRAME_SRC}",
                )
                return csp
    except Exception:  # noqa: BLE001 - a bad ad config must not break headers
        pass
    return CSP


def _is_production(settings_obj) -> bool:
    """Whether this process should be treated as a real deployment.

    Deliberately conservative, because the alternative is refusing to start a
    developer who has not read the README. It does not trust debug mode either
    way: a production deploy with debug accidentally off is exactly the case
    worth catching. FIXITHUB_ENV is the explicit switch, and serving over HTTPS
    (secure cookies on) counts as production, since nothing else does that.
    """
    if os.environ.get("FIXITHUB_ENV", "").strip().lower() == "production":
        return True
    return bool(settings_obj.secure_cookies)


def install_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.secure_cookies:
            # Only over HTTPS, for the reason on HSTS_HEADER.
            for header, value in HSTS_HEADER.items():
                response.headers.setdefault(header, value)
        # Tailwind needs to load from its CDN, and our own CSS/JS from 'self'.
        response.headers.setdefault("Content-Security-Policy", _build_csp())
        return response


def install_handlers(app: FastAPI) -> None:
    from .templates import render_error

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException):
        if request.url.path.startswith(("/tools/api", "/api")):
            return JSONResponse(
                status_code=exc.status_code,
                content={"ok": False, "error": str(exc.detail)},
            )

        if exc.status_code in (301, 302, 307, 308) and exc.headers.get("location"):
            return RedirectResponse(
                exc.headers["location"], status_code=exc.status_code
            )

        template = "404.html" if exc.status_code == 404 else "error.html"
        context: dict = {
            "site_name": SITE_NAME,
            "site_description": SITE_DESCRIPTION,
            "canonical_url": request.url.path,
            "categories": {},
            "category_names": {},
            "difficulty_labels": {},
            "current_path": request.url.path,
            "status_code": exc.status_code,
            "error_title": {
                403: "Access denied",
                404: "Page not found",
                429: "Too many requests",
                500: "Something went wrong",
            }.get(exc.status_code, "Request failed"),
            "error_message": str(exc.detail),
            "nav_open": "",
        }
        return HTMLResponse(
            render_error(template, context), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        message = first.get("msg", "Invalid input.")
        if message.startswith("value_error."):
            message = message.split("value_error. ", 1)[-1]
        if request.url.path.startswith(("/tools/api", "/api")):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"ok": False, "error": str(message)},
            )
        context = {
            "site_name": SITE_NAME,
            "site_description": SITE_DESCRIPTION,
            "canonical_url": request.url.path,
            "categories": {},
            "category_names": {},
            "difficulty_labels": {},
            "current_path": request.url.path,
            "status_code": 422,
            "error_title": "Invalid input",
            "error_message": str(message),
            "nav_open": "",
        }
        return HTMLResponse(
            render_error("error.html", context),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("Unhandled error on %s", request.url.path)
        if request.url.path.startswith(("/tools/api", "/api")):
            return JSONResponse(
                status_code=500, content={"ok": False, "error": "Internal server error."}
            )
        return HTMLResponse(
            render_error(
                "error.html",
                {
                    "site_name": SITE_NAME,
                    "site_description": SITE_DESCRIPTION,
                    "canonical_url": request.url.path,
                    "categories": {},
                    "category_names": {},
                    "difficulty_labels": {},
                    "current_path": request.url.path,
                    "status_code": 500,
                    "error_title": "Something went wrong",
                    "error_message": (
                        str(exc)
                        if settings.debug
                        else "An unexpected error occurred. It has been logged."
                    ),
                    "nav_open": "",
                },
            ),
            status_code=500,
        )


app = create_app()


async def _healthcheck() -> PlainTextResponse:
    """Confirm the database is reachable."""
    from sqlalchemy import text

    from .db import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - report unhealthy rather than raising
        return PlainTextResponse("unhealthy", status_code=503)
    return PlainTextResponse("ok")


# /healthz is the documented path; /health is kept because load balancers and
# container orchestrators commonly expect that name.
app.add_api_route("/healthz", _healthcheck, methods=["GET"], include_in_schema=False)
app.add_api_route("/health", _healthcheck, methods=["GET"], include_in_schema=False)
