"""Jinja2 environment setup and shared render helpers."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import HTMLResponse

from .config import CATEGORIES, DIFFICULTY_LABELS, SITE_DESCRIPTION, SITE_NAME, STATIC_DIR, TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Values that are needed even on error pages, where no database is available.
BASE_CONTEXT = {
    "site_name": SITE_NAME,
    "site_description": SITE_DESCRIPTION,
    "categories": CATEGORIES,
    "category_names": {key: value["name"] for key, value in CATEGORIES.items()},
    "difficulty_labels": DIFFICULTY_LABELS,
    "nav_open": "",
}


def _ads_context():
    """The ad settings row, cached for the duration of the request.

    Ads render on every page, so the settings row is read once per request
    rather than once per template. Returns None when ads are off, so the
    templates can output nothing with a single truthiness check.
    """
    from .models import AdSettings
    from .db import SessionLocal

    try:
        with SessionLocal() as db:
            row = db.query(AdSettings).first()
            if row is not None and row.enabled and row.publisher_id:
                return row
    except Exception:  # noqa: BLE001 - a broken ad config never breaks the page
        pass
    return None


def render(
    request: Request,
    template_name: str,
    context: dict[str, Any] | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    """Render a template with the shared context merged in."""
    merged = {**BASE_CONTEXT, **(context or {})}
    merged.setdefault("request", request)
    merged.setdefault("canonical_url", str(request.url).split("?")[0])
    merged.setdefault("current_path", request.url.path)

    # Ads are injected by the base template. The flag is off on admin pages,
    # login/account pages, and error pages (ads_config is None there), so the
    # admin and auth pages never carry ads and broken config never breaks a page.
    merged["ads_config"] = _ads_context()
    path = request.url.path
    is_admin = path.startswith("/admin")
    is_login_or_account = path in ("/login", "/signup", "/account", "/logout", "/verify")
    merged["ads_on"] = (
        merged["ads_config"] is not None
        and not is_admin
        and not is_login_or_account
        and status_code == 200
    )

    # Pre-group units by placement so the base template can loop once per
    # placement instead of scanning every unit for every placement.
    ads_units: dict[str, list] = {p: [] for p in ("header", "sidebar", "above-content", "below-content", "inside-content", "footer")}
    if merged["ads_on"]:
        from .models import AdUnit
        from .db import SessionLocal
        from .services.ads import unit_matches_page, render_unit, push_script

        is_homepage = path == "/"
        is_article = path.startswith("/articles/") and not path.endswith("/feedback")
        try:
            with SessionLocal() as db:
                units = (
                    db.query(AdUnit)
                    .filter(AdUnit.enabled.is_(True))
                    .order_by(AdUnit.created_at)
                    .all()
                )
                for unit in units:
                    if unit_matches_page(unit, path, is_homepage, is_article):
                        ads_units[unit.placement].append(
                            {"markup": render_unit(unit, merged["ads_config"].publisher_id), "push": push_script(unit)}
                        )
        except Exception:  # noqa: BLE001
            pass
    merged["ads_units"] = ads_units

    # The ad script tag is built here so the template never has to assemble the
    # AdSense URL, which is validated once at config time rather than per unit.
    from .services.ads import script_src
    merged["ads_script"] = script_src(merged["ads_config"].publisher_id) if merged["ads_config"] else ""

    # SEO overrides are path-keyed. Applied after route-provided values, so an
    # admin edit always wins over the template's own og_title/og_description.
    from .models import SeoOverride
    from .db import SessionLocal

    seo_override = None
    seo_settings = None
    try:
        with SessionLocal() as db:
            seo_override = db.query(SeoOverride).filter(SeoOverride.path == path).first()
            from .models import SiteSeoSettings
            seo_settings = db.query(SiteSeoSettings).first()
    except Exception:  # noqa: BLE001
        pass

    merged["seo_title"] = seo_override.title if seo_override and seo_override.title else ""
    merged["seo_description"] = seo_override.description if seo_override and seo_override.description else ""
    merged["seo_image"] = seo_override.og_image if seo_override else ""
    merged["seo_sitemap_priority"] = seo_override.sitemap_priority if seo_override else ""
    merged["seo_sitemap_changefreq"] = seo_override.sitemap_changefreq if seo_override else ""
    merged["seo_settings"] = seo_settings

    # The announcement banner is shown on every public page. Plain text, no
    # markup, so admin input cannot break the page.
    from .models import Announcement
    try:
        with SessionLocal() as db:
            merged["announcement"] = (
                db.query(Announcement).order_by(Announcement.id.desc()).first()
            )
    except Exception:  # noqa: BLE001
        merged["announcement"] = None

    return templates.TemplateResponse(
        request,
        template_name,
        merged,
        status_code=status_code,
        headers=headers,
    )


def render_fragment(template_name: str, context: dict[str, Any]) -> str:
    """Render a template to a string, for templates without a request."""
    return templates.get_template(template_name).render(context)


def _markdown_filter(markdown_text: str):
    """Render trusted markdown for display.

    Admin-authored prose only. It goes through the same sanitiser as article
    bodies, so a script or event handler in this field is stripped rather than
    rendered.

    The result is wrapped in Markup because the sanitiser has already done the
    work. Returning a plain str would make Jinja escape it a second time and the
    reader would see literal tags on the page.
    """
    from markupsafe import Markup

    from .services.markdown import render as render_markdown

    if not markdown_text or not markdown_text.strip():
        return Markup("")
    return Markup(render_markdown(markdown_text).html)


templates.env.filters["markdown_safe"] = _markdown_filter


def _wordcount_filter(text: str) -> int:
    import re

    return len(re.findall(r"\S+", text or ""))


templates.env.filters["wordcount"] = _wordcount_filter


@lru_cache(maxsize=4)
def _cached_fragment(template_name: str, cache_key: tuple) -> str:
    return templates.get_template(template_name).render(dict(cache_key))


def render_error(template_name: str, context: dict[str, Any]) -> str:
    """Render an error template outside the request/response cycle."""
    merged = {**BASE_CONTEXT, **context}
    # Error pages never carry ads, even when ads are enabled. Spreading the
    # BASE_CONTEXT alone would leave ads_config undefined, which is truthy
    # enough for Jinja to try rendering it.
    merged["ads_config"] = None
    merged["ads_on"] = False
    return templates.get_template(template_name).render(merged)


def static_url(path: str) -> str:
    """Static asset URL. StaticFiles handles caching via Last-Modified."""
    return f"/static/{path.lstrip('/')}"
