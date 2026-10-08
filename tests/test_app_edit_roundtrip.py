"""Regression test for editing an uploaded app without re-uploading the file.

Editing an app is the single most common admin action on a published download,
and the form posts every field on every save. If a save path rebuilds the record
from the form alone, the fields the form does not carry - the stored filename,
its size and its checksum - are silently reset, which turns a working download
into a 404 or an integrity failure.
"""

import re

import pytest

from tests.conftest import fake_exe, fake_png, make_csrf

FAKE_BINARY = fake_exe()
FAKE_SHOT = fake_png()

FIELDS = {
    "title": "DiskInfo",
    "summary": "Reads SMART data.",
    "purpose": "Use it when a drive reports errors.",
    "version": "1.4",
    "vendor": "Contoso",
    "vendor_url": "https://example.com/diskinfo",
    "category": "hardware",
    "warnings_text": "Do not run on a failing disk.",
}


def _upload(client, csrf, slug="diskinfo", **overrides):
    data = {**FIELDS, "slug": slug, "csrf": csrf, "is_published": "1"}
    data.update(overrides)
    return client.post(
        "/admin/apps/save",
        data=data,
        files={
            "binary": (f"{slug}.exe", FAKE_BINARY, "application/octet-stream"),
            "screenshot": (f"{slug}.png", FAKE_SHOT, "image/png"),
        },
        follow_redirects=False,
    )


@pytest.mark.usefixtures("admin_client")
def test_editing_an_app_keeps_the_stored_file_and_checksum(admin_client):
    csrf = make_csrf(admin_client)

    created = _upload(admin_client, csrf)
    assert created.status_code == 303, created.text

    listing = admin_client.get("/admin/apps")
    assert listing.status_code == 200
    row = re.search(r'<td class="px-4 py-3 font-mono text-xs[^"]*">([^<]+)</td>', listing.text)
    assert row is not None, "the listing did not show the stored filename"
    original_name = row.group(1).strip()
    assert original_name, "the stored filename was empty after upload"

    digest_before = _sha_on_disk(admin_client, original_name)

    # Edit one descriptive field only. No file is attached, so the save must
    # leave the existing file, its size and its checksum alone.
    saved = admin_client.post(
        "/admin/apps/save",
        data={**FIELDS, "slug": "diskinfo", "version": "1.5", "csrf": csrf, "is_published": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303, saved.text

    listing = admin_client.get("/admin/apps")
    row = re.search(r'<td class="px-4 py-3 font-mono text-xs[^"]*">([^<]+)</td>', listing.text)
    assert row is not None
    assert row.group(1).strip() == original_name, (
        "the stored filename changed on an edit that uploaded no file"
    )
    assert "1.5" in listing.text, "the edited version was not saved"

    after = _sha_on_disk(admin_client, original_name)
    assert after is not None, "the stored file vanished after the edit"
    assert after == digest_before, "the stored file's contents changed on a metadata-only edit"


def test_the_recorded_checksum_matches_the_file_after_an_edit(admin_client):
    """The checksum in the listing must still match the file on disk.

    A download whose stored checksum no longer matches is refused by
    integrity_ok, so a mismatched checksum is a broken download rather than a
    cosmetic inconsistency.
    """
    csrf = make_csrf(admin_client)
    assert _upload(admin_client, csrf).status_code == 303

    saved = admin_client.post(
        "/admin/apps/save",
        data={**FIELDS, "slug": "diskinfo", "summary": "Rewritten summary.", "csrf": csrf},
        follow_redirects=False,
    )
    assert saved.status_code == 303

    listing = admin_client.get("/admin/apps")
    assert listing.status_code == 200
    # The listing shows a truncated hash with an ellipsis and the full value in
    # the title attribute, so the recorded prefix is still readable.
    shown = re.search(r'title="([0-9a-f]{64})"', listing.text)
    assert shown is not None, "the listing did not show a recorded checksum"

    from app.services.apps import hash_file, stored_path

    recorded = shown.group(1)
    # The stored name is built from the slug, so it is derivable here.
    path = stored_path("diskinfo.exe")
    assert path is not None, "the stored file was missing after the edit"
    assert hash_file(path) == recorded, (
        "the checksum recorded in the listing no longer matches the file on disk, "
        "so the download would be refused"
    )


def _form_value(edit_page: str, field: str) -> str:
    """The value the edit form would submit for one input, or '' if absent."""
    match = re.search(rf'name="{field}"[^>]*value="([^"]*)"', edit_page)
    return match.group(1) if match else ""


def _form_textarea(edit_page: str, field: str) -> str:
    match = re.search(rf'name="{field}"[^>]*>(.*?)</textarea>', edit_page, re.S)
    return match.group(1).strip() if match else ""


@pytest.mark.usefixtures("admin_client")
def test_the_edit_form_prefills_every_field_it_can_save(admin_client):
    """Loading the edit form and submitting it unchanged must change nothing.

    The form context is built from AppDownload.to_dict(), which omitted purpose,
    vendor_url and category. The template renders those from the dict, so the
    form came back with them empty even though the database held real values.
    An admin who opened a record to fix a typo in the title and hit Save would
    have silently wiped the tool's description and vendor link, and the next
    visitor would see a download page with nothing explaining what it is for.
    """
    csrf = make_csrf(admin_client)
    assert _upload(admin_client, csrf).status_code == 303

    edit = admin_client.get("/admin/apps/diskinfo/edit")
    assert edit.status_code == 200
    page = edit.text

    assert _form_value(page, "purpose") == "", "purpose is a textarea, not an input"
    assert _form_textarea(page, "purpose") == FIELDS["purpose"], (
        "the edit form did not prefill purpose, so re-saving would erase it"
    )
    assert _form_textarea(page, "summary") == FIELDS["summary"]
    assert _form_textarea(page, "warnings_text") == FIELDS["warnings_text"]
    assert _form_value(page, "vendor_url") == FIELDS["vendor_url"], (
        "the edit form did not prefill vendor_url, so re-saving would erase it"
    )
    assert _form_value(page, "title") == FIELDS["title"]
    assert _form_value(page, "version") == FIELDS["version"]
    assert _form_value(page, "vendor") == FIELDS["vendor"]
    assert f'value="{FIELDS["category"]}" selected' in page.replace("\n", " ").replace(
        "  ", " "
    ) or re.search(
        rf'<option value="{re.escape(FIELDS["category"])}"\s+selected', page
    ), "the category select did not mark the stored category as selected"


@pytest.mark.usefixtures("admin_client")
def test_resubmitting_the_edit_form_unchanged_preserves_every_field(admin_client):
    """The end-to-end version: a no-op edit must not lose anything."""
    csrf = make_csrf(admin_client)
    assert _upload(admin_client, csrf).status_code == 303

    before = _form_fields(admin_client, "diskinfo")

    saved = admin_client.post(
        "/admin/apps/save",
        data={**before, "slug": "diskinfo", "csrf": csrf, "is_published": "1"},
        follow_redirects=False,
    )
    assert saved.status_code == 303, saved.text

    after = _form_fields(admin_client, "diskinfo")
    assert after == before, "re-saving the edit form unchanged altered the record"


def _form_fields(client, slug: str) -> dict:
    """Every editable field, read back out of the edit form as a browser would."""
    page = client.get(f"/admin/apps/{slug}/edit").text
    return {
        "title": _form_value(page, "title"),
        "version": _form_value(page, "version"),
        "vendor": _form_value(page, "vendor"),
        "vendor_url": _form_value(page, "vendor_url"),
        "summary": _form_textarea(page, "summary"),
        "purpose": _form_textarea(page, "purpose"),
        "warnings_text": _form_textarea(page, "warnings_text"),
        "category": _selected_option(page, "category"),
    }


def _selected_option(page: str, select_name: str) -> str:
    block = re.search(
        rf'<select[^>]*name="{select_name}"[^>]*>(.*?)</select>', page, re.S
    )
    if block is None:
        return ""
    chosen = re.search(r'<option value="([^"]*)"[^>]*selected', block.group(1))
    return chosen.group(1) if chosen else ""


def _sha_on_disk(client, stored_name):
    """Hash a file in the upload directory the app was configured to use."""
    from app.services.apps import hash_file, stored_path

    # stored_path resolves by name and refuses anything outside the directory.
    path = stored_path(stored_name)
    if path is None:
        return None
    return hash_file(path)


