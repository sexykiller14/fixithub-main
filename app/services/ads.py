"""Ads settings and rendering helpers.

This module is the only place that knows how a validated <ins> tag is built.
Everything else stores structured fields and calls render_unit, so there is no
way for an admin to paste raw HTML into the site.
"""

from __future__ import annotations

import re
from html import escape

from ..models import AdSettings, AdUnit

# ---------------------------------------------------------------- enums

FORMATS = AdUnit.FORMATS
PLACEMENTS = AdUnit.PLACEMENTS
SHOW_ON = AdUnit.SHOW_ON
DEVICES = AdUnit.DEVICES

# ------------------------------------------------------------- validation

# Format as Google hands it to you in the AdSense console.
PUBLISHER_RE = re.compile(r"^ca-pub-\d{16}$")
SLOT_RE = re.compile(r"^\d+$")
LAYOUT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PATH_RE = re.compile(r"^/[A-Za-z0-9\-/]*$")

# Hard caps so a stray paste cannot grow the settings row without bound.
MAX_LABEL = 120
MAX_ADS_TXT = 4000


def validate_publisher_id(value: str) -> str:
    """Reject the empty case differently: it disables ads, not an error."""
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if not PUBLISHER_RE.match(cleaned):
        raise ValueError("Publisher ID must look like ca-pub-1234567890123456.")
    return cleaned


def validate_slot_id(value: str) -> str:
    cleaned = (value or "").strip()
    if not SLOT_RE.match(cleaned):
        raise ValueError("Ad slot ID must be numeric.")
    return cleaned


def validate_layout_key(value: str, format: str) -> str:
    cleaned = (value or "").strip()
    if format in ("in-article", "in-feed"):
        if not cleaned:
            raise ValueError(
                "In-article and in-feed units need the layout key from the "
                "AdSense console, or Google renders nothing."
            )
        if not LAYOUT_KEY_RE.match(cleaned):
            raise ValueError("Layout key may only contain letters, numbers, - and _.")
        return cleaned
    # Ignored for every other format; silently discard it so editing a unit
    # back to 'auto' does not leave a stale key behind.
    return ""


def validate_paths(raw: str) -> str:
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    for part in parts:
        if not PATH_RE.match(part):
            raise ValueError(
                f"'{part}' is not a valid page path. Use paths like / or /articles."
            )
    return ", ".join(parts)


def validate_ad_settings(enabled, publisher_id, auto_ads, ads_txt) -> dict:
    """Coerce and check the settings form. Raises ValueError on the first problem."""
    if enabled and not (publisher_id or "").strip():
        raise ValueError("Add a publisher ID before enabling ads.")
    return {
        "enabled": bool(enabled),
        "publisher_id": validate_publisher_id(publisher_id),
        "auto_ads": bool(auto_ads),
        "ads_txt": (ads_txt or "").strip()[:MAX_ADS_TXT],
    }


def validate_unit(label, slot_id, format, placement, nth_paragraph, layout_key, show_on, selected_paths, device) -> dict:
    if format not in FORMATS:
        raise ValueError(f"Unknown format '{format}'.")
    if placement not in PLACEMENTS:
        raise ValueError(f"Unknown placement '{placement}'.")
    if show_on not in SHOW_ON:
        raise ValueError(f"Unknown show-on '{show_on}'.")
    if device not in DEVICES:
        raise ValueError(f"Unknown device '{device}'.")

    try:
        nth = int(nth_paragraph)
    except (TypeError, ValueError):
        raise ValueError("Nth paragraph must be a number.")
    if nth < 1 or nth > 50:
        raise ValueError("Nth paragraph must be between 1 and 50.")

    return {
        "label": (label or "").strip()[:MAX_LABEL],
        "slot_id": validate_slot_id(slot_id),
        "format": format,
        "placement": placement,
        "nth_paragraph": nth,
        "layout_key": validate_layout_key(layout_key, format),
        "show_on": show_on,
        "selected_paths": validate_paths(selected_paths),
        "device": device,
    }


# ------------------------------------------------------------ show-on logic


def inject_inside_content(html: str, unit_markup: str, nth_paragraph: int) -> str:
    """Insert a unit inside an article body, after the Nth closing paragraph tag.

    Counts closing </p> tags, which the markdown renderer closes after every
    paragraph, including ones wrapped in <li> or <blockquote>. Inserting after
    a complete paragraph is safer than splitting mid-paragraph.
    """
    parts = html.split("</p>")
    if len(parts) <= nth_paragraph:
        # Not enough paragraphs to place it inside; append instead of dropping.
        return html + unit_markup
    # Rejoin the first N paragraphs, insert the unit, then the rest.
    before = "</p>".join(parts[:nth_paragraph]) + "</p>"
    rest = "</p>".join(parts[nth_paragraph:])
    return before + unit_markup + rest


def unit_matches_page(unit: AdUnit, path: str, is_homepage: bool, is_article: bool) -> bool:
    """Whether this unit should appear on the given request path."""
    if not unit.enabled:
        return False
    rule = unit.show_on
    if rule == "all":
        return True
    if rule == "homepage":
        return is_homepage
    if rule == "articles":
        return is_article
    # "selected": an explicit allowlist of page paths.
    return path in unit.paths


# -------------------------------------------------------------- rendering

# The responsive wrapper carries the min-height, so the AdSense iframe cannot
# push content down once it loads. Google's own guidance is to reserve space
# rather than let ads shift the layout.
_WRAPPER = '<div class="ad-slot ad-slot--{device}" data-placement="{placement}" style="min-height:{min_height}px">'


def _format_attrs(ad_format: str, layout_key: str) -> str:
    if ad_format == "display":
        return 'data-ad-format="display"'
    if ad_format in ("in-article", "in-feed"):
        layout = "in-article" if ad_format == "in-article" else "in-feed"
        return (
            f'data-ad-format="fluid" data-ad-layout="{layout}" '
            f'data-ad-layout-key="{escape(layout_key, quote=True)}"'
        )
    # "auto" and "responsive" both map to the responsive format, which is what
    # an unsized <ins> needs to fill its container.
    return 'data-ad-format="auto" data-full-width-responsive="true"'


def render_unit(unit: AdUnit, publisher_id: str) -> str:
    """The complete markup for one unit. Every interpolated value is either a
    slug from an enum or a value that passed validation."""
    min_height = {
        "header": 90,
        "sidebar": 250,
        "above-content": 250,
        "below-content": 250,
        "inside-content": 250,
        "footer": 90,
    }[unit.placement]

    device = unit.device if unit.device in DEVICES else "both"
    attrs = _format_attrs(unit.format, unit.layout_key)
    return (
        _WRAPPER.format(device=device, placement=unit.placement, min_height=min_height)
        + '<ins class="adsbygoogle" style="display:block" '
        + f'data-ad-client="{escape(publisher_id, quote=True)}" '
        + f'data-ad-slot="{escape(unit.slot_id, quote=True)}" {attrs}></ins>'
        + "</div>"
    )


def push_script(unit: AdUnit) -> str:
    """The AdSense activation call for one unit.

    Kept separate from render_unit so the template can emit one script per
    placement without interleaving it with the tag. The IntersectionObserver
    wrapper defers the push until the slot approaches the viewport, which is
    the practical form of lazy loading for AdSense.
    """
    return (
        "<script>"
        "(function(){"
        "var el=document.currentScript;"
        "var push=function(){(adsbygoogle=window.adsbygoogle||[]).push({});};"
        "if(el&&el.previousElementSibling&&'IntersectionObserver' in window){"
        "new IntersectionObserver(function(entries,obs){"
        "if(entries[0].isIntersecting){push();obs.disconnect();}"
        "},{rootMargin:'200px'}).observe(el.previousElementSibling);"
        "}else{push();}"
        "})();"
        "</script>"
    )


def script_src(publisher_id: str) -> str:
    return (
        "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"
        f"?client={escape(publisher_id, quote=True)}"
    )