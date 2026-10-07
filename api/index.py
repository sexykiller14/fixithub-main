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

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.main import app


class _VercelPathFix(BaseHTTPMiddleware):
    """Fix the request path when Vercel routes everything to api/index.py.

    Vercel's rewrite rule sends all requests to api/index.py, which makes the
    ASGI scope path '/api/index.py'. The real URL is available in the
    x-matched-path header. We restore it so FastAPI routes work correctly.
    """

    async def dispatch(self, request: Request, call_next):
        # x-matched-path contains the original URL path (e.g. '/' or '/articles')
        real_path = request.headers.get("x-matched-path") or request.headers.get("x-forwarded-uri")
        if real_path:
            real_path = real_path.split("?")[0]
            # Only override if it is not pointing back at the entrypoint itself
            if real_path and real_path not in ("/api/index.py", "/api/index", "/api/index.py/"):
                request.scope["path"] = real_path
        elif request.scope.get("path") in ("/api/index.py", "/api/index", "/api/index.py/"):
            request.scope["path"] = "/"
        elif request.scope.get("path", "").startswith("/api/index.py/"):
            request.scope["path"] = request.scope["path"][len("/api/index.py"):]

        return await call_next(request)


# Add the Vercel path-fix middleware directly to the FastAPI app.
# Vercel requires `app` to be the FastAPI instance itself.
app.add_middleware(_VercelPathFix)

__all__ = ["app"]
