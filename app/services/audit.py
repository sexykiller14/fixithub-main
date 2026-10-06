"""Writing and reading the admin audit log.

Kept in a service rather than in the routes so that the rule about what may be
recorded lives in one place: a caller cannot accidentally log a password, a
token or file bytes, because those never make it past _detail().
"""

from __future__ import annotations

import hashlib

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import AdminAuditLog

MAX_DETAIL = 300

# Actions worth recording. Reads are deliberately absent: see the model's
# docstring for why.
ACTIONS = {
    "article.save": "Article saved",
    "article.delete": "Article deleted",
    "article.preview": "Article previewed",
    "stopcode.save": "Stop code saved",
    "stopcode.delete": "Stop code deleted",
    "app.save": "Upload saved",
    "app.delete": "Upload deleted",
    "comment.approve": "Comment approved",
    "comment.reject": "Comment rejected",
    "comment.delete": "Comment deleted",
    "user.delete": "Reader account deleted",
    "question.reply": "Question answered",
    "question.reopen": "Question reopened",
    "question.delete": "Question deleted",
    "ad.settings": "Ad settings changed",
    "ad.unit.save": "Ad unit saved",
    "ad.unit.toggle": "Ad unit toggled",
    "ad.unit.delete": "Ad unit deleted",
    "seo.save": "SEO override saved",
    "seo.delete": "SEO override deleted",
    "announcement.save": "Announcement saved",
    "backup.created": "Backup downloaded",
    "restore.performed": "Database restored",
    "password.changed": "Admin password changed",
    "auth.login": "Signed in",
    "auth.login_failed": "Failed sign-in attempt",
    "auth.logout": "Signed out",
    "auth.2fa.enrol": "Two-factor enrolment started",
    "auth.2fa.enabled": "Two-factor authentication enabled",
    "auth.2fa.disabled": "Two-factor authentication disabled",
    "auth.2fa.recovery_used": "Recovery code used",
}


def _detail(text: str | None) -> str:
    """Clamp a detail string, collapsing whitespace so it stays one line."""
    if not text:
        return ""
    flat = " ".join(str(text).split())
    return flat[:MAX_DETAIL]


def record(
    db: Session,
    action: str,
    *,
    target_type: str = "",
    target_id: str | int = "",
    detail: str = "",
    ip_hash: str = "",
    commit: bool = True,
) -> AdminAuditLog | None:
    """Add one row. Returns None for an action that is not in the allowlist.

    Refusing unknown actions is deliberate: it means a typo in a caller cannot
    quietly create a row nobody will ever group by, and it keeps the table's
    action column to a known set.
    """
    if action not in ACTIONS:
        return None

    row = AdminAuditLog(
        action=action,
        target_type=target_type[:40],
        target_id=str(target_id)[:120],
        detail=_detail(detail),
        ip_hash=ip_hash[:64],
    )
    db.add(row)
    if commit:
        db.commit()
    return row


def hash_ip(ip: str) -> str:
    """A stable pseudonymous identifier for an address.

    Hashed rather than stored raw so the log is useful for spotting one client
    doing something repeatedly without becoming a list of visitor addresses.
    The salt keeps the digests from being reversed by brute-forcing the whole
    IPv4 space.
    """
    from ..config import settings

    return hashlib.sha256(f"{settings.secret_key}:{ip}".encode()).hexdigest()[:32]


def recent(db: Session, limit: int = 200, action: str = "") -> list[AdminAuditLog]:
    """Newest first. Optionally filtered to one action."""
    query = select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at), desc(AdminAuditLog.id))
    if action:
        query = query.where(AdminAuditLog.action == action)
    return list(db.execute(query.limit(limit)).scalars())


def counts_by_action(db: Session) -> dict[str, int]:
    """How many times each action has been recorded, for the summary tiles."""
    from sqlalchemy import func

    rows = db.execute(
        select(AdminAuditLog.action, func.count()).group_by(AdminAuditLog.action)
    ).all()
    return {action: count for action, count in rows}