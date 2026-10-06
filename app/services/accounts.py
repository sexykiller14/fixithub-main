"""Reader accounts: validation, tokens, sessions and verification email.

Two rules shape everything here.

First, only the hash of a token is ever stored. A raw verification link or
session token in the database would mean a leaked backup hands over every live
account, so tokens are generated with `secrets`, hashed with SHA-256, and the
raw value is returned exactly once, to be put in a URL or an email.

Second, an account is not an admin. Nothing in this module or the session
helpers can reach the admin panel, which is guarded separately by a signed
cookie and its own password. That separation is asserted by a test, because it
is the boundary that matters most.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import SITE_URL, settings
from ..models import AuthToken, User
from ..security import hash_password, verify_password

# Deliberately permissive. Refusing unusual-but-valid addresses locks out real
# readers, and a false rejection is worse here than a slightly odd address.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

MIN_PASSWORD = 10
MAX_PASSWORD = 200

TOKEN_PURPOSE_VERIFY = "verify"
TOKEN_PURPOSE_RESET = "reset"
TOKEN_PURPOSE_SESSION = "session"

VERIFY_TTL = timedelta(days=2)
RESET_TTL = timedelta(minutes=60)
SESSION_TTL = timedelta(days=30)
SESSION_IDLE = timedelta(days=14)


class AccountError(Exception):
    """A reason to refuse an account operation, safe to show to the reader."""


@dataclass
class IssuedToken:
    """A freshly created token. `raw` is the only time it is available."""

    raw: str
    user: User


# ------------------------------------------------------------- validation


def normalise_email(raw: str) -> str:
    return (raw or "").strip().lower()


def validate_email(raw: str) -> str:
    """Return the normalised address, or raise."""
    email = normalise_email(raw)
    if not email:
        raise AccountError("Enter your email address.")
    if len(email) > 254:
        raise AccountError("That email address is too long.")
    if ".." in email:
        raise AccountError("That email address is not valid.")
    if not EMAIL_RE.match(email):
        raise AccountError("Enter a valid email address, for example name@example.com")
    return email


def validate_password(password: str, email: str = "") -> str:
    """Reject weak passwords with a reason the reader can act on.

    Length is the requirement. Composition rules push people toward
    `Password1!`, which is barely better than a dictionary word, so the check
    stays on length plus the obvious refusals.
    """
    value = password or ""
    if len(value) < MIN_PASSWORD:
        raise AccountError(
            f"Use at least {MIN_PASSWORD} characters. Longer is stronger and "
            "easier to remember than a short one full of symbols."
        )
    if len(value) > MAX_PASSWORD:
        raise AccountError("That password is too long.")
    lowered = value.lower()
    if lowered in {"password123", "1234567890", "qwertyuiop", "letmein1234"}:
        raise AccountError("That password is too easy to guess. Try a phrase instead.")
    if email:
        local = normalise_email(email).split("@")[0]
        # Only a full-length match is rejected, so `bob@example.com` is fine
        # for someone whose name is `bobby`.
        if len(local) >= 4 and local in lowered:
            raise AccountError("Your password should not contain your email address.")
    return value


# ---------------------------------------------------------------- tokens


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def issue_token(db: Session, user: User, purpose: str, ttl: timedelta) -> IssuedToken:
    """Create a token and store only its hash."""
    raw = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            purpose=purpose,
            expires_at=datetime.now(timezone.utc) + ttl,
        )
    )
    return IssuedToken(raw=raw, user=user)


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email_normalised == normalise_email(email)))


def resolve_token(db: Session, raw: str, purpose: str) -> tuple[User, AuthToken] | None:
    """Look up a valid, unexpired token and return its owner.

    Returns None for every failure mode rather than raising, so a caller cannot
    accidentally tell an attacker whether a token was real but expired or never
    existed.
    """
    if not raw:
        return None
    record = db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(raw),
            AuthToken.purpose == purpose,
        )
    )
    if record is None:
        return None

    now = datetime.now(timezone.utc)
    expires = _as_utc(record.expires_at)
    if expires is not None and expires <= now:
        db.delete(record)
        db.commit()
        return None

    user = db.get(User, record.user_id)
    if user is None or not user.is_active:
        return None
    return user, record


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes even for timezone-aware columns."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def sweep_expired(db: Session) -> int:
    """Delete tokens past their expiry. Returns how many rows went.

    The comparison is done in Python rather than in SQL. SQLite stores these as
    naive datetimes even though the column is timezone-aware, so a SQL
    comparison between an aware and a naive value raises on some versions. The
    rows are filtered with the same `_as_utc` normalisation `resolve_token`
    uses, which keeps one definition of "expired".
    """
    now = datetime.now(timezone.utc)
    removed = 0
    for record in db.scalars(select(AuthToken)).all():
        expires = _as_utc(record.expires_at)
        if expires is not None and expires <= now:
            db.delete(record)
            removed += 1
    db.commit()
    return removed


# ------------------------------------------------------------- accounts


def create_user(db: Session, email: str, password: str) -> tuple[User, IssuedToken]:
    """Register a reader and issue their verification token."""
    clean_email = validate_email(email)
    validate_password(password, clean_email)

    if find_user_by_email(db, clean_email) is not None:
        # Deliberately explicit. This is not a secret an attacker can use to
        # enumerate accounts for anything, because they still cannot sign in
        # without the password.
        raise AccountError("An account already exists for that email address.")

    user = User(
        email=clean_email,
        email_normalised=clean_email,
        password_hash=hash_password(password),
        is_verified=False,
        is_active=True,
    )
    db.add(user)
    db.flush()

    token = issue_token(db, user, TOKEN_PURPOSE_VERIFY, VERIFY_TTL)
    db.commit()
    return user, token


def verify_email(db: Session, raw_token: str) -> bool:
    """Consume a verification token. Returns False if it was not valid."""
    found = resolve_token(db, raw_token, TOKEN_PURPOSE_VERIFY)
    if found is None:
        return False
    user, record = found

    user.is_verified = True
    user.verified_at = datetime.now(timezone.utc)
    # A verified account should not also be holding an unused verification
    # token, so this one is spent here.
    db.delete(record)
    db.commit()
    return True


def check_password(db: Session, email: str, password: str) -> User | None:
    """Return the user when the password matches, otherwise None."""
    user = find_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def start_session(db: Session, user: User) -> IssuedToken:
    """Replace any existing session with a new one.

    Opening a fresh session on every sign-in means a stolen link stops working
    as soon as the real user signs in again.
    """
    db.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == TOKEN_PURPOSE_SESSION,
        )
    )
    token = issue_token(db, user, TOKEN_PURPOSE_SESSION, SESSION_TTL)
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return token


def current_user(db: Session, raw_token: str | None) -> User | None:
    """Resolve a session cookie to its user, or None."""
    if not raw_token:
        return None
    found = resolve_token(db, raw_token, TOKEN_PURPOSE_SESSION)
    if found is None:
        return None
    user, record = found

    now = datetime.now(timezone.utc)
    last_seen = _as_utc(record.last_seen_at)
    if last_seen is not None and now - last_seen > SESSION_IDLE:
        # Idle for too long, so end it even though the absolute expiry is later.
        db.delete(record)
        db.commit()
        return None

    record.last_seen_at = now
    db.commit()
    return user


def end_session(db: Session, raw_token: str | None) -> None:
    """Delete the session row, so the cookie cannot be replayed."""
    if not raw_token:
        return
    db.execute(delete(AuthToken).where(AuthToken.token_hash == hash_token(raw_token)))
    db.commit()


def delete_user(db: Session, user: User) -> int:
    """Delete a reader and everything they wrote. Returns comment count.

    This is the data-deletion path promised on the privacy page, so it has to
    actually remove the comments rather than orphan them.
    """
    from ..models import Comment

    comments = db.scalars(
        select(Comment).where(Comment.user_id == user.id)
    ).all()
    removed = len(comments)

    db.execute(delete(AuthToken).where(AuthToken.user_id == user.id))
    for comment in comments:
        db.delete(comment)
    db.delete(user)
    db.commit()
    return removed


def send_verification_email(user: User, token: str) -> bool:
    """Email a verification link. Returns False if mail is not configured.

    Failing to send is not fatal: the reader can ask for a new link, and the
    admin can verify an account by hand. Failing loudly on a signup form would
    be worse than telling them the email could not be sent right now.
    """
    if not settings.smtp_host or not settings.smtp_from:
        return False

    link = f"{SITE_URL}/verify/{token}"
    message = EmailMessage()
    message["Subject"] = "Confirm your FixIT Hub account"
    message["From"] = settings.smtp_from
    message["To"] = user.email
    message.set_content(
        "Thanks for registering.\n\n"
        "Confirm your account by opening this link:\n\n"
        f"{link}\n\n"
        "The link works for two days. If you did not register, you can ignore "
        "this message and nothing will happen.\n\n"
        "FixIT Hub"
    )

    try:
        if settings.smtp_port == 465:
            # Port 465 is implicit TLS, so the connection is wrapped before the
            # greeting rather than after STARTTLS.
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                smtp.ehlo()
                # Opportunistic TLS on any other port, which is what port 587
                # and most submission servers expect.
                if smtp.has_extn("starttls"):
                    smtp.starttls()
                    smtp.ehlo()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(message)
    except (smtplib.SMTPException, OSError):
        # Logged by the caller; the account still exists and can be verified by
        # requesting another link.
        _log_email(user.email, message["Subject"], False, "SMTP send failed")
        return False
    _log_email(user.email, message["Subject"], True, "")
    return True


def _log_email(to_email: str, subject: str, sent_ok: bool, error: str) -> None:
    """Record that the site tried to send a message, not that it succeeded.

    The body is never stored: a verification or reset link in an admin log
    would be a live credential sitting in the database.
    """
    from ..db import session_scope
    from ..models import EmailLog

    try:
        with session_scope() as log_db:
            log_db.add(
                EmailLog(to_email=to_email, subject=subject, sent_ok=sent_ok, error=error)
            )
    except Exception:  # noqa: BLE001 - logging must never fail the request
        pass


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)