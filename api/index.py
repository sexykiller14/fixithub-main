"""Vercel Serverless Function entrypoint for FixIT Hub."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root directory to sys.path so app and its packages can be resolved
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure VERCEL environment marker is set
os.environ.setdefault("VERCEL", "1")

from app.main import app

_ENTRYPOINT_PATHS = ("/api/index.py", "/api/index")


def _restore_path(path: str, headers: dict[str, str]) -> str:
    """Return the real request path when Vercel hands us the entrypoint path.

    Vercel's FastAPI support normally passes the original path through, in which
    case this is a no-op. If a rewrite to the entrypoint is ever in play, the
    path arrives as '/api/index.py'; recover it from a forwarding header when
    one carries a real path, otherwise fall back to stripping the prefix.
    """
    for prefix in _ENTRYPOINT_PATHS:
        if path == prefix or path == prefix + "/":
            break
        if path.startswith(prefix + "/"):
            return path[len(prefix):]
    else:
        return path  # Not the entrypoint: leave real paths alone.

    for name in ("x-matched-path", "x-forwarded-uri"):
        candidate = (headers.get(name) or "").split("?", 1)[0]
        if candidate.startswith("/") and candidate.rstrip("/") not in _ENTRYPOINT_PATHS:
            return candidate
    return "/"


class _VercelPathFix:
    """Pure ASGI middleware, so the rewritten scope reaches the router."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            path = _restore_path(scope.get("path", "/"), headers)
            if path != scope.get("path"):
                scope = dict(scope)
                scope["path"] = path
                scope["raw_path"] = path.encode("utf-8")
        await self.inner(scope, receive, send)


# Vercel requires `app` to be the FastAPI instance itself.
app.add_middleware(_VercelPathFix)

__all__ = ["app"]
