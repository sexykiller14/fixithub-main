"""HTTP-level tests for the admin upload flow and public download routes."""

from __future__ import annotations

import io

import pytest

from app.config import APPS_DIR, USER_SESSION_COOKIE
from app.db import SessionLocal
from app.models import AppDownload
from app.services.apps import hash_file, remove_stored, remove_stored_image
from tests.conftest import fake_exe, fake_jpeg, fake_png, fake_webp, make_csrf


def _clear_rows():
    """Remove test rows, their files and any reader, so ordering cannot matter."""
    from app.models import AuthToken, Comment, User

    session = SessionLocal()
    try:
        for row in session.query(AppDownload).all():
            remove_stored(row.filename)
            remove_stored_image(row.screenshot_filename or "")
            session.delete(row)
        for user in session.query(User).all():
            session.query(AuthToken).filter(AuthToken.user_id == user.id).delete()
            session.query(Comment).filter(Comment.user_id == user.id).delete()
            session.delete(user)
        session.commit()
    finally:
        session.close()


@pytest.fixture
def clean_apps():
    _clear_rows()
    yield
    _clear_rows()


def sign_in_verified(client) -> None:
    """Sign in as a confirmed reader, which is what a download now requires."""
    from app.models import User
    from app.services import accounts

    session = SessionLocal()
    try:
        user, token = accounts.create_user(session, "downloader@example.com", "a-long-good-phrase")
        accounts.verify_email(session, token.raw)
        raw = accounts.start_session(session, user).raw
    finally:
        session.close()

    client.cookies.set(USER_SESSION_COOKIE, raw)


def upload_and_sign_in(client, **overrides):
    """Upload, publish, and sign in so the download route is reachable."""
    response = upload(client, **overrides)
    assert response.status_code == 303, response.text[:400]
    sign_in_verified(client)
    return response


def upload(client, **overrides):
    """POST an upload form. A binary is supplied unless the test omits it.

    A screenshot can be attached by passing ``screenshot=`` with bytes and
    ``screenshot_filename=`` with a name. The field is multipart-optional, so
    omitting both must behave exactly as before.
    """
    payload = overrides.pop("payload", fake_exe())
    filename = overrides.pop("filename", "setup.exe")
    shot = overrides.pop("screenshot", None)
    shot_name = overrides.pop("screenshot_filename", "shot.png")
    data = {
        "slug": "test-tool",
        "title": "Test Tool",
        "summary": "A test binary used by the automated suite.",
        "purpose": "## When to use it\n\nOnly in tests.",
        "version": "1.0",
        "vendor": "Test Vendor",
        "vendor_url": "https://example.com/tool",
        "category": "hardware",
        "warnings_text": "Only for testing.",
        "csrf": make_csrf(client),
    }
    data.update(overrides)
    files = {"binary": (filename, io.BytesIO(payload), "application/octet-stream")}
    if shot is not None:
        files["screenshot"] = (shot_name, io.BytesIO(shot), "application/octet-stream")
    return client.post(
        "/admin/apps/save",
        data=data,
        files=files,
        follow_redirects=False,
    )


# ------------------------------------------------------------- admin pages


def test_admin_apps_page_requires_login(client):
    response = client.get("/admin/apps", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_admin_apps_list_and_form_render(admin_client, clean_apps):
    listing = admin_client.get("/admin/apps")
    assert listing.status_code == 200
    assert "Upload a tool" in listing.text
    # The page must tell the admin uploads are not virus scanned. The <strong>
    # tag splits this phrase in the markup, so match the parts around it.
    assert "not</strong> scanned by antivirus" in listing.text

    form = admin_client.get("/admin/apps/new")
    assert form.status_code == 200
    assert 'name="binary"' in form.text
    assert 'enctype="multipart/form-data"' in form.text


def test_upload_requires_a_csrf_token(client, clean_apps):
    """Without a valid token nothing should be written."""
    response = client.post(
        "/admin/apps/save",
        data={"slug": "no-csrf", "title": "X", "summary": "Y"},
        files={"binary": ("x.exe", io.BytesIO(fake_exe()), "application/octet-stream")},
        follow_redirects=False,
    )
    assert response.status_code in (303, 403)
    if response.status_code == 303:
        assert response.headers["location"] == "/admin"

    session = SessionLocal()
    try:
        assert session.query(AppDownload).count() == 0
    finally:
        session.close()


def test_upload_requires_auth(client, clean_apps):
    response = client.post(
        "/admin/apps/save",
        data={"slug": "unauth", "title": "X", "summary": "Y"},
        files={"binary": ("x.exe", io.BytesIO(fake_exe()), "application/octet-stream")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"

    session = SessionLocal()
    try:
        assert session.query(AppDownload).count() == 0
    finally:
        session.close()


# ------------------------------------------------------------------ upload


def test_successful_upload_stores_file_and_row(admin_client, clean_apps):
    response = upload(admin_client, is_published="on")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/apps?saved=test-tool"

    stored = APPS_DIR / "test-tool.exe"
    assert stored.is_file()

    session = SessionLocal()
    try:
        row = session.query(AppDownload).filter_by(slug="test-tool").one()
        assert row.filename == "test-tool.exe"
        assert row.is_published is True
        assert row.size_bytes == len(fake_exe())
        assert row.sha256 == hash_file(stored)
        assert row.warnings == ["Only for testing."]
    finally:
        session.close()


def test_new_upload_defaults_to_draft(admin_client, clean_apps):
    """An unpublished upload must not be reachable from the public site."""
    upload(admin_client)
    session = SessionLocal()
    try:
        assert session.query(AppDownload).one().is_published is False
    finally:
        session.close()

    sign_in_verified(admin_client)
    assert admin_client.get("/apps/test-tool", follow_redirects=False).status_code == 404
    assert admin_client.get("/apps/test-tool/download").status_code == 404


def test_upload_refuses_a_renamed_script(admin_client, clean_apps):
    """The core check: a text file claiming to be an executable is rejected."""
    response = upload(admin_client, payload=b"@echo off\r\nrem not an exe\r\n")
    assert response.status_code == 400
    assert "not a Windows executable" in response.text
    assert not (APPS_DIR / "test-tool.exe").exists()

    session = SessionLocal()
    try:
        assert session.query(AppDownload).count() == 0
    finally:
        session.close()


@pytest.mark.parametrize("filename", ["bad.bat", "bad.ps1", "bad.scr", "bad.html", "bad.vbs"])
def test_upload_refuses_script_extensions(admin_client, clean_apps, filename):
    response = upload(admin_client, filename=filename)
    assert response.status_code == 400
    assert "not accepted" in response.text


def test_upload_refuses_a_traversing_client_filename(admin_client, clean_apps):
    """The stored name comes from the slug, so this cannot escape the folder."""
    upload(admin_client, filename="../../../windows/system32/evil.exe", is_published="on")
    stored = sorted(p.name for p in APPS_DIR.iterdir() if p.is_file())
    assert stored == ["test-tool.exe"]


def test_upload_refuses_a_bad_slug(admin_client, clean_apps):
    response = upload(admin_client, slug="Not A Slug")
    assert response.status_code == 400
    assert "lowercase letters" in response.text


def test_upload_requires_a_file_for_a_new_record(admin_client, clean_apps):
    response = admin_client.post(
        "/admin/apps/save",
        data={
            "slug": "no-file",
            "title": "No file",
            "summary": "There is no binary attached.",
            "category": "hardware",
            "csrf": make_csrf(admin_client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "Choose a file" in response.text


def test_upload_requires_title_and_summary(admin_client, clean_apps):
    response = upload(admin_client, title="", summary="")
    assert response.status_code == 400
    assert "A title is required" in response.text
    assert "summary is required" in response.text


def test_edit_metadata_without_replacing_the_file(admin_client, clean_apps):
    upload(admin_client, is_published="on")
    stored = APPS_DIR / "test-tool.exe"
    before = stored.read_bytes()

    response = admin_client.post(
        "/admin/apps/save",
        data={
            "slug": "test-tool",
            "title": "Renamed Tool",
            "summary": "The summary was updated.",
            "category": "windows",
            "csrf": make_csrf(admin_client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert stored.read_bytes() == before, "the file must be untouched"

    session = SessionLocal()
    try:
        row = session.query(AppDownload).one()
        assert row.title == "Renamed Tool"
        assert row.category == "windows"
    finally:
        session.close()


def test_replacing_the_file_updates_the_checksum(admin_client, clean_apps):
    upload(admin_client, is_published="on")
    session = SessionLocal()
    try:
        first_hash = session.query(AppDownload).one().sha256
    finally:
        session.close()

    replacement = fake_exe(b"MZ")
    replacement = b"MZ" + b"a different binary entirely" + b"\x00" * 200
    response = upload(admin_client, payload=replacement, is_published="on")
    assert response.status_code == 303

    session = SessionLocal()
    try:
        row = session.query(AppDownload).one()
        assert row.sha256 != first_hash
        assert row.integrity_ok() is True
    finally:
        session.close()


def test_replacing_with_a_different_extension_removes_the_old_file(admin_client, clean_apps):
    upload(admin_client, is_published="on")
    assert (APPS_DIR / "test-tool.exe").exists()

    payload = b"PK\x03\x04" + b"\x00" * 300
    response = upload(admin_client, payload=payload, filename="renamed.zip", is_published="on")
    assert response.status_code == 303

    assert not (APPS_DIR / "test-tool.exe").exists(), "the old file should be gone"
    assert (APPS_DIR / "test-tool.zip").exists()


def test_delete_removes_the_row_and_the_file(admin_client, clean_apps):
    upload(admin_client, is_published="on")
    assert (APPS_DIR / "test-tool.exe").exists()

    response = admin_client.post(
        "/admin/apps/test-tool/delete",
        data={"csrf": make_csrf(admin_client)},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert not (APPS_DIR / "test-tool.exe").exists()

    session = SessionLocal()
    try:
        assert session.query(AppDownload).count() == 0
    finally:
        session.close()


# ------------------------------------------------------------- screenshots


def test_screenshot_is_optional_and_defaults_to_none(admin_client, clean_apps):
    """An upload with no image still succeeds, which is how every upload
    behaved before this field existed."""
    response = upload(admin_client, is_published="on")
    assert response.status_code == 303, response.text[:400]

    session = SessionLocal()
    try:
        row = session.query(AppDownload).one()
        assert row.screenshot_filename == ""
        assert row.has_screenshot is False
    finally:
        session.close()

    # The index shows a placeholder rather than a broken image.
    index = admin_client.get("/apps")
    assert "No screenshot yet" in index.text


def test_upload_stores_the_screenshot(admin_client, clean_apps):
    response = upload(
        admin_client, is_published="on", screenshot=fake_png(), screenshot_filename="window.png"
    )
    assert response.status_code == 303, response.text[:400]

    session = SessionLocal()
    try:
        row = session.query(AppDownload).one()
        assert row.screenshot_filename == "test-tool-shot.png"
        assert row.has_screenshot is True
    finally:
        session.close()

    # The name is derived from the slug, never from what the browser sent.
    assert (APPS_DIR / "screenshots" / "test-tool-shot.png").exists()


def test_screenshot_is_served_with_a_declared_image_type(admin_client, clean_apps):
    upload(admin_client, is_published="on", screenshot=fake_png())

    response = admin_client.get("/apps/test-tool/screenshot")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    # A visitor's browser decodes these pixels, so the response must not let a
    # browser sniff its way to some other type or treat it as a document.
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
    assert response.content == fake_png()


@pytest.mark.parametrize(
    "payload,filename,expected_type",
    [
        (fake_png(), "shot.png", "image/png"),
        (fake_jpeg(), "shot.jpg", "image/jpeg"),
        (fake_jpeg(), "shot.jpeg", "image/jpeg"),
        (fake_webp(), "shot.webp", "image/webp"),
    ],
)
def test_each_allowed_image_format_is_accepted(
    admin_client, clean_apps, payload, filename, expected_type
):
    response = upload(admin_client, is_published="on", screenshot=payload, screenshot_filename=filename)
    assert response.status_code == 303, response.text[:400]

    served = admin_client.get("/apps/test-tool/screenshot")
    assert served.status_code == 200
    assert served.headers["content-type"] == expected_type


def test_svg_is_refused(admin_client, clean_apps):
    """SVG is markup a browser parses and can script, so it is not an image
    type this site accepts."""
    response = upload(
        admin_client,
        is_published="on",
        screenshot=b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
        screenshot_filename="shot.svg",
    )
    assert response.status_code == 400
    assert "svg" in response.text.lower()


def test_a_renamed_script_is_refused_as_a_screenshot(admin_client, clean_apps):
    """The extension says PNG but the bytes are a batch file."""
    response = upload(
        admin_client, is_published="on", screenshot=b"@echo off\r\n", screenshot_filename="shot.png"
    )
    assert response.status_code == 400
    assert "png" in response.text.lower()


def test_a_bad_image_extension_is_refused(admin_client, clean_apps):
    response = upload(
        admin_client, is_published="on", screenshot=fake_png(), screenshot_filename="shot.gif"
    )
    assert response.status_code == 400


def test_replacing_the_screenshot_removes_the_old_file(admin_client, clean_apps):
    upload(admin_client, is_published="on", screenshot=fake_png(), screenshot_filename="one.png")
    assert (APPS_DIR / "screenshots" / "test-tool-shot.png").exists()

    upload(admin_client, is_published="on", screenshot=fake_jpeg(), screenshot_filename="two.jpg")
    assert (APPS_DIR / "screenshots" / "test-tool-shot.jpg").exists()
    assert not (APPS_DIR / "screenshots" / "test-tool-shot.png").exists(), (
        "the replaced screenshot should be deleted, not left orphaned"
    )


def test_a_failed_screenshot_leaves_the_previous_one_alone(admin_client, clean_apps):
    """A rejected image must not also wipe the working screenshot, and must not
    commit the metadata changes that came with it."""
    upload(admin_client, is_published="on", screenshot=fake_png())

    response = upload(
        admin_client,
        is_published="on",
        title="Renamed By Mistake",
        screenshot=b"not an image at all",
        screenshot_filename="broken.png",
    )
    assert response.status_code == 400

    session = SessionLocal()
    try:
        row = session.query(AppDownload).one()
        assert row.title == "Test Tool", "a rejected image must not commit other edits"
        assert row.screenshot_filename == "test-tool-shot.png"
    finally:
        session.close()

    assert admin_client.get("/apps/test-tool/screenshot").status_code == 200


def test_unpublished_screenshot_is_not_served(admin_client, clean_apps):
    upload(admin_client, screenshot=fake_png())
    assert admin_client.get("/apps/test-tool/screenshot").status_code == 404


def test_screenshot_is_served_without_signing_in(client, admin_client, clean_apps):
    """Screenshots are informational, so they are not behind the download wall.
    Only the binary itself needs an account."""
    upload(admin_client, is_published="on", screenshot=fake_png())

    response = client.get("/apps/test-tool/screenshot")
    assert response.status_code == 200
    # The binary is still refused to the same anonymous visitor.
    assert client.get("/apps/test-tool/download", follow_redirects=False).status_code == 303


def test_missing_screenshot_for_an_unknown_slug_is_a_plain_404(client, clean_apps):
    response = client.get("/apps/never-existed/screenshot")
    assert response.status_code == 404
    # No detail leaks. The slug appears in the canonical URL that base.html
    # emits for every page, so assert on the error text itself rather than on
    # the string being absent from the whole document.
    assert "No published download" not in response.text
    assert "Download not found" not in response.text


def test_delete_removes_the_screenshot_too(admin_client, clean_apps):
    upload(admin_client, is_published="on", screenshot=fake_png())
    stored = APPS_DIR / "screenshots" / "test-tool-shot.png"
    assert stored.exists()

    admin_client.post(
        "/admin/apps/test-tool/delete",
        data={"csrf": make_csrf(admin_client)},
        follow_redirects=False,
    )
    assert not stored.exists(), "the screenshot should not be orphaned on disk"


def test_admin_form_offers_the_screenshot_field(admin_client, clean_apps):
    form = admin_client.get("/admin/apps/new")
    assert form.status_code == 200
    assert 'name="screenshot"' in form.text
    assert ".png" in form.text
    # The upload form has to stay multipart now that it takes two files.
    assert "multipart/form-data" in form.text


def test_index_is_a_grid_with_thumbnails(admin_client, clean_apps):
    upload(admin_client, is_published="on", screenshot=fake_png())

    index = admin_client.get("/apps")
    assert index.status_code == 200
    assert 'src="/apps/test-tool/screenshot"' in index.text
    assert "Test Tool" in index.text
    assert "sm:grid-cols-2" in index.text


# ----------------------------------------------------------- public pages


def test_public_index_and_detail_render(admin_client, clean_apps):
    upload(admin_client, is_published="on")

    index = admin_client.get("/apps")
    assert index.status_code == 200
    assert "Test Tool" in index.text
    # The listing has to warn about SmartScreen, because users will hit it.
    assert "SmartScreen" in index.text

    detail = admin_client.get("/apps/test-tool")
    assert detail.status_code == 200
    assert "SHA-256" in detail.text
    assert "Checksum verified" in detail.text
    assert "When to use it" in detail.text


def test_detail_page_disables_download_when_the_hash_does_not_match(admin_client, clean_apps):
    upload_and_sign_in(admin_client, is_published="on")
    stored = APPS_DIR / "test-tool.exe"
    stored.write_bytes(b"MZ" + b"tampered after upload")

    page = admin_client.get("/apps/test-tool")
    assert page.status_code == 200
    assert "Checksum mismatch" in page.text
    assert "/apps/test-tool/download" not in page.text

    download = admin_client.get("/apps/test-tool/download")
    assert download.status_code == 409


def test_detail_page_disables_download_when_the_file_is_missing(admin_client, clean_apps):
    upload_and_sign_in(admin_client, is_published="on")
    (APPS_DIR / "test-tool.exe").unlink()

    page = admin_client.get("/apps/test-tool")
    assert page.status_code == 200
    assert "missing or cannot be verified" in page.text

    assert admin_client.get("/apps/test-tool/download").status_code == 404


def test_unknown_slug_is_404(admin_client, clean_apps):
    assert admin_client.get("/apps/nope", follow_redirects=False).status_code == 404
    # Signed in, so this reaches the route rather than bouncing at the gate.
    sign_in_verified(admin_client)
    assert admin_client.get("/apps/nope/download").status_code == 404


# -------------------------------------------------------------- downloads


def test_download_is_an_attachment_with_nosniff(admin_client, clean_apps):
    upload_and_sign_in(admin_client, is_published="on")

    response = admin_client.get("/apps/test-tool/download")
    assert response.status_code == 200
    assert response.content == fake_exe()
    assert response.headers["content-disposition"] == 'attachment; filename="test-tool.exe"'
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"] == "application/octet-stream"
    assert "sandbox" in response.headers["content-security-policy"]


def test_download_increments_the_counter(admin_client, clean_apps):
    upload_and_sign_in(admin_client, is_published="on")
    admin_client.get("/apps/test-tool/download")
    admin_client.get("/apps/test-tool/download")

    session = SessionLocal()
    try:
        assert session.query(AppDownload).one().download_count == 2
    finally:
        session.close()


def test_purpose_markdown_is_sanitised(admin_client, clean_apps):
    """The purpose field renders markdown, so it must not allow script tags."""
    upload(
        admin_client,
        purpose='## Safe\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>',
        is_published="on",
    )
    page = admin_client.get("/apps/test-tool")
    assert page.status_code == 200
    assert "<script>alert(1)</script>" not in page.text
    assert "onerror=" not in page.text


# ------------------------------------------------------------------- seo


def test_sitemap_lists_published_only(admin_client, clean_apps):
    upload(admin_client, is_published="on")
    body = admin_client.get("/sitemap.xml").text
    assert "/apps/test-tool" in body
    assert "/apps" in body

    upload(admin_client, is_published="")
    body = admin_client.get("/sitemap.xml").text
    assert "/apps/test-tool" not in body


def test_dashboard_counts_uploads(admin_client, clean_apps):
    upload(admin_client, is_published="on")
    page = admin_client.get("/admin/dashboard")
    assert page.status_code == 200
    assert "/admin/apps" in page.text