"""Mirroring admin content edits to GitHub.

The site's content lives in two places at once. Postgres is what the running app
reads and writes, and the markdown in content/*.md is what the repository holds.
An admin editing an article on Vercel updates the database row immediately, but
the filesystem there is read-only, so the markdown file silently stops being
written and the repository drifts out of date.

This module closes that gap: after a content edit is committed, the matching
markdown file is pushed to GitHub, where it is versioned, reviewable and
recoverable. It is a mirror, not the source of truth. Nothing here is on the
path between an admin saving an article and the article appearing on the site -
a GitHub failure is logged and recorded, and the save stands either way. Making
GitHub authoritative would mean the site went down whenever GitHub did, and an
article edit would block on a network round trip to api.github.com.

Deliberately not attempted:
  - No force-push, no branch rewrites, no history edits of any kind. The Contents
    API only ever creates a commit on top.
  - No token without a repository scope, and no token wider than the one repo.
  - Nothing is ever deleted from the repository. A removed article leaves the
    file in place, because a mirror that destroys data on a mistaken delete is
    worse than one that keeps a stale file.

Configuration, all optional. With no token the module reports itself
unconfigured and every caller treats that as "nothing to do".

    FIXITHUB_GITHUB_TOKEN   fine-grained token, Contents: read and write
    FIXITHUB_GITHUB_REPO    "owner/name"
    FIXITHUB_GITHUB_BRANCH  branch to commit to, default "main"
"""

from __future__ import annotations

import base64
import logging

import httpx

log = logging.getLogger(__name__)

API_ROOT = "https://api.github.com"

# A single content write is a small request/response. Generous enough for a
# cold lambda, short enough that a hung connection does not hold the admin's
# request open long after the save itself has finished.
TIMEOUT = 20.0


class GitHubError(Exception):
    """A push to GitHub failed. Never raised out of a save path."""


def _setting(name: str) -> str:
    import os

    return (os.environ.get(name) or "").strip()


def configured() -> bool:
    """Whether a mirror has been set up at all."""
    return bool(_setting("FIXITHUB_GITHUB_TOKEN") and _setting("FIXITHUB_GITHUB_REPO"))


def repo() -> str:
    return _setting("FIXITHUB_GITHUB_REPO")


def branch() -> str:
    return _setting("FIXITHUB_GITHUB_BRANCH") or "main"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_setting('FIXITHUB_GITHUB_TOKEN')}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fixithub-content-mirror",
    }


def _content_url(path: str) -> str:
    if not path or path.startswith("/"):
        raise GitHubError(f"Refusing to push {path!r}: must be a relative repo path")
    # Each segment is a URL path component, so an encoded separator would let a
    # crafted path address a file outside content/.
    segments = path.split("/")
    if any(seg in {"", ".", ".."} for seg in segments):
        raise GitHubError(f"Refusing to push {path!r}: bad path segment")
    return f"{API_ROOT}/repos/{repo()}/contents/{'/'.join(segments)}"


def current_sha(path: str) -> str | None:
    """The blob SHA currently at `path`, or None when it is not there yet.

    Needed because the Contents API treats a create and an update differently:
    omitting `sha` on an existing file is a 422, and supplying a stale one is a
    409. Reading it first is what makes a repeat edit work.
    """
    try:
        response = httpx.get(_content_url(path), headers=_headers(), timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise GitHubError(f"Could not read {path}: {type(exc).__name__}") from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise GitHubError(f"Could not read {path}: HTTP {response.status_code}")
    try:
        return response.json().get("sha")
    except ValueError as exc:
        raise GitHubError(f"Could not read {path}: malformed response") from exc


def push_content_file(path: str, content: str, message: str) -> str | None:
    """Commit `content` to `path` on the configured branch.

    Returns the new commit SHA, or None when the file was byte-identical to what
    was already there - in which case no commit is made, so a retry or a
    double-submit does not fill the history with empty commits.

    Raises GitHubError on any real failure. Callers are expected to catch it.
    """
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    sha = current_sha(path)

    payload: dict = {
        "message": message,
        "content": encoded,
        "branch": branch(),
    }
    if sha:
        payload["sha"] = sha

    try:
        response = httpx.put(
            _content_url(path), json=payload, headers=_headers(), timeout=TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise GitHubError(f"Could not push {path}: {type(exc).__name__}") from exc

    if response.status_code in (200, 201):
        try:
            commit = response.json().get("commit") or {}
            return commit.get("sha")
        except ValueError:
            return None

    if response.status_code == 409:
        # Someone else committed to the branch between the read and the write.
        # Reported rather than retried: a silent retry could overwrite whatever
        # the other commit contained.
        raise GitHubError(
            f"Could not push {path}: the branch moved while saving (409). "
            "Push again to retry."
        )
    if response.status_code == 422:
        raise GitHubError(f"Could not push {path}: rejected by GitHub (422)")
    raise GitHubError(f"Could not push {path}: HTTP {response.status_code}")


def mirror_article(path: str, markdown: str, slug: str) -> tuple[bool, str]:
    """Mirror one article, reporting rather than raising.

    Returns (ok, detail). The detail is what goes in the audit log, so it has to
    be safe to show an admin: it names the file and the failure, and never
    carries the token.
    """
    if not configured():
        return False, "not configured"
    if not path:
        return False, "no repo path for this article"
    try:
        commit = push_content_file(
            path, markdown, f"content: update {slug} from the admin panel"
        )
    except GitHubError as exc:
        log.warning("Content mirror failed for %s: %s", path, exc)
        return False, str(exc)
    if commit is None:
        return True, "unchanged"
    return True, f"committed {commit[:7]}"
