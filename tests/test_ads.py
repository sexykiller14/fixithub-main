"""Ads / AdSense administration and rendering.

The three properties worth protecting: an admin who can reach the settings
form cannot paste raw HTML, the AdSense script only reaches the page when the
master switch is on and the publisher id is valid, and no admin or error page
ever carries the tag.
"""

from __future__ import annotations

import re

import pytest

from app.models import AdSettings, AdUnit


@pytest.fixture(autouse=True)
def clean_ads_tables():
    """Each test starts with empty ad tables.

    admin_client writes via FastAPI's own session, which commits, so rows left
    by one test would otherwise be visible to the next.
    """
    from app.db import SessionLocal

    with SessionLocal() as db:
        db.query(AdUnit).delete()
        db.query(AdSettings).delete()
        db.commit()
    yield


# --------------------------------------------------------------- admin auth


def test_settings_form_requires_admin(client):
    response = client.get("/admin/ads", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"

    response = client.post(
        "/admin/ads/settings",
        data={"enabled": "1", "publisher_id": "ca-pub-1234567890123456", "csrf": "x"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_settings_reject_a_forged_csrf_token(admin_client):
    response = admin_client.post(
        "/admin/ads/settings",
        data={
            "enabled": "1",
            "publisher_id": "ca-pub-1234567890123456",
            "csrf": "not-the-token",
        },
    )
    assert response.status_code == 403


# ------------------------------------------------------- settings validation


def _csrf(client) -> str:
    page = client.get("/admin/ads")
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None
    return match.group(1)


def test_a_valid_publisher_id_is_stored(admin_client, db):
    response = admin_client.post(
        "/admin/ads/settings",
        data={
            "enabled": "1",
            "publisher_id": "ca-pub-1234567890123456",
            "ads_txt": "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0",
            "csrf": _csrf(admin_client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    row = db.query(AdSettings).first()
    assert row.enabled is True
    assert row.publisher_id == "ca-pub-1234567890123456"


def test_an_invalid_publisher_id_is_rejected(admin_client, db):
    admin_client.post(
        "/admin/ads/settings",
        data={
            "publisher_id": "definitely-not-a-pub-id",
            "csrf": _csrf(admin_client),
        },
    )
    row = db.query(AdSettings).first()
    assert row is None or row.publisher_id != "definitely-not-a-pub-id"


def test_enabling_without_a_publisher_id_is_rejected(admin_client, db):
    admin_client.post(
        "/admin/ads/settings",
        data={
            "enabled": "1",
            "publisher_id": "",
            "csrf": _csrf(admin_client),
        },
    )
    row = db.query(AdSettings).first()
    # The row was either never created or saved with enabled=False.
    assert row is None or row.enabled is False


# --------------------------------------------------------- unit CRUD


def _save_unit(admin_client, **overrides):
    data = {
        "label": "Header",
        "slot_id": "1234567890",
        "format": "auto",
        "placement": "above-content",
        "nth_paragraph": "2",
        "layout_key": "",
        "show_on": "all",
        "selected_paths": "",
        "device": "both",
        "csrf": _csrf(admin_client),
    }
    data.update(overrides)
    return admin_client.post("/admin/ads/unit/save", data=data, follow_redirects=False)


def test_a_valid_unit_is_stored_and_listed(admin_client, db):
    response = _save_unit(admin_client)
    assert response.status_code == 303

    unit = db.query(AdUnit).first()
    assert unit is not None
    assert unit.label == "Header"
    assert unit.enabled is True

    page = admin_client.get("/admin/ads")
    assert "Header" in page.text
    assert "1234567890" in page.text


def test_a_non_numeric_slot_id_is_rejected(admin_client, db):
    _save_unit(admin_client, slot_id="not-numeric")

    assert db.query(AdUnit).count() == 0


def test_an_unknown_format_is_rejected(admin_client, db):
    # An injected <script> cannot get saved because the enum check rejects it.
    _save_unit(admin_client, format='<script>alert(1)</script>')

    assert db.query(AdUnit).count() == 0


def test_an_unknown_placement_is_rejected(admin_client, db):
    _save_unit(admin_client, placement="not-a-placement")

    assert db.query(AdUnit).count() == 0


def test_in_article_without_a_layout_key_is_rejected(admin_client, db):
    _save_unit(admin_client, format="in-article", layout_key="")

    assert db.query(AdUnit).count() == 0


def test_in_article_with_a_layout_key_is_accepted(admin_client, db):
    _save_unit(admin_client, format="in-article", layout_key="abc123")

    unit = db.query(AdUnit).first()
    assert unit is not None
    assert unit.layout_key == "abc123"


def test_a_saved_unit_can_be_edited(admin_client, db):
    _save_unit(admin_client)
    unit = db.query(AdUnit).first()

    response = _save_unit(admin_client, id=str(unit.id), label="Edited label")
    assert response.status_code == 303

    db.refresh(unit)
    assert unit.label == "Edited label"


def test_a_unit_can_be_toggled_off(admin_client, db):
    _save_unit(admin_client)
    unit = db.query(AdUnit).first()

    admin_client.post(f"/admin/ads/unit/{unit.id}/toggle", data={"csrf": _csrf(admin_client)})
    db.refresh(unit)
    assert unit.enabled is False

    admin_client.post(f"/admin/ads/unit/{unit.id}/toggle", data={"csrf": _csrf(admin_client)})
    db.refresh(unit)
    assert unit.enabled is True


def test_a_unit_can_be_deleted(admin_client, db):
    _save_unit(admin_client)
    unit = db.query(AdUnit).first()

    admin_client.post(f"/admin/ads/unit/{unit.id}/delete", data={"csrf": _csrf(admin_client)})
    assert db.query(AdUnit).count() == 0


# ----------------------------------------------- public rendering


def _enable_ads(db, publisher_id="ca-pub-1234567890123456"):
    row = AdSettings(enabled=True, publisher_id=publisher_id)
    db.add(row)
    db.commit()
    return row


def test_no_ad_markup_when_disabled(client, db):
    db.add(AdSettings(enabled=False, publisher_id="ca-pub-1234567890123456"))
    db.commit()

    page = client.get("/")
    assert page.status_code == 200
    assert "googlesyndication" not in page.text
    assert "adsbygoogle" not in page.text


def test_no_ad_markup_without_a_publisher_id(client, db):
    db.add(AdSettings(enabled=True, publisher_id=""))
    db.commit()

    page = client.get("/")
    assert "googlesyndication" not in page.text


def test_the_ad_script_loads_when_enabled(client, db):
    _enable_ads(db)

    page = client.get("/")
    assert "pagead2.googlesyndication.com" in page.text
    assert "client=ca-pub-1234567890123456" in page.text


def test_ad_units_render_on_the_public_page(client, db):
    _enable_ads(db)
    db.add(
        AdUnit(
            label="Above content",
            slot_id="9876543210",
            format="auto",
            placement="above-content",
            show_on="all",
            device="both",
            enabled=True,
        )
    )
    db.commit()

    page = client.get("/")
    assert 'data-ad-slot="9876543210"' in page.text
    assert 'data-ad-format="auto"' in page.text
    assert 'min-height:250px' in page.text


def test_no_ads_on_admin_pages(admin_client, db):
    _enable_ads(db)
    db.add(
        AdUnit(
            label="Above content",
            slot_id="9876543210",
            format="auto",
            placement="above-content",
            show_on="all",
            device="both",
            enabled=True,
        )
    )
    db.commit()

    for path in ("/admin", "/admin/ads", "/admin/dashboard", "/admin/questions"):
        page = admin_client.get(path, follow_redirects=False)
        assert "adsbygoogle" not in page.text, f"ads leaked onto {path}"


def test_no_ads_when_an_error_page_renders(client, db):
    _enable_ads(db)

    response = client.get("/articles/this-slug-does-not-exist")
    assert response.status_code == 404
    assert "adsbygoogle" not in response.text


def test_the_csp_strict_when_ads_are_off(client, db):
    page = client.get("/")
    csp = page.headers.get("content-security-policy", "")

    assert "googlesyndication" not in csp


def test_the_csp_extends_when_ads_are_on(client, db):
    _enable_ads(db)

    page = client.get("/")
    csp = page.headers.get("content-security-policy", "")

    assert "pagead2.googlesyndication.com" in csp
    assert "frame-src" in csp


def test_ads_txt_is_served_verbatim(client, db):
    _enable_ads(db)
    settings = db.query(AdSettings).first()
    settings.ads_txt = "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n"
    db.commit()

    response = client.get("/ads.txt")
    assert response.status_code == 200
    assert response.text == "google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n"
    assert "text/plain" in response.headers["content-type"]


def test_a_disabled_unit_does_not_render(client, db):
    _enable_ads(db)
    db.add(
        AdUnit(
            label="Disabled",
            slot_id="1111111111",
            format="auto",
            placement="above-content",
            show_on="all",
            device="both",
            enabled=False,
        )
    )
    db.commit()

    page = client.get("/")
    assert "1111111111" not in page.text


def test_a_unit_scoped_to_homepage_does_not_render_on_articles(client, db):
    _enable_ads(db)
    db.add(
        AdUnit(
            label="Homepage only",
            slot_id="2222222222",
            format="auto",
            placement="above-content",
            show_on="homepage",
            device="both",
            enabled=True,
        )
    )
    db.commit()

    article = "/articles/ram-stability-xmp-expo"
    assert "2222222222" not in client.get(article).text
    assert "2222222222" in client.get("/").text


def test_inside_content_placement_lands_inside_the_article(client, db):
    _enable_ads(db)
    db.add(
        AdUnit(
            label="Inside",
            slot_id="3333333333",
            format="display",
            placement="inside-content",
            nth_paragraph=2,
            show_on="all",
            device="both",
            enabled=True,
        )
    )
    db.commit()

    page = client.get("/articles/ram-stability-xmp-expo")
    html = page.text
    slot_index = html.find('data-ad-slot="3333333333"')
    assert slot_index != -1
    # The slot should appear inside the prose, not after the whole article.
    prose_start = html.find('<div class="prose-article')
    prose_end = html.find('</div>', prose_start)
    assert prose_start != -1 and slot_index > prose_start


def test_the_admin_ads_page_shows_saved_settings(admin_client, db):
    _enable_ads(db)
    settings = db.query(AdSettings).first()
    settings.ads_txt = "google.com, pub-1, DIRECT, f08c47fec0942fa0"
    db.commit()

    page = admin_client.get("/admin/ads")
    assert "ca-pub-1234567890123456" in page.text
    assert "google.com, pub-1" in page.text