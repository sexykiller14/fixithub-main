"""Hardware diagnostics guides."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import build_context, total_counts
from ..models import Article
from ..services.scripts_catalog import get_script
from ..templates import render

router = APIRouter()

# Hardware topics and the article that covers each one.
TOPICS: list[dict] = [
    {
        "slug": "ram",
        "title": "Memory (RAM) testing",
        "blurb": "MemTest86, Windows Memory Diagnostic, XMP and EXPO, and what a single error means",
        "article": "test-ram-memory-errors",
        "icon": "memory",
        "warning": "One error is a failure. Replace the module.",
        "script": "ram-diagnostics",
    },
    {
        "slug": "storage",
        "title": "SSD and HDD health",
        "blurb": "SMART counters, read-only chkdsk scans, and when to replace a drive",
        "article": "check-disk-health-ssd-hdd",
        "icon": "drive",
        "warning": "Back up before running any repair on a failing drive.",
        "script": "disk-health",
    },
    {
        "slug": "temperatures",
        "title": "CPU and GPU temperatures",
        "blurb": "Safe ranges, thermal throttling, dust, paste and airflow",
        "article": "fix-high-cpu-temperature",
        "icon": "temperature",
        "warning": "Repeated thermal shutdowns shorten hardware life.",
    },
    {
        "slug": "psu",
        "title": "Power supply problems",
        "blurb": "Symptom checklist, wattage sizing, and the swap test",
        "article": "psu-failure-symptoms",
        "icon": "power",
        "warning": "Never open a power supply.",
    },
    {
        "slug": "beep-codes",
        "title": "Beep codes and POST errors",
        "blurb": "Classic beep patterns and motherboard diagnostic LEDs",
        "article": "beep-codes-and-post-codes",
        "icon": "speaker",
        "warning": "Patterns vary by manufacturer; check your board manual.",
    },
    {
        "slug": "battery",
        "title": "Laptop battery health",
        "blurb": "powercfg reports, health percentages, and swollen batteries",
        "article": "fix-laptop-battery-health",
        "icon": "battery",
        "warning": "A swollen battery is a fire risk. Stop using it.",
    },
    {
        "slug": "ssd-upgrade",
        "title": "Replacing an HDD with an SSD",
        "blurb": "Choosing, cloning and the mistakes that break a migration",
        "article": "hdd-to-ssd-upgrade-guide",
        "icon": "upgrade",
        "warning": "Cloning erases the destination drive completely.",
    },
    {
        "slug": "ram-upgrade",
        "title": "Adding or upgrading RAM",
        "blurb": "DDR4 vs DDR5, SODIMM vs DIMM, matched kits and XMP",
        "article": "upgrade-ram-laptop-desktop",
        "icon": "upgrade",
        "warning": "DDR4 and DDR5 are not interchangeable.",
    },
    {
        "slug": "sleep-wake",
        "title": "Laptop sleep and wake faults",
        "blurb": "Power requests, Fast Startup, lid switches and driver conflicts",
        "article": "laptop-sleep-wake-issues",
        "icon": "sleep",
        "warning": "Disable Fast Startup before diagnosing sleep problems.",
    },
]


@router.get("/hardware", name="hardware_index")
def hardware_index(request: Request, db: Session = Depends(get_db)):
    topics = []
    for topic in TOPICS:
        article = db.query(Article).filter(Article.slug == topic["article"]).first()
        script = get_script(topic["script"]) if topic.get("script") else None
        topics.append({**topic, "article_row": article, "script_row": script.info if script else None})

    context = build_context(
        request,
        db,
        nav_open="hardware",
        topics=topics,
        counts=total_counts(db),
    )
    return render(request, "hardware_index.html", context)


@router.get("/hardware/{slug}", name="hardware_topic")
def hardware_topic(request: Request, slug: str, db: Session = Depends(get_db)):
    topic = next((item for item in TOPICS if item["slug"] == slug.lower()), None)
    if topic is None:
        return render(
            request,
            "404.html",
            build_context(
                request,
                db,
                nav_open="hardware",
                robots="noindex, nofollow",
                status_code=404,
                error_title="Guide not found",
                error_message=f"We do not have a hardware guide called '{slug}'.",
            ),
            status_code=404,
        )

    article = db.query(Article).filter(Article.slug == topic["article"]).first()
    if article is None:
        return render(
            request,
            "404.html",
            build_context(
                request,
                db,
                nav_open="hardware",
                robots="noindex, nofollow",
                status_code=404,
                error_title="Article missing",
                error_message="The guide for this topic has not been written yet.",
            ),
            status_code=404,
        )

    from ..services.content import load_all_articles
    from ..services.markdown import render as render_markdown

    rendered = render_markdown(article.body)
    others = [
        {"title": item["title"], "slug": item["slug"], "blurb": item["blurb"]}
        for item in TOPICS
        if item["slug"] != topic["slug"]
    ]

    script = get_script(topic["script"]) if topic.get("script") else None

    context = build_context(
        request,
        db,
        nav_open="hardware",
        topic=topic,
        article=article,
        rendered=rendered,
        toc=rendered.toc,
        others=others,
        script=script.info if script else None,
        script_source=script.source if script else None,
        counts=total_counts(db),
    )
    return render(request, "hardware_topic.html", context)
