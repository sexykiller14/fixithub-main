"""Uploadable application binaries.

This is the one part of the site that stores files it did not write. Scripts
are text in git; apps are programs an admin uploads, so every check that
normally comes for free has to be applied explicitly here.

The rules, and why each exists:

  Extension allowlist   Anything outside the list is refused outright. The
                        stored filename is built from the slug, never from the
                        client's filename, so an upload cannot escape the
                        directory or pick its own extension.
  Magic byte check      A file whose bytes disagree with its extension is
                        refused, which catches a renamed executable.
  Size cap              Enforced while streaming, so an oversized upload is
                        abandoned partway rather than buffered first.
  SHA-256 recorded      Shown on the public page so a visitor can verify what
                        they downloaded, and recomputed on download so silent
                        tampering on disk is reported rather than served.
  Attachment only       Downloads are sent as an attachment with a plain
                        content type, so a browser saves the file instead of
                    executing it in any context.

Nothing in this module executes, unpacks or inspects the contents of an
uploaded binary beyond its first two bytes.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import SITE_URL
from . import storage
from .storage import StorageError

# Only these may be uploaded. The list is deliberately short: this site has no
# legitimate need for .scr, .bat, .js, .html or .vbs.
ALLOWED_SUFFIXES = (".exe", ".msi", ".zip")

# 50 MB. Large enough for a vendor installer, small enough that a mistake is
# noticed quickly rather than filling a disk.
MAX_APP_BYTES = 50 * 1024 * 1024

# Screenshot formats. SVG is deliberately absent: it is markup that a browser
# parses and can script, so allowing it here would undo the point of the
# allowlist. These four are raster images, decoded as pixels and nothing more.
ALLOWED_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

# 4 MB. A screenshot of a tool window is far smaller than any real installer,
# so this cap is generous while keeping the directory small.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLUG_MAX = 60

# A DOS/PE executable starts with MZ. A zip starts with PK. Anything else is
# not the type its extension claims to be.
MAGIC = {
    ".exe": (b"MZ",),
    ".msi": (b"\xd0\xcf\x11\xe0",),  # OLE compound file
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

# Image headers, checked against the extension so a renamed script cannot be
# passed off as a screenshot. WebP is a RIFF container, so the WEBP tag sits at
# a fixed offset rather than at the start.
IMAGE_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}
IMAGE_MAGIC_OFFSET = {"webp": 8}


class AppUploadError(Exception):
    """A reason to refuse an upload, safe to show to the admin."""


@dataclass
class ValidatedUpload:
    slug: str
    filename: str
    path: Path | None
    size: int
    sha256: str


def clean_slug(raw: str) -> str:
    """Normalise and validate a slug. Raises rather than silently fixing, so a
    bad slug is visible in the admin form instead of becoming a surprise."""
    slug = (raw or "").strip().lower()
    if not slug:
        raise AppUploadError("A slug is required.")
    if len(slug) > SLUG_MAX:
        raise AppUploadError(f"The slug must be {SLUG_MAX} characters or fewer.")
    if not SLUG_RE.match(slug):
        raise AppUploadError(
            "The slug may only contain lowercase letters, numbers and single "
            "hyphens, for example: crystal-disk-info"
        )
    return slug


def sanitise_filename(client_filename: str, slug: str, suffix: str) -> str:
    """Build the stored filename from the slug, keeping only the suffix.

    The client's filename is never used to build a path. Taking just its
    extension means the stored name cannot contain a directory separator or
    anything else that would change where the file lands.
    """
    return f"{slug}{suffix.lower()}"


def check_suffix(client_filename: str) -> str:
    """Return the validated lowercase suffix, or raise."""
    name = (client_filename or "").strip()
    # Take the last component only, in case a browser sent a path.
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if not suffix:
        raise AppUploadError(
            "That file has no extension. Allowed types are "
            + ", ".join(ALLOWED_SUFFIXES)
        )
    if suffix not in ALLOWED_SUFFIXES:
        raise AppUploadError(
            f"Files ending in {suffix} are not accepted. Allowed types are "
            + ", ".join(ALLOWED_SUFFIXES)
        )
    return suffix


def check_magic(head: bytes, suffix: str) -> None:
    """Confirm the bytes match the claimed file type."""
    signatures = MAGIC.get(suffix)
    if not signatures:
        return
    if not any(head.startswith(signature) for signature in signatures):
        expected = {
            ".exe": "a Windows executable (MZ header)",
            ".msi": "a Windows installer (OLE file)",
            ".zip": "a zip archive (PK header)",
        }.get(suffix, "a matching file")
        raise AppUploadError(
            f"The contents of this file are not {expected}. The extension says "
            f"{suffix} but the data does not match, so the upload was refused."
        )


def check_image_suffix(client_filename: str) -> str:
    """Return the validated lowercase image suffix, or raise."""
    name = (client_filename or "").strip()
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    suffix = Path(name).suffix.lower()
    if not suffix:
        raise AppUploadError(
            "That screenshot has no extension. Allowed types are "
            + ", ".join(ALLOWED_IMAGE_SUFFIXES)
        )
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise AppUploadError(
            f"Screenshots ending in {suffix} are not accepted. Allowed types are "
            + ", ".join(ALLOWED_IMAGE_SUFFIXES)
        )
    return suffix


def check_image_magic(head: bytes, suffix: str) -> None:
    """Confirm the bytes are the raster image the extension claims.

    Only the header is read. The image is never decoded or rewritten on the
    server, so there is no image-parsing code here to attack. What is left is
    that a visitor's browser decodes these pixels, which is why the format list
    excludes SVG.
    """
    if suffix == ".webp":
        # RIFF....WEBP: the size field sits between the two tags.
        if len(head) < 12 or head[:4] != b"RIFF" or head[8:12] != b"WEBP":
            raise AppUploadError(
                "The contents of this file are not a WebP image. The extension "
                "says .webp but the data does not match, so the upload was "
                "refused."
            )
        return

    signatures = IMAGE_MAGIC.get(suffix)
    if not signatures:
        return
    if not any(head.startswith(signature) for signature in signatures):
        expected = {".png": "a PNG image", ".jpg": "a JPEG image"}.get(
            suffix, "a matching image"
        )
        raise AppUploadError(
            f"The contents of this file are not {expected}. The extension says "
            f"{suffix} but the data does not match, so the upload was refused."
        )


def store_upload(
    slug: str,
    client_filename: str,
    chunks: list[bytes],
) -> ValidatedUpload:
    """Validate and write one uploaded binary.

    `chunks` is the already-read body. Splitting read from write keeps the
    streaming cap in the route and leaves this function testable without a
    request.
    """
    suffix = check_suffix(client_filename)
    filename = sanitise_filename(client_filename, slug, suffix)

    data = b"".join(chunks)
    if not data:
        raise AppUploadError("That file is empty.")
    if len(data) > MAX_APP_BYTES:
        raise AppUploadError(
            f"That file is {len(data) / 1024 / 1024:.1f} MB. "
            f"The limit is {MAX_APP_BYTES // 1024 // 1024} MB."
        )

    check_magic(data[:8], suffix)

    digest = hashlib.sha256(data).hexdigest()
    store = storage.backend()
    # Validation is complete, so only now does anything reach storage. A file
    # refused above never creates an object, which matters when the backend is a
    # shared bucket rather than a directory that gets cleaned up later.
    try:
        store.put(filename, data)
    except StorageError as exc:
        raise AppUploadError(
            _write_failure(filename, store.name, "binary", exc)
        ) from exc

    return ValidatedUpload(
        slug=slug,
        filename=filename,
        path=store.local_path(filename),
        size=len(data),
        sha256=digest,
    )


def _write_failure(filename: str, backend_name: str, subject: str, exc: Exception) -> str:
    """Turn a storage failure into something the admin can act on.

    `subject` names the thing being stored, so the same message works for a
    binary and a screenshot without either being patched into the other.
    """
    if backend_name == "supabase":
        return (
            f"The {subject} could not be saved to the storage bucket. Check "
            "that the bucket exists, is private, and that "
            f"FIXITHUB_STORAGE_KEY is the service-role key. ({type(exc).__name__})"
        )
    return (
        f"The {subject} could not be written to disk. Check that the {subject} "
        f"directory is writable. ({type(exc).__name__})"
    )


def store_image(
    slug: str,
    client_filename: str,
    chunks: list[bytes],
) -> ValidatedUpload:
    """Validate and write one uploaded screenshot.

    Mirrors store_upload, but writes into a separate images directory and
    validates an image header instead of an executable one. The stored name is
    derived from the slug, so a screenshot cannot choose its own path.
    """
    suffix = check_image_suffix(client_filename)
    filename = f"{slug}-shot{suffix}"

    data = b"".join(chunks)
    if not data:
        raise AppUploadError("That screenshot is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise AppUploadError(
            f"That screenshot is {len(data) / 1024 / 1024:.1f} MB. "
            f"The limit is {MAX_IMAGE_BYTES // 1024 // 1024} MB."
        )

    check_image_magic(data[:16], suffix)

    digest = hashlib.sha256(data).hexdigest()
    store = storage.image_backend()
    try:
        store.put(filename, data)
    except StorageError as exc:
        raise AppUploadError(
            _write_failure(filename, store.name, "screenshot", exc)
        ) from exc

    return ValidatedUpload(
        slug=slug,
        filename=filename,
        path=store.local_path(filename),
        size=len(data),
        sha256=digest,
    )


def remove_stored_image(filename: str) -> None:
    """Delete a stored screenshot, ignoring one that is already gone."""
    if not filename:
        return
    try:
        storage.image_backend().delete(filename)
    except StorageError:
        pass


def stored_image_path(filename: str) -> Path | None:
    """Resolve a stored screenshot name to a path inside the images directory.

    Returns None unless the resolved path really is inside IMAGES_DIR, so a
    name that escaped validation still cannot be served. None is also the answer
    when storage is remote: there is no path, and the caller reads the bytes
    through read_image instead.
    """
    if not filename or "/" in filename or "\\" in filename:
        return None
    return storage.image_backend().local_path(filename)


def read_image(filename: str) -> bytes | None:
    """The screenshot's bytes, or None when it is not there."""
    if not filename or "/" in filename or "\\" in filename:
        return None
    return storage.image_backend().get(filename)


# A real, declared content type per suffix. Served rather than guessed from the
# file, so a mismatched name cannot make a browser sniff its way to something
# else. nosniff on the response does the rest.
IMAGE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def image_content_type(filename: str) -> str:
    return IMAGE_CONTENT_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream")


def remove_stored(filename: str) -> None:
    """Delete a stored binary, ignoring one that is already gone."""
    if not filename:
        return
    try:
        storage.backend().delete(filename)
    except StorageError:
        pass


def hash_file(path: Path) -> str | None:
    """Hash a file on disk, or None if it cannot be read."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


def stored_path(filename: str) -> Path | None:
    """Resolve a stored filename to a path inside the upload directory.

    Returns None unless the resolved path really is inside APPS_DIR, so a
    filename that escaped validation still cannot be served. None is also the
    answer when storage is remote, where the caller reads bytes instead.
    """
    if not filename or "/" in filename or "\\" in filename:
        return None
    return storage.backend().local_path(filename)


def read_binary(filename: str) -> bytes | None:
    """The binary's bytes, or None when it is not there."""
    if not filename or "/" in filename or "\\" in filename:
        return None
    return storage.backend().get(filename)


def file_present(filename: str) -> bool:
    """Whether the stored file exists, without reading it.

    Cheaper than stat() for remote storage, which only needs one small list
    request rather than the object's size and metadata.
    """
    if not filename or "/" in filename or "\\" in filename:
        return False
    return storage.backend().stat(filename) is not None


def format_size(size: int) -> str:
    if size <= 0:
        return "unknown"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def shorten_hash(value: str) -> str:
    """First 16 hex characters, for display in a table."""
    return (value or "")[:16]