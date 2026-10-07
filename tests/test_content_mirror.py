"""The GitHub content mirror.

The mirror exists because the site runs from Postgres while the repository holds
the markdown, and on Vercel the filesystem is read-only, so an admin's edit
reached the database and never the repository. What matters is the asymmetry it
is built around: the save must succeed whether or not the push does.

These tests pin that asymmetry hardest, because getting it wrong in the other
direction is the failure that takes a content site down.
"""

from __future__ import annotations

import base64

import pytest

from app.services import github


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    """A configured mirror, with HTTP replaced by a recording double."""
    monkeypatch.setenv("FIXITHUB_GITHUB_TOKEN", "github_pat_test_token")
    monkeypatch.setenv("FIXITHUB_GITHUB_REPO", "sexykiller14/fixithub")
    monkeypatch.setenv("FIXITHUB_GITHUB_BRANCH", "main")

    calls: list = []

    class FakeResponse:
        def __init__(self, status_code=200, payload=None, text=""):
            self.status_code = status_code
            self._payload = payload if payload is not None else {}
            self.text = text

        def json(self):
            if isinstance(self._payload, Exception):
                raise self._payload
            return self._payload

    class FakeClient:
        def __init__(self, get=None, put=None):
            self._get = get
            self._put = put

        def get(self, url, headers=None, timeout=None):
            calls.append(("GET", url))
            return self._get(url) if self._get else FakeResponse(404, {})

        def put(self, url, json=None, headers=None, timeout=None):
            calls.append(("PUT", url, json))
            return self._put(url, json) if self._put else FakeResponse(
                200, {"commit": {"sha": "abc123def456"}}
            )

    def install(get=None, put=None):
        monkeypatch.setattr(github.httpx, "get", FakeClient(get, put).get)
        monkeypatch.setattr(github.httpx, "put", FakeClient(get, put).put)
        return calls

    return install


def test_unconfigured_without_a_token(monkeypatch):
    monkeypatch.delenv("FIXITHUB_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("FIXITHUB_GITHUB_REPO", raising=False)
    assert not github.configured()


def test_unconfigured_when_only_the_repo_is_set(monkeypatch):
    monkeypatch.setenv("FIXITHUB_GITHUB_REPO", "sexykiller14/fixithub")
    monkeypatch.delenv("FIXITHUB_GITHUB_TOKEN", raising=False)
    assert not github.configured()


def test_configured_with_both(configured):
    assert github.configured()
    assert github.repo() == "sexykiller14/fixithub"
    assert github.branch() == "main"


def test_branch_defaults_to_main(monkeypatch):
    monkeypatch.setenv("FIXITHUB_GITHUB_BRANCH", "")
    assert github.branch() == "main"


# ------------------------------------------------------------- path handling


def test_a_traversing_path_is_refused(configured):
    """A crafted path must not address a file outside content/."""
    for path in ("../secrets.txt", "content/../../etc/passwd", "/etc/passwd"):
        with pytest.raises(github.GitHubError):
            github._content_url(path)


def test_a_normal_content_path_is_accepted(configured):
    url = github._content_url("content/hardware/bsod-guide.md")
    assert url.endswith("/repos/sexykiller14/fixithub/contents/content/hardware/bsod-guide.md")


# ------------------------------------------------------------------ pushing


def test_a_new_file_is_created_without_a_sha(configured):
    calls = configured()
    ok, detail = github.mirror_article(
        "content/new.md", "# New\n", "new-slug"
    )

    assert ok
    payload = [c for c in calls if c[0] == "PUT"][0][2]
    assert "sha" not in payload, "a create must not send a sha"
    assert base64.b64decode(payload["content"]).decode() == "# New\n"
    assert payload["branch"] == "main"


def test_an_existing_file_is_updated_with_its_sha(configured):
    """An update must carry the current blob SHA.

    The Contents API rejects a write to an existing file that omits it, and
    rejects one that carries a stale value, so reading the SHA first is the
    difference between a second edit working and failing.
    """
    calls = configured(
        get=lambda url: type("R", (), {
            "status_code": 200,
            "json": lambda self: {"sha": "existing-blob-sha"},
            "text": "",
        })()
    )

    ok, _detail = github.mirror_article("content/old.md", "# Old\n", "old-slug")

    assert ok
    payload = [c for c in calls if c[0] == "PUT"][0][2]
    assert payload["sha"] == "existing-blob-sha"


def test_an_unchanged_file_makes_no_commit(configured):
    """A repeat save should not fill the history with empty commits.

    The write is attempted and GitHub answers 200 with no commit, which is what
    the API does when the blob is byte-identical.
    """
    configured(
        put=lambda url, json: type("R", (), {
            "status_code": 200,
            "json": lambda self: {},
            "text": "",
        })()
    )
    ok, detail = github.mirror_article("content/same.md", "# Same\n", "same-slug")

    assert ok
    assert detail == "unchanged"


# ------------------------------------------------- the save must not depend


def test_a_push_failure_is_reported_not_raised(configured):
    """The one invariant the whole design rests on."""
    configured(put=lambda url, json: type("R", (), {
        "status_code": 500,
        "json": lambda self: {},
        "text": "boom",
    })())

    ok, detail = github.mirror_article("content/x.md", "# X\n", "x-slug")

    assert not ok
    assert "500" in detail


def test_a_conflict_is_reported_and_not_retried(configured):
    """A 409 means the branch moved. Retrying could overwrite the other commit."""
    calls = configured(put=lambda url, json: type("R", (), {
        "status_code": 409,
        "json": lambda self: {},
        "text": "conflict",
    })())

    ok, detail = github.mirror_article("content/x.md", "# X\n", "x-slug")

    assert not ok
    assert "409" in detail
    # One read, one write. A retry would mean two writes.
    assert len([c for c in calls if c[0] == "PUT"]) == 1


def test_mirroring_when_unconfigured_is_a_no_op(monkeypatch):
    monkeypatch.delenv("FIXITHUB_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("FIXITHUB_GITHUB_REPO", raising=False)
    ok, detail = github.mirror_article("content/x.md", "# X\n", "x-slug")
    assert not ok
    assert detail == "not configured"


def test_the_token_never_appears_in_a_failure_detail(configured):
    configured(put=lambda url, json: type("R", (), {
        "status_code": 401,
        "json": lambda self: {},
        "text": "bad credentials",
    })())

    ok, detail = github.mirror_article("content/x.md", "# X\n", "x-slug")

    assert not ok
    assert "github_pat_test_token" not in detail
