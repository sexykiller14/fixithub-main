"""Markdown rendering with strict HTML sanitisation, TOC generation and callouts."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

# Tags allowed through from article markdown. Anything else is escaped.
ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "b", "i", "u", "s",
    "code", "pre", "blockquote", "a", "table", "thead", "tbody",
    "tr", "th", "td", "span", "div", "sup", "sub", "del", "kbd",
}

# Tags whose entire contents are discarded, not just the tag itself.
DROP_WITH_CONTENT = {
    "script", "style", "iframe", "object", "embed", "form",
    "svg", "math", "noscript", "template", "img", "video", "audio", "source",
}

ALLOWED_ATTRS = {
    "a": {"href", "title", "rel", "target"},
    "code": {"class"},
    "pre": {"class"},
    "span": {"class"},
    "div": {"class"},
    "p": {"class"},
    "h1": {"id"},
    "h2": {"id"},
    "h3": {"id"},
    "h4": {"id"},
    "h5": {"id"},
    "h6": {"id"},
    "th": {"align"},
    "td": {"align"},
}

URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
SAFE_SCHEMES = {"http", "https", "mailto"}

# `[!WARNING]`, `[!DANGER]`, `[!TIP]`, `[!NOTE]` blocks.
CALLOUT_RE = re.compile(
    r"^> \[!(WARNING|DANGER|TIP|NOTE|IMPORTANT)\]\s*$", re.MULTILINE
)
CALLOUT_STYLE = {
    "WARNING": ("warning", "Warning"),
    "DANGER": ("danger", "Danger"),
    "TIP": ("tip", "Tip"),
    "NOTE": ("note", "Note"),
    "IMPORTANT": ("important", "Important"),
}

CALLOUT_BLOCK_RE = re.compile(
    r"^> \[!(WARNING|DANGER|TIP|NOTE|IMPORTANT)\][ \t]*\n((?:^>.*\n?)+)", re.MULTILINE
)

_FENCE_RE = re.compile(r"^(```|~~~)([a-zA-Z0-9_+-]*)[ \t]*$")

_slug_space_re = re.compile(r"\s+")
_SLUG_EDGE_RE = re.compile(r"-{2,}")
_slug_unsafe_re = re.compile(r"[^a-z0-9\s-]", re.IGNORECASE)


def slugify(text: str) -> str:
    """Build a URL-safe anchor id from heading text.

    Separators other than whitespace or a hyphen become hyphens rather than
    being deleted, so "Fix: Step 1/2" reads as fix-step-1-2 rather than
    fix-step-12.
    """
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = text.lower().replace("_", " ")
    # Anything that is not a letter, digit or whitespace becomes a separator,
    # so punctuation never gets silently deleted and words never merge.
    text = _slug_unsafe_re.sub(" ", text)
    text = _slug_space_re.sub("-", text)
    text = _SLUG_EDGE_RE.sub("-", text)
    return text.strip("-") or "section"


def _strip_markdown(text: str) -> str:
    """Rough plain-text version of markdown, used for summaries and search."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_>]{1,3}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_summary(markdown: str, limit: int = 240) -> str:
    """First prose paragraph of the article, trimmed to a sensible length."""
    body = re.sub(r"^---.*?---\s*", "", markdown, flags=re.DOTALL)
    lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if not stripped:
            if lines:
                break
            continue
        if stripped.startswith(("#", ">", "|", "![", "<!--")):
            if lines:
                break
            continue
        if re.match(r"^[-*+]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            if lines:
                break
            continue
        lines.append(stripped)
    text = _strip_markdown(" ".join(lines))
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(".,;:") + "..."


def reading_time(markdown: str, words_per_minute: int = 200) -> int:
    """Estimate reading time in whole minutes, minimum 1."""
    words = len(_strip_markdown(markdown).split())
    return max(1, round(words / words_per_minute))


class Sanitizer:
    """Strict allowlist HTML sanitiser.

    This runs after markdown rendering so that even if raw HTML is present in a
    .md file, only known-safe tags, attributes and URL schemes survive.
    """

    def __init__(self) -> None:
        self._tag_re = re.compile(r"<\s*(/?)\s*([a-zA-Z][a-zA-Z0-9-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/?)\s*>")
        self._comment_re = re.compile(r"<!--.*?-->", re.DOTALL)

    def clean(self, markup: str) -> str:
        markup = self._comment_re.sub("", markup)
        # Drop dangerous elements along with everything they contain.
        for name in DROP_WITH_CONTENT:
            markup = re.sub(
                rf"<\s*{name}\b.*?<\s*/\s*{name}\s*>", "", markup, flags=re.DOTALL | re.I
            )
            markup = re.sub(rf"<\s*/?\s*{name}\b[^>]*>", "", markup, flags=re.I)

        out: list[str] = []
        pos = 0
        for match in self._tag_re.finditer(markup):
            out.append(markup[pos : match.start()])
            pos = match.end()
            closing, raw_name, attrs_raw, self_closing = match.groups()
            name = raw_name.lower()

            if name not in ALLOWED_TAGS:
                # Disallowed tags are escaped rather than emitted, so their
                # attributes can never become live markup.
                if not closing:
                    out.append(html.escape(match.group(0)))
                continue

            if closing:
                out.append(f"</{name}>")
                continue

            attrs = self._filter_attrs(name, attrs_raw)
            tag = f"<{name}{attrs}"
            if self_closing or name in {"br", "hr"}:
                out.append(tag + " />")
            else:
                out.append(tag + ">")
        out.append(markup[pos:])
        return "".join(out)

    def _filter_attrs(self, tag: str, attrs_raw: str) -> str:
        allowed = ALLOWED_ATTRS.get(tag, set())
        if not allowed or not attrs_raw.strip():
            return ""
        parts: list[str] = []
        for match in re.finditer(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+))?", attrs_raw):
            attr = match.group(1).lower()
            value = match.group(2)
            if attr not in allowed:
                continue
            if value is None:
                parts.append(f" {attr}")
                continue
            value = value.strip("\"'")
            if attr == "href":
                if not self._safe_url(value):
                    continue
                parts.append(f' href="{html.escape(value, quote=True)}"')
                # Outbound links open in a new tab without leaking the referrer.
                if URL_SCHEME_RE.match(value) and not value.lower().startswith("mailto:"):
                    parts.append(' target="_blank"')
                    parts.append(' rel="noopener noreferrer nofollow"')
                continue
            if attr == "class":
                # Keep only safe class name characters, preserving spaces.
                cleaned = " ".join(re.sub(r"[^a-zA-Z0-9_-]", " ", value).split())
                if cleaned:
                    parts.append(f' class="{html.escape(cleaned, quote=True)}"')
                continue
            parts.append(f' {attr}="{html.escape(value, quote=True)}"')
        return "".join(parts)

    @staticmethod
    def _safe_url(url: str) -> bool:
        candidate = url.strip()
        if not candidate:
            return False
        # Reject control characters and characters used to obscure schemes.
        if any(ord(ch) < 0x20 for ch in candidate):
            return False
        compact = re.sub(r"[\s\x00-\x20]", "", candidate)
        if compact.startswith("#") or compact.startswith("/"):
            return True
        match = URL_SCHEME_RE.match(compact)
        if not match:
            # Relative URL, which is safe.
            return True
        return match.group(0)[:-1].lower() in SAFE_SCHEMES


@dataclass
class TocEntry:
    id: str
    text: str
    level: int


@dataclass
class RenderedArticle:
    html: str = ""
    toc: list[TocEntry] = field(default_factory=list)
    summary: str = ""
    reading_time: int = 1
    plain_text: str = ""


def _convert_callouts(markdown: str) -> str:
    """Turn blockquote callouts into styled div blocks the sanitizer allows."""

    def replace(match: re.Match) -> str:
        kind = match.group(1).upper()
        body = match.group(2)
        css, label = CALLOUT_STYLE.get(kind, ("note", "Note"))
        lines = []
        for line in body.splitlines():
            line = re.sub(r"^\s*>\s?", "", line)
            lines.append(line)
        content = "\n".join(lines).strip()
        return (
            f'\n<div class="callout callout-{css}">\n'
            f'<p class="callout-title">{label}</p>\n'
            f"{content}\n"
            "</div>\n"
        )

    return CALLOUT_BLOCK_RE.sub(replace, markdown)


class ArticleRenderer:
    """Renders article markdown to sanitised HTML plus a table of contents."""

    def __init__(self) -> None:
        # html=True lets our own callout <div>s through markdown-it so the
        # sanitizer can style them. Raw HTML in a .md file still has to pass the
        # allowlist below, so scripts and event handlers never survive.
        self._md = MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
        self._md.enable(["table", "strikethrough"])
        self._sanitizer = Sanitizer()

    def render(self, markdown: str, extract_toc: bool = True) -> RenderedArticle:
        prepared = self._prepare(markdown)
        tokens = self._md.parse(prepared)
        if extract_toc:
            self._apply_heading_ids(tokens)
        rendered = self._md.renderer.render(tokens, self._md.options, {})  # noqa: S308
        cleaned = self._sanitizer.clean(rendered)
        return RenderedArticle(
            html=cleaned,
            toc=self._collect_toc(tokens) if extract_toc else [],
            summary=extract_summary(markdown),
            reading_time=reading_time(markdown),
            plain_text=_strip_markdown(markdown),
        )

    def _prepare(self, markdown: str) -> str:
        """Convert custom block syntax into markdown-it friendly HTML."""
        text = markdown.replace("\r\n", "\n").replace("\r", "\n")
        text = _convert_callouts(text)
        return text

    def _apply_heading_ids(self, tokens) -> None:
        """Give every h2 and h3 a stable anchor id for the table of contents."""
        used: dict[str, int] = {}
        for index, token in enumerate(tokens):
            if token.type != "heading_open":
                continue
            if token.tag not in {"h2", "h3"}:
                continue
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            text = inline.content if inline is not None else token.content
            base = slugify(text)
            count = used.get(base, 0)
            used[base] = count + 1
            anchor = base if count == 0 else f"{base}-{count}"
            token.attrSet("id", anchor)

    def _collect_toc(self, tokens) -> list[TocEntry]:
        entries: list[TocEntry] = []
        for index, token in enumerate(tokens):
            if token.type != "heading_open" or token.tag not in {"h2", "h3"}:
                continue
            inline = tokens[index + 1] if index + 1 < len(tokens) else None
            text = _strip_markdown(inline.content if inline is not None else token.content)
            anchor = token.attrGet("id")
            if anchor:
                entries.append(TocEntry(id=anchor, text=text, level=3 if token.tag == "h3" else 2))
        return entries

    @staticmethod
    def render_inline(text: str) -> str:
        """Render a short markdown string for inline hints."""
        md = MarkdownIt("commonmark", {"html": True, "linkify": False})
        return Sanitizer().clean(md.render(text))


renderer = ArticleRenderer()


def render(markdown: str) -> RenderedArticle:
    """Render markdown to sanitised HTML with a table of contents."""
    return renderer.render(markdown)
