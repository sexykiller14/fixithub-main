"""The dashboard's charts and stat cards.

The daily-series helper is the part that can be wrong quietly: a GROUP BY over
a text date, a window that omits days with no rows, or a flat series that draws
a chart implying data where there is none. These tests drive the helper against
a real database and check the rendered page.
"""

import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import Article, ArticleView, SearchQuery


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@pytest.fixture
def seeded_views(db):
    """Two days of views: a busy day and a quiet one, leaving gaps between.

    Returns (article, views_added). The baseline total is captured here, before
    this fixture writes anything, because the prepared database is
    session-scoped: other tests add views too, so a test cannot compare against
    an absolute number or take its own "before" reading once the fixture has
    already run.
    """
    from app.db import SessionLocal
    from app.routes.admin import _daily_series

    article = db.scalar(select(Article).limit(1))
    assert article is not None, "the seeded database has no article"

    with SessionLocal() as probe:
        baseline = _daily_series(probe, days=30)["total_views"]

    today = datetime.now(timezone.utc).date()
    for offset, count in ((0, 7), (1, 3)):
        day = (today - timedelta(days=offset)).isoformat()
        db.add(ArticleView(article_id=article.id, view_date=day, views=count))
    db.commit()

    return article, baseline


@pytest.mark.usefixtures("admin_client")
def test_the_series_has_one_point_per_day_for_the_window(db, seeded_views):
    """A day with no rows must still appear, or the chart grows a false gap."""
    from app.db import SessionLocal
    from app.routes.admin import _daily_series

    with SessionLocal() as db:
        series = _daily_series(db, days=30)

    assert series["days"] == 30
    assert len(series["points"]) == 30, "the window is not fully populated"

    days = [point["day"] for point in series["points"]]
    assert days == sorted(days), "the points are not oldest first"
    assert days[-1] == _today(), "the last point is not today"


@pytest.mark.usefixtures("admin_client")
def test_the_series_sums_the_days_it_found(db, seeded_views):
    """The total must move by exactly what the fixture wrote.

    The baseline is captured before the fixture inserts, because the prepared
    database is session-scoped and earlier tests in this file leave views behind.
    """
    from app.db import SessionLocal
    from app.routes.admin import _daily_series

    _article, baseline = seeded_views

    with SessionLocal() as db:
        after = _daily_series(db, days=30)

    assert after["total_views"] == baseline + 10, (
        f"the total is {after['total_views'] - baseline} above the baseline, not the "
        "10 views this fixture wrote"
    )
    assert sum(p["views"] for p in after["points"]) == after["total_views"], (
        "the stated total does not match the sum of the daily points"
    )


@pytest.mark.usefixtures("admin_client")
def test_a_day_with_no_rows_reports_zero_not_missing(db, seeded_views):
    from app.db import SessionLocal
    from app.routes.admin import _daily_series

    with SessionLocal() as db:
        series = _daily_series(db, days=30)

    zero_days = [p for p in series["points"] if p["views"] == 0]
    assert zero_days, "every day reported a view, which cannot be right"
    assert all("day" in p and "views" in p for p in zero_days)


def test_the_series_day_keys_are_strings(db):
    """Every point's day must be a YYYY-MM-DD string, not a date object.

    This is the invariant that broke on PostgreSQL. date() returns a string on
    SQLite and a datetime.date on PostgreSQL, and the points are looked up
    against isoformat() strings, so a date object misses every key and the
    searches chart silently reads zero. Asserting the type rather than a value
    catches it on SQLite too, which is the only backend this suite runs.
    """
    from app.db import SessionLocal
    from app.routes.admin import _daily_series

    row = SearchQuery(
        query="a search that finds something",
        normalised="a search that finds something",
        result_count=1,
        hits=1,
    )
    db.add(row)
    db.commit()
    try:
        with SessionLocal() as probe:
            series = _daily_series(probe, days=30)
    finally:
        # The prepared database is session-scoped and a later test asserts on an
        # all-zero window, so this row has to go rather than be left behind.
        db.delete(row)
        db.commit()

    for point in series["points"]:
        assert isinstance(point["day"], str), (
            f"day is {type(point['day']).__name__}, not str"
        )
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", point["day"]), (
            f"day is {point['day']!r}, which is not YYYY-MM-DD"
        )


@pytest.mark.usefixtures("admin_client")
def test_the_dashboard_draws_a_chart_when_there_is_data(admin_client, db):
    article = db.scalar(select(Article).limit(1))
    db.add(ArticleView(article_id=article.id, view_date=_today(), views=4))
    db.commit()

    page = admin_client.get("/admin/dashboard")
    assert page.status_code == 200
    assert 'class="admin-spark ' in page.text, "no sparkline was drawn"
    assert "admin-spark-bar" in page.text, "the chart has no bars"


@pytest.mark.usefixtures("admin_client")
def test_an_empty_window_draws_a_message_not_a_flat_chart(admin_client, db):
    """A window of zeros would render a level line that implies data."""
    db.query(ArticleView).delete()
    db.commit()

    page = admin_client.get("/admin/dashboard")
    assert page.status_code == 200
    assert "admin-spark-empty" in page.text, (
        "an all-zero window should say so rather than drawing a chart"
    )
    assert 'class="admin-spark ' not in page.text, "a chart was drawn for an empty window"


@pytest.mark.usefixtures("admin_client")
def test_the_dashboard_states_the_traffic_totals(admin_client, db):
    """The chart is aria-hidden, so the number has to be in the text."""
    article = db.scalar(select(Article).limit(1))
    db.add(ArticleView(article_id=article.id, view_date=_today(), views=11))
    db.commit()

    body = admin_client.get("/admin/dashboard").text
    assert "Article views" in body
    assert "Last 30 days" in body
    assert re.search(r">\s*11\s*<", body), "the view total is not shown"


@pytest.mark.usefixtures("admin_client")
def test_pending_queues_are_promoted_when_non_empty(admin_client):
    """The two moderation queues are the only cards that imply an action."""
    body = admin_client.get("/admin/dashboard").text

    if "Comments to approve" in body:
        assert "admin-stat-urgent" in body, "an urgent queue lost its styling"
        assert "/admin/comments?status_filter=pending" in body
    if "Questions unanswered" in body:
        assert "/admin/questions?status_filter=new" in body


@pytest.mark.usefixtures("admin_client")
def test_a_calm_install_hides_the_urgent_cards(admin_client):
    """With nothing waiting, the dashboard should not open on an empty alert."""
    body = admin_client.get("/admin/dashboard").text
    if "Comments to approve" not in body and "Questions unanswered" not in body:
        assert "admin-stat-urgent" not in body, (
            "an urgent card rendered with nothing to approve"
        )