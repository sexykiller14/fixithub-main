"""Search over articles and stop codes, with query logging."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from sqlalchemy import Integer, func, select
from sqlalchemy.orm import Session

from ..models import Article, Feedback, SearchQuery, StopCode
from .ssrf import validate_search_query

STOP_CODE_HINT_RE = re.compile(r"(?i)\b(?:0x)?([0-9a-f]{2,8})\b")


def normalised_term(raw: str) -> str:
    """Casefold and strip accents so 'Drucker' matches 'drucker'."""
    text = unicodedata.normalize("NFKD", (raw or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def hash_ip(ip: str) -> str:
    """One-way hash of a client IP, so feedback can be deduped without storing it."""
    return hashlib.sha256(f"fixithub:{ip}".encode("utf-8")).hexdigest()[:32]


def search_articles(db: Session, term: str, category: str | None = None, limit: int = 20) -> tuple[list[Article], int]:
    """Search articles. Returns (results, total matches before the limit)."""
    from ..db import search as fts_search

    try:
        query = validate_search_query(term)
    except ValueError:
        return [], 0
    if len(query) < 2:
        return [], 0

    rows = fts_search.query(query, limit=limit * 3, category=category)
    if not rows:
        return [], 0

    ids = [row[0] for row in rows]
    articles = list(db.execute(select(Article).where(Article.id.in_(ids))).scalars())
    order = {article_id: index for index, article_id in enumerate(ids)}
    articles.sort(key=lambda a: order.get(a.id, 999))

    if category:
        articles = [a for a in articles if a.category == category]

    # Broaden if the FTS pass was too strict to find anything useful.
    if not articles:
        like = f"%{query.lower()}%"
        articles = list(
            db.execute(
                select(Article)
                .where(
                    func.lower(Article.title).like(like)
                    | func.lower(Article.summary).like(like)
                    | func.lower(Article.body).like(like)
                )
                .order_by(Article.is_featured.desc(), Article.view_count.desc())
                .limit(limit)
            ).scalars()
        )

    return articles[:limit], len(rows)


def search_stop_codes(db: Session, term: str, limit: int = 10) -> list[StopCode]:
    """Fuzzy search stop codes by name or hex, for the search page."""
    from .stopcodes import lookup, search

    raw = (term or "").strip()
    if len(raw) < 2:
        return []

    exact = lookup(db, raw)
    if exact is not None:
        return [exact]

    results = search(db, raw, limit=limit)
    if results:
        return results

    pattern = f"%{normalised_term(raw).upper()}%"
    return list(
        db.execute(
            select(StopCode)
            .where(
                func.upper(StopCode.name).like(pattern)
                | func.upper(StopCode.code_hex).like(pattern)
                | StopCode.meaning.ilike(f"%{raw}%")
            )
            .order_by(StopCode.code_uint)
            .limit(limit)
        ).scalars()
    )


def combined_search(db: Session, term: str, limit: int = 20) -> dict:
    """Search both content types and record the query for the admin dashboard."""
    try:
        query = validate_search_query(term)
    except ValueError:
        return {"query": term, "articles": [], "stop_codes": [], "total": 0}

    articles, total = search_articles(db, query, limit=limit)
    stop_codes = search_stop_codes(db, query, limit=8)
    record_search(db, query, len(articles) + len(stop_codes))
    return {
        "query": query,
        "articles": articles,
        "stop_codes": stop_codes,
        "total": len(articles) + len(stop_codes),
    }


def record_search(db: Session, term: str, result_count: int) -> None:
    """Upsert a search query row for the admin popular-search list."""
    clean = normalised_term(term)
    if len(clean) < 2:
        return
    clean = clean[:240]
    existing = db.scalar(select(SearchQuery).where(SearchQuery.normalised == clean))
    if existing is None:
        db.add(
            SearchQuery(
                query=term.strip()[:250],
                normalised=clean,
                result_count=result_count,
                hits=1,
            )
        )
    else:
        existing.hits += 1
        existing.query = term.strip()[:250]
        existing.result_count = result_count
    db.commit()


def popular_searches(db: Session, limit: int = 20) -> list[SearchQuery]:
    return list(
        db.execute(
            select(SearchQuery).order_by(SearchQuery.hits.desc(), SearchQuery.last_seen_at.desc()).limit(limit)
        ).scalars()
    )


def zero_result_searches(db: Session, limit: int = 10) -> list[SearchQuery]:
    """Queries that returned nothing, which show us what content is missing."""
    return list(
        db.execute(
            select(SearchQuery)
            .where(SearchQuery.result_count == 0)
            .order_by(SearchQuery.hits.desc())
            .limit(limit)
        ).scalars()
    )


def record_feedback(
    db: Session,
    target_type: str,
    target_id: int,
    helpful: bool,
    comment: str = "",
    ip: str = "",
) -> Feedback:
    """Store one helpful/not helpful vote, one per IP per target."""
    kind = target_type if target_type in {"article", "stop_code"} else "article"
    ip_hash = hash_ip(ip) if ip else ""

    if kind == "article" and target_id:
        article = db.get(Article, target_id)
        if article is not None:
            already = db.scalar(
                select(Feedback).where(
                    Feedback.target_type == "article",
                    Feedback.target_id == target_id,
                    Feedback.ip_hash == ip_hash,
                )
            )
            if already is not None:
                already.helpful = helpful
                already.comment = comment[:500]
                if helpful:
                    article.helpful_yes += 1
                else:
                    article.helpful_no += 1
                db.commit()
                return already
            if helpful:
                article.helpful_yes += 1
            else:
                article.helpful_no += 1

    feedback = Feedback(
        target_type=kind,
        target_id=target_id,
        helpful=helpful,
        comment=comment[:500],
        ip_hash=ip_hash,
    )
    db.add(feedback)
    db.commit()
    return feedback


def feedback_summary(db: Session) -> dict:
    """Aggregate feedback numbers for the admin dashboard."""
    article_votes = db.execute(
        select(
            func.count(Feedback.id),
            func.sum(func.cast(Feedback.helpful, Integer)),
        ).where(Feedback.target_type == "article")
    ).one()
    total_articles = article_votes[0] or 0
    positive = int(article_votes[1] or 0)
    return {
        "total_votes": total_articles,
        "positive": positive,
        "negative": max(0, total_articles - positive),
        "percent": int(round(positive / total_articles * 100)) if total_articles else 0,
    }


def recent_feedback(db: Session, limit: int = 25) -> list[Feedback]:
    return list(
        db.execute(
            select(Feedback).order_by(Feedback.created_at.desc()).limit(limit)
        ).scalars()
    )
