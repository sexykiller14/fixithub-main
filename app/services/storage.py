"""Byte storage for admin-uploaded files, on disk or in Supabase Storage.

The site has two kinds of state that are not rows in the database: the binaries
and screenshots an admin uploads, and (separately) the TOTP secret for admin
two-factor enrolment. Both were files on disk, which works on Docker, Render and
Railway but not on Vercel, where the filesystem is read-only and is discarded on
every deploy. Rather than teach each caller about that, this module picks a
backend from the environment and presents the same operations either way.

  FIXITHUB_STORAGE_URL and FIXITHUB_STORAGE_KEY set  ->  Supabase Storage
  unset                                              ->  local disk

Every operation takes the stored *filename*, never a path, and each backend
decides where that name actually lands: the local one keeps the existing
directory layout, so an existing Docker install is unaffected, and the Supabase
one prefixes the object key. Callers therefore never build a location and
cannot get it wrong.

The Supabase backend is written against the Storage REST API with httpx rather
than the supabase SDK, because httpx is already a dependency and the SDK is not.
It means one fewer thing to install and one fewer version to track.

Nothing here decides *whether* a file is acceptable. Extension allowlists, magic
byte checks and size caps are the caller's job and run before put() is reached,
so a refused upload never reaches storage.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# An upload of a 50 MB installer on a cold lambda is the slow case, so this is
# generous. A longer hang would hold the request open rather than fail fast.
STORAGE_TIMEOUT = 30.0

DEFAULT_BUCKET = "fixithub-apps"

# Where screenshots go inside the bucket. Distinct from the binary prefix so a
# screenshot can never overwrite a binary, or the reverse.
BINARY_PREFIX = "apps"
IMAGE_PREFIX = "screenshots"


class StorageError(Exception):
    """A storage operation failed. Safe to log, not to show a visitor."""


def _configured() -> tuple[str, str] | None:
    url = (os.environ.get("FIXITHUB_STORAGE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("FIXITHUB_STORAGE_KEY") or "").strip()
    if url and key:
        return url, key
    return None


def storage_configured() -> bool:
    return _configured() is not None


def _bucket() -> str:
    return (os.environ.get("FIXITHUB_STORAGE_BUCKET") or DEFAULT_BUCKET).strip()


def _safe_name(filename: str) -> str:
    """Reject anything that is not a plain filename.

    Every backend funnels names through this. On disk the risk is a path escape
    out of the upload directory; on Supabase the name becomes a URL path segment,
    so ".." there would address an object outside the intended prefix. Both are
    prevented by refusing separators outright.
    """
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise StorageError(f"Refusing to use {filename!r} as a stored filename")
    return filename


# ---------------------------------------------------------------- local disk


class LocalStorage:
    """Files on the local filesystem. Unchanged layout, for non-serverless hosts."""

    name = "local"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, filename: str) -> Path:
        return self.root / _safe_name(filename)

    def put(self, filename: str, data: bytes) -> None:
        target = self._path(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Write under a temporary name and move into place, so a concurrent
        # reader can never observe a half-written file.
        temporary = target.parent / f".{target.name}.partial"
        try:
            temporary.write_bytes(data)
            temporary.replace(target)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StorageError(
                f"Could not write {filename}: {type(exc).__name__}"
            ) from exc

    def get(self, filename: str) -> bytes | None:
        try:
            return self._path(filename).read_bytes()
        except (OSError, StorageError):
            return None

    def stat(self, filename: str) -> dict | None:
        """Size and checksum for one file, or None when it is not there."""
        try:
            path = self._path(filename)
        except StorageError:
            return None
        if not path.is_file():
            return None
        try:
            data = path.read_bytes()
        except OSError:
            return None
        return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def delete(self, filename: str) -> None:
        try:
            self._path(filename).unlink(missing_ok=True)
        except (OSError, StorageError):
            pass

    def local_path(self, filename: str) -> Path | None:
        """The on-disk path, or None when the file is not there.

        Only the local backend can answer this. Callers use it to hand
        FileResponse a path, which streams the file instead of buffering it in
        memory; remote objects are buffered instead, since there is no path to
        hand over.
        """
        try:
            path = self._path(filename)
        except StorageError:
            return None
        return path if path.is_file() else None


# ---------------------------------------------------------- supabase storage


class SupabaseStorage:
    """Private objects in a Supabase Storage bucket, over the REST API.

    The bucket is expected to be private. Downloads are proxied through the app
    rather than handed out as public URLs, because the routes that serve them
    gate on a confirmed reader account, and because the response headers
    (nosniff, Content-Disposition attachment, the image CSP) are the reason the
    bytes are safe to hand to a browser at all.
    """

    name = "supabase"

    def __init__(self, url: str, key: str, bucket: str, prefix: str) -> None:
        self.root = f"{url}/storage/v1/object"
        self.bucket = bucket
        self.prefix = prefix
        self.headers = {"Authorization": f"Bearer {key}", "apikey": key}

    def _object_url(self, filename: str) -> str:
        return f"{self.root}/{self.bucket}/{self.prefix}/{_safe_name(filename)}"

    def put(self, filename: str, data: bytes) -> None:
        # x-upsert makes a repeat upload replace rather than fail with 409, which
        # is what an admin re-uploading a newer build of the same tool expects.
        headers = {
            **self.headers,
            "x-upsert": "true",
            "Content-Type": "application/octet-stream",
            # Recorded so stat() can verify integrity without downloading the
            # object again. Only written by this module, with the service key,
            # after the bytes were validated and hashed locally.
            "x-metadata-sha256": hashlib.sha256(data).hexdigest(),
        }
        try:
            response = httpx.put(
                self._object_url(filename),
                content=data,
                headers=headers,
                timeout=STORAGE_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise StorageError(f"Could not upload {filename}: {type(exc).__name__}") from exc
        if response.status_code not in (200, 201):
            raise StorageError(
                f"Could not upload {filename}: HTTP {response.status_code} {response.text[:200]}"
            )

    def get(self, filename: str) -> bytes | None:
        try:
            response = httpx.get(self._object_url(filename), headers=self.headers, timeout=STORAGE_TIMEOUT)
        except httpx.HTTPError as exc:
            log.warning("Storage GET failed for %s: %s", filename, type(exc).__name__)
            return None
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            log.warning("Storage GET returned HTTP %s for %s", response.status_code, filename)
            return None
        return response.content

    def stat(self, filename: str) -> dict | None:
        """Size and the checksum recorded at upload, without downloading.

        This matters because of the 50 MB cap: the detail page verifies
        integrity on every view, and fetching the object to hash it would mean
        pulling half a gigabyte through a lambda to draw a page.
        """
        try:
            key = f"{self.prefix}/{_safe_name(filename)}"
        except StorageError:
            return None
        try:
            response = httpx.post(
                f"{self.root}/list/{self.bucket}",
                json={"prefix": key, "limit": 10},
                headers={**self.headers, "Content-Type": "application/json"},
                timeout=STORAGE_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            log.warning("Storage list failed for %s: %s", filename, type(exc).__name__)
            return None
        if response.status_code != 200:
            log.warning("Storage list returned HTTP %s for %s", response.status_code, filename)
            return None
        try:
            entries = response.json()
        except ValueError:
            return None
        for entry in entries or []:
            # The list endpoint returns everything under the prefix directory,
            # so the match has to be exact rather than merely prefixed.
            if entry.get("name") != key:
                continue
            size = entry.get("size")
            return {
                "size": int(size) if isinstance(size, (int, float)) else 0,
                "sha256": (entry.get("metadata") or {}).get("sha256"),
            }
        return None

    def delete(self, filename: str) -> None:
        try:
            httpx.delete(self._object_url(filename), headers=self.headers, timeout=STORAGE_TIMEOUT)
        except httpx.HTTPError as exc:
            log.warning("Storage delete failed for %s: %s", filename, type(exc).__name__)

    def local_path(self, filename: str) -> Path | None:
        """Never available. Callers buffer these objects instead."""
        return None


# ----------------------------------------------------------------- selection

# Cached per process: building a backend reads the environment, and switching
# mid-process would mean objects written to one backend being read from another.
_binary_backend: LocalStorage | SupabaseStorage | None = None
_image_backend: LocalStorage | SupabaseStorage | None = None


def backend() -> LocalStorage | SupabaseStorage:
    """The backend for uploaded binaries."""
    global _binary_backend
    if _binary_backend is None:
        config = _configured()
        if config:
            url, key = config
            _binary_backend = SupabaseStorage(url, key, _bucket(), BINARY_PREFIX)
            log.info("Using Supabase Storage bucket %s", _bucket())
        else:
            from ..config import APPS_DIR

            _binary_backend = LocalStorage(APPS_DIR)
    return _binary_backend


def image_backend() -> LocalStorage | SupabaseStorage:
    """The backend for screenshots. Separate from the binary one, as above."""
    global _image_backend
    if _image_backend is None:
        config = _configured()
        if config:
            url, key = config
            _image_backend = SupabaseStorage(url, key, _bucket(), IMAGE_PREFIX)
        else:
            from ..config import IMAGES_DIR

            _image_backend = LocalStorage(IMAGES_DIR)
    return _image_backend


def reset_for_tests() -> None:
    """Forget the cached backends, so a test can change the environment."""
    global _binary_backend, _image_backend
    _binary_backend = None
    _image_backend = None
