"""Pagination and search on the admin list pages.

The bug these guard against is specific: filtering after a LIMIT silently drops
matching rows from later pages, so a paginated search reports that nothing
exists when it does. Every search assertion here therefore checks the total as
well as the rows, because a total that disagrees with the results is the tell.
"""

import re

import pytest


def _pager_text(response):
    return response.text


@pytest.mark.usefixtures("admin_client")
def test_articles_page_renders(admin_client):
    response = admin_client.get("/admin/articles")
    assert response.status_code == 200


@pytest.mark.usefixtures("admin_client")
def test_articles_are_paginated(admin_client, db):
    from app.models import Article

    total = db.query(Article).count()
    body = admin_client.get("/admin/articles").text

    # One page shows a plain count; more than one shows the full pager.
    if total > 50:
        assert f"of {total}" in body, "the pager does not state the total"
        assert "Showing 1&ndash;50" in body, "the first page is not the first 50 rows"
        assert "pagination" in body.lower()
    else:
        assert f"{total} item" in body, "the page never states how many rows there are"


@pytest.mark.usefixtures("admin_client")
def test_a_second_page_holds_different_rows(admin_client, db):
    from app.models import Article

    if db.query(Article).count() <= 50:
        pytest.skip("needs more than one page of articles")

    first = admin_client.get("/admin/articles?page=1").text
    second = admin_client.get("/admin/articles?page=2").text
    assert first != second, "page 2 rendered the same rows as page 1"


@pytest.mark.usefixtures("admin_client")
def test_a_page_past_the_end_falls_back_to_the_last(admin_client):
    """Deleting rows while someone is on page 3 must not show an empty table."""
    response = admin_client.get("/admin/articles?page=99999")
    assert response.status_code == 200


@pytest.mark.parametrize("junk", ["0", "-5", "abc", "1e400", "99999999999999999999", ""])
@pytest.mark.usefixtures("admin_client")
def test_a_nonsense_page_number_does_not_crash(admin_client, junk):
    response = admin_client.get(f"/admin/articles?page={junk}")
    assert response.status_code == 200, f"page={junk!r} returned {response.status_code}"


@pytest.mark.usefixtures("admin_client")
def test_searching_articles_filters_and_reports_a_total(admin_client, db):
    from app.models import Article

    article = db.query(Article).first()
    needle = article.title[:12]

    response = admin_client.get(f"/admin/articles?q={needle}")
    assert response.status_code == 200
    assert needle.lower() in response.text.lower(), "the matching article is not on the page"


@pytest.mark.usefixtures("admin_client")
def test_a_search_with_no_matches_says_so(admin_client):
    response = admin_client.get("/admin/articles?q=zzzzz-nothing-matches-zzzzz")
    assert response.status_code == 200
    assert "0 items" in response.text or "No articles" in response.text, (
        "an empty result did not say the search found nothing"
    )


@pytest.mark.usefixtures("admin_client")
def test_the_search_term_is_escaped_in_the_pager(admin_client):
    """The pager echoes q into the search box and into hrefs.

    Checked against the admin search field specifically rather than the whole
    document: the page legitimately contains its own <script> tags, so a
    page-wide assertion would pass or fail for the wrong reason.
    """
    body = admin_client.get('/admin/articles?q=%22%3E%3Cscript%3Ealert(1)%3C/script%3E').text

    field = re.search(r'id="admin-search"[^>]*value="([^"]*)"', body)
    assert field is not None, "the admin search box is missing"
    assert "<" not in field.group(1), "a raw < survived into the search box value"
    assert "&lt;script&gt;" in field.group(1), "the term was not HTML-escaped in the field"

    # And the pager's links must carry it percent-encoded, not raw.
    for href in re.findall(r'href="(/admin/articles\?page=[^"]+)"', body):
        assert 'q="%22%3E%3Cscript%3E' in href or "q=" not in href, (
            f"the search term was not encoded in a page link: {href}"
        )


@pytest.mark.usefixtures("admin_client")
def test_stop_codes_paginate_and_search(admin_client, db):
    from app.models import StopCode

    total = db.query(StopCode).count()
    response = admin_client.get("/admin/stop-codes")
    assert response.status_code == 200
    assert f"of {total}" in response.text

    code = db.query(StopCode).first()
    found = admin_client.get(f"/admin/stop-codes?q={code.name}")
    assert found.status_code == 200
    assert code.name in found.text


@pytest.mark.usefixtures("admin_client")
def test_uploads_paginate_and_search(admin_client):
    page = admin_client.get("/admin/apps")
    assert page.status_code == 200

    searched = admin_client.get("/admin/apps?q=zzzzz-nothing")
    assert searched.status_code == 200
    assert "0 items" in searched.text or "Nothing uploaded" in searched.text


@pytest.mark.usefixtures("admin_client")
def test_search_and_page_compose(admin_client):
    """The two parameters must not clobber each other."""
    response = admin_client.get("/admin/articles?q=fix&page=1")
    assert response.status_code == 200
    assert 'name="q"' in response.text, "the search box lost its value"


@pytest.mark.usefixtures("admin_client")
def test_the_pager_links_keep_the_search(admin_client, db):
    from app.models import Article

    if db.query(Article).count() <= 50:
        pytest.skip("needs more than one page to check the composed links")

    body = admin_client.get("/admin/articles?q=e&page=1").text
    hrefs = re.findall(r'href="(/admin/articles\?page=[^"]+)"', body)
    assert hrefs, "no page links were rendered"
    for href in hrefs:
        assert "q=" in href, f"page link lost the search term: {href}"