"""Reader comments on articles, stop codes and uploaded tools.

Three rules decide how this behaves.

Comments are plain text. A reader's words never reach the markdown renderer, so
there is no path from a comment to injected markup on an article page. The
templates escape the body.

Comments are moderated. A new comment is `pending` and invisible to everyone but
its author and the admin queue. With open registration, an unmoderated comment
box is a spam relay and a link-farm, and the cost of that lands on the readers
rather than the spammer.

Comments belong to a real account. That is what lets the author delete their
own, and what makes the deletion right on the privacy page meaningful.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import build_context, total_counts
from ..models import AppDownload, Article, Comment, StopCode
from ..rate_limit import SlidingWindowLimiter, enforce
from ..security import client_ip, valid_reader_csrf
from ..services.search import hash_ip
from ..templates import render

from .accounts import signed_in_reader

router = APIRouter()

MAX_BODY = 4000
MIN_BODY = 10

# Comments are cheap to post and expensive to moderate, so the limit is tight.
comment_limiter = SlidingWindowLimiter(5, 600)

TARGET_ARTICLE = "article"
TARGET_STOP_CODE = "stop_code"
TARGET_APP = "app"

TARGET_LABELS = {
    TARGET_ARTICLE: "article",
    TARGET_STOP_CODE: "stop code",
    TARGET_APP: "tool",
}


def resolve_target(db: Session, target_type: str, target_id: int):
    """Find the thing being commented on, or None.

    Kept separate from the posting route so the listing path can never be
    tricked into touching a row of a type the route was not meant to serve.
    """
    if target_type == TARGET_ARTICLE:
        return db.get(Article, target_id)
    if target_type == TARGET_STOP_CODE:
        return db.get(StopCode, target_id)
    if target_type == TARGET_APP:
        return db.get(AppDownload, target_id)
    return None


def target_label(target_type: str, target) -> str:
    if target_type == TARGET_APP:
        return getattr(target, "title", "tool")
    if target_type == TARGET_STOP_CODE:
        return getattr(target, "name", "stop code")
    return getattr(target, "title", "article")


def approved_comments(db: Session, target_type: str, target_id: int, limit: int = 50) -> list[Comment]:
    """Public comments for one page, oldest first so replies read in order."""
    return list(
        db.execute(
            select(Comment)
            .where(
                Comment.target_type == target_type,
                Comment.target_id == target_id,
                Comment.status == Comment.STATUS_APPROVED,
            )
            .order_by(Comment.created_at)
            .limit(limit)
        ).scalars()
    )


def comment_summary(db: Session, target_type: str, target_id: int) -> dict:
    """Counts for the badge on a page: approved, and the author's own pending."""
    approved = db.scalar(
        select(func.count())
        .select_from(Comment)
        .where(
            Comment.target_type == target_type,
            Comment.target_id == target_id,
            Comment.status == Comment.STATUS_APPROVED,
        )
    )
    return {"approved": approved or 0}


def anchor_for(target_type: str, target_id: int, slug_or_name: str) -> str:
    """The URL a comment form posts back to."""
    if target_type == TARGET_ARTICLE:
        return f"/articles/{slug_or_name}"
    if target_type == TARGET_STOP_CODE:
        return f"/bsod/{slug_or_name}"
    return f"/apps/{slug_or_name}"


@router.post("/comments", name="comment_post")
def comment_post(
    request: Request,
    target_type: str = Form("", max_length=20),
    target_id: str = Form("", max_length=20),
    body: str = Form("", max_length=MAX_BODY),
    csrf: str = Form("", max_length=200),
    db: Session = Depends(get_db),
):
    """Record a comment for moderation."""
    limited = enforce(
        request,
        comment_limiter,
        prefix="comment",
        message="You have posted several comments recently. Wait a few minutes.",
    )
    if limited is not None:
        return limited

    user = signed_in_reader(request, db)
    fallback = "/"

    if target_type not in TARGET_LABELS:
        return RedirectResponse(fallback, status_code=303)

    try:
        numeric_id = int(target_id)
    except (TypeError, ValueError):
        return RedirectResponse(fallback, status_code=303)

    if user is None:
        # Send them to sign in and back again, rather than silently dropping it.
        response = RedirectResponse(
            f"/login?next=/comments", status_code=303
        )
        return response

    if not valid_reader_csrf(request, csrf):
        return RedirectResponse(fallback, status_code=303)

    clean = (body or "").strip()
    if len(clean) < MIN_BODY:
        return RedirectResponse(fallback + "?comment=too-short", status_code=303)

    target = resolve_target(db, target_type, numeric_id)
    if target is None:
        return RedirectResponse(fallback, status_code=303)

    slug = getattr(target, "slug", None) or getattr(target, "name", None)
    back = anchor_for(target_type, numeric_id, slug or "")

    db.add(
        Comment(
            user_id=user.id,
            target_type=target_type,
            target_id=numeric_id,
            body=clean,
            status=Comment.STATUS_PENDING,
            ip_hash=hash_ip(client_ip(request)),
        )
    )
    db.commit()

    return RedirectResponse(f"{back}?comment=submitted", status_code=303)


def comment_context(request: Request, db: Session, target_type: str, target_id: int) -> dict:
    """Everything a page needs to render its comment section."""
    user = signed_in_reader(request, db)
    approved = approved_comments(db, target_type, target_id)

    own_pending = []
    if user is not None:
        own_pending = list(
            db.execute(
                select(Comment).where(
                    Comment.target_type == target_type,
                    Comment.target_id == target_id,
                    Comment.user_id == user.id,
                    Comment.status == Comment.STATUS_PENDING,
                )
            ).scalars()
        )

    return {
        "comments": approved,
        "comment_counts": comment_summary(db, target_type, target_id),
        "pending_comments": own_pending,
        "comment_target_type": target_type,
        "comment_target_id": target_id,
        "comment_notice": request.query_params.get("comment", ""),
    }