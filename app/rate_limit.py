"""In-memory sliding window rate limiting for the network tools.

10 requests per minute per client IP by default. This is per-process state,
which is correct for a single uvicorn worker and documented in the README for
multi-worker deployments.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .config import settings
from .security import client_ip


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_after: int
    limit: int


class SlidingWindowLimiter:
    """Thread-safe sliding window counter keyed by client IP."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> RateLimitResult:
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            timestamps = [ts for ts in self._hits.get(key, []) if ts > cutoff]
            if len(timestamps) >= self.max_requests:
                self._hits[key] = timestamps
                oldest = timestamps[0]
                reset_after = max(1, int(round(oldest + self.window - now)) + 1)
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    reset_after=reset_after,
                    limit=self.max_requests,
                )
            timestamps.append(now)
            self._hits[key] = timestamps
            remaining = self.max_requests - len(timestamps)
            reset_after = int(round(timestamps[0] + self.window - now)) + 1
        return RateLimitResult(
            allowed=True,
            remaining=max(0, remaining),
            reset_after=max(1, reset_after),
            limit=self.max_requests,
        )

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def cleanup(self) -> None:
        """Drop stale keys so memory does not grow with unique client IPs."""
        cutoff = time.monotonic() - self.window
        with self._lock:
            for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                self._hits.pop(key, None)


tool_limiter = SlidingWindowLimiter(settings.rate_limit_max, settings.rate_limit_window)

# A tighter bucket for the admin login form.
login_limiter = SlidingWindowLimiter(10, 300)

# A small bucket for feedback so it cannot be used to flood the database.
feedback_limiter = SlidingWindowLimiter(20, 600)

# Tight, because "Ask us anything" is an unauthenticated endpoint that inserts a
# row per request. Same reasoning as the comment bucket.
ask_limiter = SlidingWindowLimiter(5, 600)

# Its own bucket rather than sharing the login one. Every attempt here runs a
# cost-12 bcrypt verify, roughly 300ms of CPU, so an unthrottled version of this
# form would be a cheap way to make the server work.
password_limiter = SlidingWindowLimiter(5, 300)

# Looser, because the widget polls this one while its panel is open. Still bounded
# so an open endpoint cannot be turned into cheap load.
ask_poll_limiter = SlidingWindowLimiter(120, 600)


def client_key(request: Request, prefix: str = "tool") -> str:
    return f"{prefix}:{client_ip(request)}"


API_PREFIXES = ("/api", "/tools/api")


def _is_api_request(request: Request) -> bool:
    return request.url.path.startswith(API_PREFIXES)


def enforce(
    request: Request,
    limiter: SlidingWindowLimiter,
    prefix: str = "tool",
    message: str | None = None,
) -> Response | None:
    """Return a 429 response when the limit is exceeded, otherwise None.

    API endpoints get JSON; browser pages get a rendered HTML error page, so a
    throttled visitor sees something readable rather than raw JSON.
    """
    result = limiter.check(client_key(request, prefix))
    if result.allowed:
        return None

    text = message or (
        f"Rate limit reached: {result.limit} requests per "
        f"{limiter.window} seconds. Try again in {result.reset_after} seconds."
    )
    headers = {
        "Retry-After": str(result.reset_after),
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": str(result.reset_after),
    }

    if _is_api_request(request):
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "error": text,
                "retry_after": result.reset_after,
                "limit": result.limit,
            },
            headers=headers,
        )

    from .templates import render_error

    html = render_error(
        "error.html",
        {
            "status_code": 429,
            "error_title": "Too many requests",
            "error_message": text,
        },
    )
    return HTMLResponse(html, status_code=429, headers=headers)
