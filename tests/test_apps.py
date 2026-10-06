"""Tests for admin-uploaded application binaries.

Uploads are the only place this site accepts a file it did not write, so these
tests lean hard on the validation rules: what is refused, what is stored where,
and what a download will and will not hand out.
"""

from __future__ import annotations

import hashlib
import io

import pytest

from app.services import apps


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    """Point the upload directory at a temporary path for every test."""
    monkeypatch.setattr(apps, "APPS_DIR", tmp_path / "uploads")
    return apps.APPS_DIR


def make_exe(payload: bytes = b"MZ" + b"\x00" * 200) -> bytes:
    """Bytes that look like a Windows executable."""
    return payload


def make_zip(payload: bytes = b"PK\x03\x04" + b"\x00" * 100) -> bytes:
    return payload


def make_msi(payload: bytes = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100) -> bytes:
    return payload


# ------------------------------------------------------------------- slugs


def test_clean_slug_accepts_lowercase_and_hyphens():
    assert apps.clean_slug("crystal-disk-info") == "crystal-disk-info"
    assert apps.clean_slug("  cpu-z4  ") == "cpu-z4"
    assert apps.clean_slug("hwinfo64") == "hwinfo64"


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "Has Caps", "double--hyphen", "trailing-", "under_score", "slash/name", "..", "a" * 61],
)
def test_clean_slug_rejects_unusable_values(bad):
    with pytest.raises(apps.AppUploadError):
        apps.clean_slug(bad)


# -------------------------------------------------------------- extensions


def test_check_suffix_allows_the_three_types():
    assert apps.check_suffix("tool.exe") == ".exe"
    assert apps.check_suffix("tool.MSI") == ".msi"
    assert apps.check_suffix("tool.Zip") == ".zip"


@pytest.mark.parametrize(
    "bad",
    [
        "payload.bat",
        "payload.ps1",
        "payload.scr",
        "payload.js",
        "payload.html",
        "payload.vbs",
        "payload.sh",
        "payload",
        "payload.exe.txt",
    ],
)
def test_check_suffix_refuses_everything_else(bad):
    with pytest.raises(apps.AppUploadError):
        apps.check_suffix(bad)


def test_check_suffix_strips_a_client_supplied_path():
    """A browser should never send a path, but if one arrives it must not be
    treated as a directory."""
    assert apps.check_suffix("C:\\Users\\me\\Downloads\\tool.exe") == ".exe"
    assert apps.check_suffix("../../etc/tool.exe") == ".exe"


# ------------------------------------------------------------ magic bytes


def test_check_magic_accepts_matching_content():
    apps.check_magic(make_exe()[:8], ".exe")
    apps.check_magic(make_zip()[:8], ".zip")
    apps.check_magic(make_msi()[:8], ".msi")


def test_check_magic_refuses_a_renamed_script():
    """The whole point: a text file named .exe must not be stored."""
    with pytest.raises(apps.AppUploadError) as exc:
        apps.check_magic(b"@echo off\r\nrem hello", ".exe")
    assert "not a Windows executable" in str(exc.value)


def test_check_magic_refuses_an_exe_named_as_zip():
    with pytest.raises(apps.AppUploadError):
        apps.check_magic(make_exe()[:8], ".zip")


# ---------------------------------------------------------------- storage


def test_store_upload_writes_the_file_and_records_a_hash(storage):
    payload = make_exe(b"MZ" + b"real content" * 50)
    result = apps.store_upload("test-tool", "anything.exe", [payload])

    assert result.filename == "test-tool.exe"
    assert result.size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.path.is_file()
    assert result.path.read_bytes() == payload
    assert result.path.parent == storage


def test_stored_filename_comes_from_the_slug_not_the_client(storage):
    """Even a hostile client filename cannot influence the stored path."""
    result = apps.store_upload("safe-slug", "../../evil name.exe", [make_exe()])
    assert result.filename == "safe-slug.exe"
    assert result.path.parent == storage


def _stored_files() -> list[str]:
    """Names of files in the upload directory, if it has been created yet."""
    if not apps.APPS_DIR.exists():
        return []
    return sorted(path.name for path in apps.APPS_DIR.iterdir())


def test_store_upload_rejects_a_renamed_script():
    with pytest.raises(apps.AppUploadError):
        apps.store_upload("bad", "innocent.exe", [b"@echo off\r\n"])
    assert _stored_files() == []


def test_store_upload_rejects_an_empty_file():
    with pytest.raises(apps.AppUploadError):
        apps.store_upload("empty", "empty.exe", [])
    assert _stored_files() == []


def test_store_upload_rejects_an_oversized_file(monkeypatch):
    # The cap is lowered rather than allocating 50 MB, so the test verifies the
    # guard without the memory cost. The real limit is checked separately below.
    monkeypatch.setattr(apps, "MAX_APP_BYTES", 2048)
    oversized = make_exe(b"MZ" + b"\x00" * 4096)
    with pytest.raises(apps.AppUploadError):
        apps.store_upload("huge", "huge.exe", [oversized])
    assert _stored_files() == []


def test_size_cap_is_fifty_megabytes():
    assert apps.MAX_APP_BYTES == 50 * 1024 * 1024


def test_store_upload_accepts_a_file_just_under_the_cap(monkeypatch):
    monkeypatch.setattr(apps, "MAX_APP_BYTES", 2048)
    payload = make_exe(b"MZ" + b"\x00" * 2000)
    assert len(payload) < apps.MAX_APP_BYTES
    result = apps.store_upload("just-fits", "j.exe", [payload])
    assert result.size == len(payload)


def test_no_partial_file_is_left_behind():
    """A refused upload must not leave a partial file for a download to find."""
    with pytest.raises(apps.AppUploadError):
        apps.store_upload("nope", "nope.exe", [b"not an exe at all"])
    assert _stored_files() == []


def test_replacing_a_file_overwrites_it(storage):
    first = apps.store_upload("tool", "a.exe", [make_exe(b"MZ" + b"one")])
    second = apps.store_upload("tool", "a.exe", [make_exe(b"MZ" + b"two")])

    assert first.path == second.path
    assert second.path.read_bytes() == make_exe(b"MZ" + b"two")


def test_remove_stored_deletes_the_file(storage):
    result = apps.store_upload("gone", "gone.exe", [make_exe()])
    apps.remove_stored(result.filename)
    assert not result.path.exists()


@pytest.mark.parametrize("hostile", ["../escape", "..\\escape", "/etc/passwd", "sub/dir.exe", "..", "."])
def test_remove_stored_refuses_paths(storage, hostile):
    """A filename with any separator must be ignored rather than resolved.

    A real file is placed first, so this proves the hostile value neither
    deletes it nor escapes the directory.
    """
    keeper = apps.store_upload("keeper", "keeper.exe", [make_exe()])
    apps.remove_stored(hostile)
    assert keeper.path.is_file(), "the stored file must survive"


# ------------------------------------------------------- path resolution


def test_stored_path_returns_the_file(storage):
    result = apps.store_upload("findable", "f.exe", [make_exe()])
    assert apps.stored_path(result.filename) == result.path


def test_stored_path_refuses_traversal(storage):
    """Every separator form is refused outright, so no crafted filename can
    resolve outside the upload directory."""
    apps.store_upload("present", "p.exe", [make_exe()])

    for hostile in [
        "../escape.exe",
        "../../escape.exe",
        "..\\escape.exe",
        "/etc/passwd",
        "sub/x.exe",
        "..",
        "",
    ]:
        assert apps.stored_path(hostile) is None, hostile


def test_stored_path_returns_none_for_a_missing_file(storage):
    apps.store_upload("present", "p.exe", [make_exe()])
    assert apps.stored_path("never-uploaded.exe") is None


# ----------------------------------------------------------------- hashes


def test_hash_file_matches_the_payload(storage):
    payload = make_exe(b"MZ" + b"hashable")
    result = apps.store_upload("hashme", "h.exe", [payload])
    assert apps.hash_file(result.path) == result.sha256


def test_hash_file_returns_none_when_missing(storage):
    assert apps.hash_file(storage / "absent.exe") is None


def test_hash_file_detects_a_changed_file(storage):
    """This is what stops a tampered upload being served quietly."""
    result = apps.store_upload("swap", "s.exe", [make_exe(b"MZ" + b"original")])
    assert apps.hash_file(result.path) == result.sha256

    result.path.write_bytes(make_exe(b"MZ" + b"tampered with"))
    assert apps.hash_file(result.path) != result.sha256


# ------------------------------------------------------------- formatting


@pytest.mark.parametrize(
    "size,expected",
    [(0, "unknown"), (512, "512 B"), (2048, "2 KB"), (5 * 1024 * 1024, "5.0 MB")],
)
def test_format_size(size, expected):
    assert apps.format_size(size) == expected


def test_shorten_hash():
    assert apps.shorten_hash("a" * 64) == "a" * 16
    assert apps.shorten_hash("") == ""


def test_allowed_suffixes_are_only_binaries():
    """Guard against someone widening the allowlist to include script types."""
    assert set(apps.ALLOWED_SUFFIXES) == {".exe", ".msi", ".zip"}
    for dangerous in (".bat", ".ps1", ".cmd", ".scr", ".js", ".vbs", ".hta", ".jar"):
        assert dangerous not in apps.ALLOWED_SUFFIXES