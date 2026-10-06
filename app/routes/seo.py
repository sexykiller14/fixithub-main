"""SEO endpoints: sitemap.xml and robots.txt."""

from __future__ import annotations

from datetime import date
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import CATEGORIES, SITE_URL
from ..db import get_db
from ..models import AppDownload, Article, StopCode
from ..services.scripts_catalog import list_scripts
from ..services.wizards import list_wizards

router = APIRouter()

STATIC_ROUTES: list[tuple[str, float, str]] = [
    ("/", 1.0, "weekly"),
    ("/articles", 0.9, "weekly"),
    ("/bsod", 0.9, "weekly"),
    ("/bsod/analyze", 0.6, "monthly"),
    ("/wizards", 0.9, "weekly"),
    ("/tools", 0.7, "monthly"),
    ("/tools/dns", 0.6, "monthly"),
    ("/tools/port", 0.6, "monthly"),
    ("/tools/status", 0.6, "monthly"),
    ("/tools/latency", 0.6, "monthly"),
    ("/tools/ip", 0.5, "monthly"),
    ("/drivers", 0.8, "monthly"),
    ("/hardware", 0.8, "monthly"),
    ("/scripts", 0.7, "monthly"),
    ("/apps", 0.6, "monthly"),
    ("/privacy", 0.3, "yearly"),
    ("/about", 0.4, "yearly"),
]

PRIORITIES = {
    "/": "1.0",
    "/articles": "0.9",
    "/bsod": "0.9",
    "/bsod/analyze": "0.7",
    "/wizards": "0.9",
    "/drivers": "0.8",
    "/hardware": "0.8",
}


@router.get("/sitemap.xml", name="sitemap")
def sitemap(request: Request, db: Session = Depends(get_db)):
    """Generate the full sitemap from the live database."""
    base = SITE_URL.rstrip("/")
    today = date.today().isoformat()
    entries: list[tuple[str, str, str, str]] = []

    from ..models import SeoOverride, SiteSeoSettings

    overrides = {o.path: o for o in db.query(SeoOverride).all()}
    site_settings = db.query(SiteSeoSettings).first()
    default_changefreq = site_settings.default_changefreq if site_settings else "monthly"
    default_priority = site_settings.default_priority if site_settings else "0.5"

    for path, _weight, _freq in STATIC_ROUTES:
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else default_priority
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    for slug in CATEGORIES:
        path = f"/category/{slug}"
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else "0.7"
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    for slug in sorted(db.execute(select(Article.slug)).scalars()):
        path = f"/articles/{slug}"
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else "0.7"
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    for name in sorted(db.execute(select(StopCode.name)).scalars()):
        path = f"/bsod/{name}"
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else "0.6"
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    for wizard in list_wizards():
        path = f"/wizards/{wizard.id}"
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else "0.9"
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    for script in list_scripts():
        path = f"/scripts/{script.slug}"
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else "0.6"
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    # Only published uploads belong in an index. Drafts 404 publicly, so
    # listing them would advertise a URL that does not resolve.
    published = db.execute(
        select(AppDownload.slug).where(AppDownload.is_published.is_(True))
    ).scalars()
    for slug in sorted(published):
        path = f"/apps/{slug}"
        ov = overrides.get(path)
        priority = ov.sitemap_priority if ov and ov.sitemap_priority else "0.5"
        entries.append((path, priority, today, ov.sitemap_changefreq if ov and ov.sitemap_changefreq else default_changefreq))

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for path, priority, updated, changefreq in entries:
        parts.append("  <url>")
        parts.append(f"    <loc>{escape(base + path)}</loc>")
        parts.append(f"    <lastmod>{updated}</lastmod>")
        parts.append(f"    <changefreq>{escape(changefreq)}</changefreq>")
        parts.append(f"    <priority>{escape(priority)}</priority>")
        parts.append("  </url>")
    parts.append("</urlset>")

    body = "\n".join(parts)
    return Response(
        content=body,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/ads.txt", name="ads_txt")
def ads_txt(request: Request, db: Session = Depends(get_db)):
    """Serve the admin-provided ads.txt verbatim."""
    from ..models import AdSettings

    row = db.query(AdSettings).first()
    body = row.ads_txt if row is not None else ""
    return PlainTextResponse(
        body,
        media_type="text/plain",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/robots.txt", name="robots")
def robots(request: Request):
    base = SITE_URL.rstrip("/")
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /admin/",
            "Disallow: /api/",
            "Disallow: /tools/api/",
            "",
            "# Account pages are per-visitor and useless in an index.",
            "Disallow: /login",
            "Disallow: /signup",
            "Disallow: /account",
            "Disallow: /logout",
            "Disallow: /verify/",
            "",
            "# Query-string search results and uploaded-dump results are not useful in an index.",
            "Disallow: /search?",
            "Disallow: /bsod/lookup?",
            "",
            f"Sitemap: {base}/sitemap.xml",
            "",
        ]
    )
    return PlainTextResponse(
        body, media_type="text/plain", headers={"Cache-Control": "public, max-age=86400"}
    )
