"""The public "Ask us anything" endpoint used by the floating widget.

Three decisions decide how this behaves.

Questions are stored, not answered automatically. The admin reads the queue at
/admin/questions and replies by hand. An unauthenticated endpoint that reaches a
language model is an open relay for whatever that model will say about your site,
so there is no automatic answer here.

The sender is anonymous unless they were already signed in. The widget asks for
no personal detail, and this route never invents one: the email is read from the
session cookie, never from the body, so a caller cannot attach someone else's
address to a question.

Reading a reply needs the token from submission. The token is random, returned
once, and stored only as a SHA-256. Without it the reply endpoint answers 404
rather than 403, because a 403 would confirm that a given id exists and let
anyone walk the queue.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..config import USER_SESSION_COOKIE
from ..db import get_db
from ..models import Question
from ..rate_limit import ask_limiter, ask_poll_limiter, enforce
from ..security import client_ip
from ..services.search import hash_ip

router = APIRouter()

# Mirrors CONFIG.maxLength in app/static/js/ask-widget.js. Enforced again here
# because the browser's maxlength is a hint, not a guarantee.
MAX_PROMPT = 500
MIN_PROMPT = 2
MAX_PAGE_URL = 400


def _json_error(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=code, content={"ok": False, "error": message})


def _hash_token(token: str) -> str:
    """Storing only the hash means a database leak does not expose live tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _reader(request: Request, db: Session):
    """The signed-in reader, or None. Resolved from the cookie, never the body."""
    from ..services.accounts import current_user

    return current_user(db, request.cookies.get(USER_SESSION_COOKIE))


async def _payload(request: Request) -> dict:
    """Accept a JSON body, returning {} rather than raising on malformed input."""
    if "application/json" not in request.headers.get("content-type", ""):
        return {}
    try:
        data = await request.json()
    except Exception:  # noqa: BLE001 - treat malformed JSON as empty
        return {}
    return data if isinstance(data, dict) else {}


@router.post("/api/ask", name="api_ask")
async def api_ask(request: Request, db: Session = Depends(get_db)):
    """Store a question and hand back the token used to read the reply."""
    limited = enforce(
        request,
        ask_limiter,
        prefix="ask",
        message="You have sent several questions recently. Try again in a few minutes.",
    )
    if limited is not None:
        return limited

    body = await _payload(request)
    prompt = str(body.get("prompt", "")).strip()[:MAX_PROMPT]
    if len(prompt) < MIN_PROMPT:
        return _json_error("Please write a little more before sending.")

    user = _reader(request, db)
    token = secrets.token_urlsafe(32)

    question = Question(
        prompt=prompt,
        page_url=str(body.get("page_url", "")).strip()[:MAX_PAGE_URL],
        email=user.email if user is not None else "",
        user_id=user.id if user is not None else None,
        ip_hash=hash_ip(client_ip(request)),
        token_hash=_hash_token(token),
    )
    db.add(question)
    db.commit()

    return JSONResponse(
        content={
            "ok": True,
            "id": question.id,
            "status": question.status,
            # Returned exactly once. The widget keeps it to poll for the reply.
            "token": token,
        }
    )


@router.get("/api/ask/{question_id}", name="api_ask_status")
def api_ask_status(
    question_id: int,
    request: Request,
    token: str = "",
    db: Session = Depends(get_db),
):
    """Return the admin's reply, but only for the token minted at submission."""
    limited = enforce(request, ask_poll_limiter, prefix="ask-read")
    if limited is not None:
        return limited

    question = db.get(Question, question_id)
    if question is None or not token:
        return _json_error("Question not found.", code=404)

    if not hmac.compare_digest(question.token_hash, _hash_token(token)):
        # 404 rather than 403: a 403 would confirm the id exists, which turns
        # this into a way to enumerate the whole queue.
        return _json_error("Question not found.", code=404)

    return JSONResponse(
        content={
            "ok": True,
            "status": question.status,
            "reply": question.reply if question.is_answered else "",
        }
    )