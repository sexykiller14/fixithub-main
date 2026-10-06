"""Loading markdown articles from /content with YAML frontmatter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..config import CONTENT_DIR, CATEGORIES
from .markdown import RenderedArticle, renderer

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)

DEFAULT_OS = "Windows 10/11"


@dataclass
class ArticleSource:
    """A parsed markdown file from /content before it hits the database."""

    slug: str
    title: str
    category: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    difficulty: str = "easy"
    os_version: str = DEFAULT_OS
    featured: bool = False
    draft: bool = False
    body: str = ""
    source_path: str = ""


def slug_from_filename(path: Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split YAML frontmatter from the markdown body."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, text[match.end() :]


def _as_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[,;]", value)]
    elif isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value]
    else:
        parts = [str(value).strip()]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return seen


def load_article_file(path: Path) -> ArticleSource | None:
    """Read one .md file. Returns None if it cannot be parsed at all."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    meta, body = parse_frontmatter(text)
    slug = str(meta.get("slug") or slug_from_filename(path))

    title = str(meta.get("title") or slug.replace("-", " ").title())
    category = str(meta.get("category") or "windows").strip().lower()
    if category not in CATEGORIES:
        category = "windows"

    difficulty = str(meta.get("difficulty") or "easy").strip().lower()
    if difficulty not in {"easy", "moderate", "hard", "advanced"}:
        difficulty = "easy"

    rendered = renderer.render(body)
    summary = str(meta.get("summary") or "").strip() or rendered.summary

    return ArticleSource(
        slug=slug,
        title=title,
        category=category,
        summary=summary,
        tags=_as_tags(meta.get("tags")),
        difficulty=difficulty,
        os_version=str(meta.get("os_version") or DEFAULT_OS),
        featured=bool(meta.get("featured", False)),
        draft=bool(meta.get("draft", False)),
        body=body,
        source_path=str(path.relative_to(CONTENT_DIR.parent)).replace("\\", "/"),
    )


def load_all_articles(directory: Path | None = None) -> list[ArticleSource]:
    """Load every markdown article under the content directory."""
    root = directory or CONTENT_DIR
    if not root.exists():
        return []
    articles: list[ArticleSource] = []
    for path in sorted(root.rglob("*.md")):
        if path.name.lower().startswith("_"):
            continue
        article = load_article_file(path)
        if article is not None:
            articles.append(article)
    return articles


def render_article(body: str) -> RenderedArticle:
    """Render markdown to sanitised HTML with a table of contents."""
    return renderer.render(body)


def parse_date(value) -> datetime:
    """Parse a frontmatter date, defaulting to now."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(timezone.utc)


def related_by_tags(article: ArticleSource, pool: list[ArticleSource], limit: int = 4) -> list[ArticleSource]:
    """Rank other articles by shared tags, then category, then featured."""
    article_tags = {t.lower() for t in article.tags}
    scored: list[tuple[int, int, ArticleSource]] = []
    for other in pool:
        if other.slug == article.slug:
            continue
        score = 0
        shared = len(article_tags & {t.lower() for t in other.tags})
        score += shared * 3
        if other.category == article.category:
            score += 2
        if shared == 0 and other.category != article.category:
            continue
        if other.featured:
            score += 1
        scored.append((score, -other.title.lower().count("a"), other))
    scored.sort(key=lambda item: (-item[0], item[2].title.lower()))
    return [item[2] for item in scored[:limit]]
