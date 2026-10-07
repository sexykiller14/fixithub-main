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

from app.main import app as _fastapi_app


class VercelPathMiddleware:
    """ASGI middleware to resolve the real request path on Vercel.

    When Vercel routes or rewrites requests to api/index.py, the ASGI scope
    path may be passed as '/api/index.py' instead of the client's actual requested
    URL path (e.g. '/' or '/articles'). This middleware restores the true path
    from Vercel's x-matched-path or x-forwarded-uri header, preventing 404s.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            headers = dict(scope.get("headers", []))

            # Check headers injected by Vercel's edge routing layer
            matched_header = headers.get(b"x-matched-path") or headers.get(b"x-forwarded-uri")
            if matched_header:
                real_path = matched_header.decode("latin-1").split("?")[0]
                if real_path and real_path not in ("/api/index.py", "/api/index"):
                    scope["path"] = real_path
                    path = real_path

            # If path is still pointing directly to the entrypoint script
            if path in ("/api/index.py", "/api/index", "/api/index.py/"):
                scope["path"] = "/"
            elif path.startswith("/api/index.py/"):
                scope["path"] = path[len("/api/index.py"):]

        await self.app(scope, receive, send)


app = VercelPathMiddleware(_fastapi_app)

__all__ = ["app"]
