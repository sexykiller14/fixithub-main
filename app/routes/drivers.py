"""Driver help pages: vendor guides and Device Manager error codes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DEVICE_MANAGER_CODES, VENDORS
from ..db import get_db
from ..deps import build_context, total_counts
from ..models import Article
from ..templates import render

router = APIRouter()

# Display order and the guide article each vendor page links to.
VENDOR_SLUGS = {
    "nvidia": "nvidia-driver-guide",
    "amd": "amd-driver-guide",
    "intel": "intel-driver-guide",
    "realtek": "realtek-audio-network-drivers",
    "lenovo": None,
    "msi": None,
    "asus": None,
    "microsoft": None,
}


@router.get("/drivers", name="drivers_index")
def drivers_index(request: Request, db: Session = Depends(get_db)):
    vendors = []
    for key, meta in VENDORS.items():
        vendors.append(
            {
                "key": key,
                "name": meta["name"],
                "downloads": meta["downloads"],
                "note": meta["note"],
                "article_slug": VENDOR_SLUGS.get(key),
            }
        )

    context = build_context(
        request,
        db,
        nav_open="drivers",
        vendors=vendors,
        codes=DEVICE_MANAGER_CODES,
        counts=total_counts(db),
    )
    return render(request, "drivers_index.html", context)


@router.get("/drivers/{slug}", name="driver_detail")
def driver_detail(request: Request, slug: str, db: Session = Depends(get_db)):
    slug = slug.lower()

    if slug == "device-manager-codes":
        return render(
            request,
            "drivers_codes.html",
            build_context(
                request,
                db,
                nav_open="drivers",
                codes=DEVICE_MANAGER_CODES,
                counts=total_counts(db),
            ),
        )

    meta = VENDORS.get(slug)
    if meta is None:
        return render(
            request,
            "404.html",
            build_context(
                request,
                db,
                nav_open="drivers",
                robots="noindex, nofollow",
                status_code=404,
                error_title="Vendor not found",
                error_message=f"We do not have a driver guide for '{slug}'.",
            ),
            status_code=404,
        )

    article = db.scalar(select(Article).where(Article.slug == VENDOR_SLUGS.get(slug or "")))
    others = [
        {"key": key, "name": value["name"], "downloads": value["downloads"]}
        for key, value in VENDORS.items()
        if key != slug
    ]

    context = build_context(
        request,
        db,
        nav_open="drivers",
        vendor=meta,
        vendor_key=slug,
        article=article,
        other_vendors=others,
        codes=DEVICE_MANAGER_CODES,
        counts=total_counts(db),
    )
    return render(request, "driver_detail.html", context)
