"""SQLAlchemy models for the FixIT Hub knowledge base.

Tables:
  articles      - markdown guides indexed from /content
  stop_codes    - BSOD bugcheck reference
  feedback      - "was this helpful?" votes
  search_queries- popular search tracking (shown in admin)
  uploads       - minidump upload audit log (metadata only, no file bytes)
  app_downloads - metadata for admin-uploaded binaries; file bytes live on
                  disk, never in the database
  users         - reader accounts, for commenting and downloads only
  auth_tokens   - verification, reset and session tokens (hashed)
  comments      - moderated reader comments on articles, codes and tools
  questions     - "Ask us anything" questions and the admin's reply
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Article(TimestampMixin, Base):
    """A markdown guide from /content, stored for fast search and filtering."""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    summary: Mapped[str] = mapped_column(String(600), default="")
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), default="easy", index=True)
    os_version: Mapped[str] = mapped_column(String(60), default="Windows 10/11")
    reading_time: Mapped[int] = mapped_column(Integer, default=3)
    body: Mapped[str] = mapped_column(Text, default="")
    source_path: Mapped[str] = mapped_column(String(400), default="")
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    helpful_yes: Mapped[int] = mapped_column(Integer, default=0)
    helpful_no: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="published")

    @property
    def helpful_total(self) -> int:
        return self.helpful_yes + self.helpful_no

    @property
    def helpful_percent(self) -> int:
        total = self.helpful_total
        if total == 0:
            return 0
        return round(self.helpful_yes / total * 100)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "tags": self.tags or [],
            "difficulty": self.difficulty,
            "os_version": self.os_version,
            "reading_time": self.reading_time,
            "is_featured": self.is_featured,
            "view_count": self.view_count,
            "status": self.status,
        }


class StopCode(Base):
    """A BSOD bugcheck code with its repair guide."""

    __tablename__ = "stop_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hex: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    code_uint: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    meaning: Mapped[str] = mapped_column(Text, default="")
    causes: Mapped[list] = mapped_column(JSON, default=list)
    fix_steps: Mapped[list] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), default="moderate")
    when_to_call_pro: Mapped[str] = mapped_column(Text, default="")
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    related_slugs: Mapped[list] = mapped_column(JSON, default=list)

    @property
    def short_hex(self) -> str:
        """0x0000007E -> 0x7E for compact display."""
        return "0x%X" % self.code_uint

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code_hex": self.code_hex,
            "code_uint": self.code_uint,
            "short_hex": self.short_hex,
            "name": self.name,
            "meaning": self.meaning,
            "causes": self.causes or [],
            "fix_steps": self.fix_steps or [],
            "difficulty": self.difficulty,
            "when_to_call_pro": self.when_to_call_pro,
        }


class Feedback(Base):
    """A helpful/not helpful vote on an article or stop code."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    target_type: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    helpful: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(String(500), default="")
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    __table_args__ = (
        Index("ix_feedback_target", "target_type", "target_id"),
    )


class SearchQuery(Base):
    """Aggregate record of what users searched for."""

    __tablename__ = "search_queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(250), index=True)
    normalised: Mapped[str] = mapped_column(String(250), index=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    hits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (Index("ix_search_normalised", "normalised"),)


class DumpUpload(Base):
    """Audit row for a minidump analysis. Only metadata is stored.

    The uploaded bytes are parsed in memory and never written to disk, so this
    table deliberately has no file path or blob column.
    """

    __tablename__ = "dump_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(260))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    signature: Mapped[str] = mapped_column(String(8), default="")
    bugcheck_code: Mapped[str] = mapped_column(String(20), default="")
    parsed_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    message: Mapped[str] = mapped_column(String(400), default="")
    os_build: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class User(Base):
    """A registered reader account.

    Accounts exist so a reader can post comments and download the tools. They
    carry no privileges beyond that: nothing in the admin panel reads this
    table, and the admin session is a separate signed cookie checked against a
    separate password.

    The email address is stored because verification and password reset need it.
    It is never exposed in the UI except to the account holder.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    # Lowercased and stripped, kept alongside email so a login lookup can match
    # on it without a case-folding expression in SQL.
    email_normalised: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(120), default="")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    comments: Mapped[list["Comment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AuthToken(Base):
    """A single-use or revocable token belonging to a user.

    Covers email verification, password reset and signed-in sessions in one
    table, distinguished by `purpose`. Only the SHA-256 of the token is stored,
    so a database leak does not hand an attacker working credentials.

    Sessions are kept here rather than in the signed cookie so that logging out
    and an admin banning a user both actually end access, which a cookie cannot
    do on its own.
    """

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(20), index=True)
    # Set for verification and reset tokens so they expire. Sessions use
    # expires_at too, but are also swept by last_seen_at.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class Comment(Base):
    """A reader comment on an article, stop code or uploaded tool.

    Comments are plain text, not markdown. A visitor's words never reach the
    markdown renderer, which removes any chance of someone injecting markup into
    a page.

    New comments start as `pending`. Nothing appears publicly until an admin
    approves it, which is what keeps an open sign-up form from becoming a spam
    relay.
    """

    __tablename__ = "comments"

    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Polymorphic reference: "article", "stop_code" or "app", plus the row id.
    target_type: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int] = mapped_column(Integer, index=True)
    body: Mapped[str] = mapped_column(String(4000), default="")
    status: Mapped[str] = mapped_column(String(20), default=STATUS_PENDING, index=True)
    # Hashed, like feedback, so a comment row does not carry a plain IP.
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderated_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    user: Mapped[User] = relationship(back_populates="comments")

    __table_args__ = (
        Index("ix_comments_target", "target_type", "target_id", "status"),
    )

    @property
    def is_public(self) -> bool:
        return self.status == self.STATUS_APPROVED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "body": self.body,
            "status": self.status,
            "created_at": self.created_at,
        }


class Question(Base):
    """A question sent through the floating "Ask us anything" widget.

    Questions are plain text, like comments: a visitor's words never reach a
    renderer, so there is no path from a question to injected markup.

    The visitor is anonymous by default, because open registration is off and
    the widget asks for no personal detail. `email` is filled in only when the
    sender already had an account, and the route fills it from the session
    cookie rather than from the request body, so it cannot be spoofed.

    `token_hash` is the SHA-256 of a random token handed to the sender's browser
    once, at submission. The visitor presents it to poll for the reply, and only
    the hash is stored, so a database leak does not let anyone read the queue.
    Storing the hash rather than the token follows the same rule as AuthToken.
    """

    __tablename__ = "questions"

    STATUS_NEW = "new"
    STATUS_ANSWERED = "answered"
    STATUSES = (STATUS_NEW, STATUS_ANSWERED)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt: Mapped[str] = mapped_column(String(500), default="")
    reply: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default=STATUS_NEW, index=True)
    # Set only when the sender was signed in, so the admin can tell one reader
    # from another. Null rather than a fake row for anonymous senders.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str] = mapped_column(String(254), default="")
    # Which page the question came from, which is usually the page that explains
    # the problem. Truncated rather than trusted whole.
    page_url: Mapped[str] = mapped_column(String(400), default="")
    # Hashed, exactly like comments and feedback, so the row carries no plain IP.
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Which admin session answered, matching Comment.moderated_by.
    replied_by: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    @property
    def is_answered(self) -> bool:
        return self.status == self.STATUS_ANSWERED

    def to_dict(self) -> dict:
        """Admin-facing shape. The token is deliberately absent."""
        return {
            "id": self.id,
            "prompt": self.prompt,
            "reply": self.reply,
            "status": self.status,
            "email": self.email,
            "page_url": self.page_url,
            "created_at": self.created_at,
            "replied_at": self.replied_at,
        }


class AdSettings(Base):
    """Site-wide advertising switch and the values every unit needs.

    Ad markup is never stored as HTML. Storing validated settings in a row and
    generating the tags at render time means an admin session can inject nothing
    beyond the one fixed AdSense snippet.
    """

    __tablename__ = "ad_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # The Google publisher id is the only thing that ties this site to AdSense.
    # Kept here so rotating it does not require touching any unit.
    publisher_id: Mapped[str] = mapped_column(String(50), default="")
    auto_ads: Mapped[bool] = mapped_column(Boolean, default=False)
    # The ads.txt file declares who may sell this site's ad inventory. Edited
    # here, served verbatim at /ads.txt.
    ads_txt: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdUnit(Base):
    """One ad placement.

    Only structured fields are stored. The markup is rendered by
    services/ads.py from these values; an admin never supplies HTML.
    """

    __tablename__ = "ad_units"

    # The enums the admin form offers and the save route accepts. An unknown
    # value cannot be stored because the save path rejects it.
    FORMATS = ("auto", "responsive", "in-article", "in-feed", "display")
    PLACEMENTS = ("header", "sidebar", "above-content", "below-content", "inside-content", "footer")
    SHOW_ON = ("all", "homepage", "articles", "selected")
    DEVICES = ("both", "desktop", "mobile")

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    slot_id: Mapped[str] = mapped_column(String(30), default="", index=True)
    format: Mapped[str] = mapped_column(String(20), default="auto")
    placement: Mapped[str] = mapped_column(String(30), default="below-content")
    # Where inside the article body the unit goes. Meaningful only when
    # placement is "inside-content"; ignored otherwise.
    nth_paragraph: Mapped[int] = mapped_column(Integer, default=2)
    # AdSense only renders in-article and in-feed units when this matches the
    # key the publisher got when creating that unit in the AdSense console.
    layout_key: Mapped[str] = mapped_column(String(50), default="")
    show_on: Mapped[str] = mapped_column(String(20), default="all")
    # The comma-separated paths when show_on is "selected". Stored as one
    # string rather than a join table because it is read whole and is never
    # queried on.
    selected_paths: Mapped[str] = mapped_column(String(500), default="")
    device: Mapped[str] = mapped_column(String(10), default="both")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    @property
    def paths(self) -> list[str]:
        return [p.strip() for p in self.selected_paths.split(",") if p.strip()]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "slot_id": self.slot_id,
            "format": self.format,
            "placement": self.placement,
            "nth_paragraph": self.nth_paragraph,
            "layout_key": self.layout_key,
            "show_on": self.show_on,
            "selected_paths": self.selected_paths,
            "device": self.device,
            "enabled": self.enabled,
        }


class AppDownload(Base):
    """An uploaded application binary available for download.

    The file itself lives on disk in the apps directory; this table holds its
    metadata and the checksum recorded at upload time. The stored filename is
    derived from the slug rather than from whatever the browser sent, so this
    column is always a plain filename inside that one directory.
    """

    __tablename__ = "app_downloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # Recorded when the file is uploaded. Recomputed on download so that
    # tampering on disk is reported instead of silently served.
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    version: Mapped[str] = mapped_column(String(40), default="")
    vendor: Mapped[str] = mapped_column(String(120), default="")
    vendor_url: Mapped[str] = mapped_column(String(400), default="")
    # Why someone would want this tool, so a visitor can decide before
    # downloading rather than after.
    purpose: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), index=True, default="hardware")
    # Optional screenshot, stored beside the binary as <slug>-shot.<ext>. Empty
    # means the tool has no image, which the index renders as a placeholder
    # rather than a broken image.
    screenshot_filename: Mapped[str] = mapped_column(String(160), default="")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    @property
    def suffix(self) -> str:
        return self.filename.rsplit(".", 1)[-1].lower() if "." in self.filename else ""

    @property
    def size_display(self) -> str:
        from .services.apps import format_size

        return format_size(self.size_bytes)

    @property
    def hash_display(self) -> str:
        return (self.sha256 or "")[:16]

    @property
    def has_screenshot(self) -> bool:
        """True when a screenshot was recorded. Does not touch the disk, so a
        file that went missing still reports as present here; the route that
        serves it returns 404 in that case."""
        return bool(self.screenshot_filename)

    def integrity_ok(self) -> bool | None:
        """Compare the recorded checksum against the stored file.

        Returns True when they match, False when they do not, and None when
        the file is missing or unreadable. Callers treat None as an error too:
        an app whose file has gone is not a working download.

        Asked of the storage backend rather than the filesystem, because on a
        serverless host there is no filesystem to ask. For remote storage the
        digest comes back as upload metadata, so this stays a small request
        instead of pulling a 50 MB installer through the function to draw a page.
        """
        from .services import storage

        if not self.filename or not self.sha256:
            return None
        try:
            found = storage.backend().stat(self.filename)
        except storage.StorageError:
            return None
        if not found:
            return None
        current = found.get("sha256")
        if not current:
            return None
        return current == self.sha256

    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "summary": self.summary,
            "filename": self.filename,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "version": self.version,
            "vendor": self.vendor,
        }


class ArticleView(Base):
    """Per-day view counter so 'popular fixes' is stable and cheap."""

    __tablename__ = "article_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), index=True)
    view_date: Mapped[str] = mapped_column(String(10), index=True)
    views: Mapped[int] = mapped_column(Integer, default=0)

    article: Mapped[Article] = relationship()


class SeoOverride(Base):
    """Per-page meta overrides. Only the fields you care about need filling in.

    A row keyed by path replaces the generated <title> and meta description
    for that page. Empty strings fall back to the article or site defaults, so
    an edit never leaves a page with an empty <title>.
    """

    __tablename__ = "seo_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(String(400), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(250), default="")
    description: Mapped[str] = mapped_column(String(600), default="")
    og_image: Mapped[str] = mapped_column(String(600), default="")
    sitemap_priority: Mapped[str] = mapped_column(String(10), default="")
    sitemap_changefreq: Mapped[str] = mapped_column(String(20), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SiteSeoSettings(Base):
    """Site-wide SEO defaults. One row, edited from /admin/seo."""

    __tablename__ = "site_seo_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    default_changefreq: Mapped[str] = mapped_column(String(20), default="monthly")
    default_priority: Mapped[str] = mapped_column(String(10), default="0.5")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class EmailLog(Base):
    """One row per email the site tried to send. Records the outcome, not the
    message body, so no password-reset link or verification token ever lands in
    the admin log.
    """

    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_email: Mapped[str] = mapped_column(String(254), default="")
    subject: Mapped[str] = mapped_column(String(250), default="")
    sent_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class AdminAuditLog(Base):
    """A record of state-changing actions taken in the admin panel.

    There is exactly one admin account, so "who" is always the same person.
    What this table is actually for is *when* and *what*: if the panel is ever
    misused, or an admin session is stolen, the sequence of changes is the only
    way to find out what happened. Moderation rows used to record a hardcoded
    admin id of 1, which carried no information at all.

    Deliberately not a security log of reads. Only writes are recorded, because
    a row per page view would grow without bound and nobody would read it.
    """

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="", index=True)
    target_id: Mapped[str] = mapped_column(String(120), default="")
    # A short human summary of the change. Never the whole record and never
    # anything secret: no passwords, tokens or file bytes.
    detail: Mapped[str] = mapped_column(String(300), default="")
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    __table_args__ = (Index("ix_admin_audit_action_created", "action", "created_at"),)


class Announcement(Base):
    """A banner shown on every public page. Kept simple: one row, one banner."""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    link_url: Mapped[str] = mapped_column(String(600), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AdminTwoFactor(Base):
    """The admin's TOTP enrolment. One row, fixed id.

    This was data/admin_2fa.json, which is a file rather than a row for a reason
    that no longer holds: the secret only had to be readable by the process, and
    the file kept it out of the database. On a serverless host the filesystem is
    read-only and discarded on every deploy, so enrolment appeared to succeed and
    then stopped validating after the next cold start.

    A row is used instead, so the enrolment survives a deploy and is shared
    across every function instance, which is what an eight-hour session cookie
    signed by a stable secret key implies anyway.

    Recovery codes are stored hashed. They are single-use bearer credentials, so
    a readable copy would defeat the point; the secret is base32 rather than
    encrypted because the project has no crypto library, and a TOTP secret is a
    shared HMAC key rather than a password.
    """

    __tablename__ = "admin_two_factor"

    id: Mapped[int] = mapped_column(primary_key=True)
    secret: Mapped[str] = mapped_column(String(64), default="")
    recovery_hashes: Mapped[list] = mapped_column(JSON, default=list)
    enabled_at: Mapped[float] = mapped_column(default=0.0)

    # Only one admin account exists, so the row id is pinned rather than
    # autoincremented. It makes "the enrolment" a lookup that cannot be fanned
    # out into two competing secrets by a repeated enrolment.
    __table_args__ = ()
