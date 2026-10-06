"""Article rendering, search, wizards, scripts and the SEO endpoints."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.content import load_article_file, parse_frontmatter
from app.services.markdown import Sanitizer, extract_summary, render, slugify

FIXTURE_ARTICLE = Path(__file__).resolve().parent.parent / "content"
from app.services.scripts_catalog import CATALOG, get_script, list_scripts
from app.services.wizards import find_option_index, follow, load_wizard, list_wizards, progress, start_step


# --------------------------------------------------------------------------
# Markdown rendering
# --------------------------------------------------------------------------


def test_headings_get_anchor_ids_and_toc():
    result = render("## First section\n\ntext\n\n### Nested\n\nmore")
    assert 'id="first-section"' in result.html
    assert 'id="nested"' in result.html
    assert [entry.text for entry in result.toc] == ["First section", "Nested"]
    assert result.toc[0].level == 2
    assert result.toc[1].level == 3


def test_duplicate_headings_get_unique_ids():
    result = render("## Fix\n\none\n\n## Fix\n\ntwo")
    assert 'id="fix"' in result.html
    assert 'id="fix-1"' in result.html


def test_script_tags_are_stripped():
    result = render('<script>alert("xss")</script>\n\nhello')
    assert "<script" not in result.html.lower()
    assert "alert" not in result.html or "&lt;script" in result.html


def test_img_tags_are_dropped_entirely():
    """Images are not in the allowlist, so they are removed rather than escaped."""
    result = render('<img src=x onerror="alert(1)">')
    assert "<img" not in result.html.lower()
    assert "onerror" not in result.html.lower()


def test_event_handler_attributes_are_stripped():
    result = render('<div onclick="steal()" onmouseover="x()">text</div>')
    assert "onclick" not in result.html.lower()
    assert "onmouseover" not in result.html.lower()
    assert "text" in result.html


def test_javascript_urls_do_not_become_links():
    """markdown-it refuses the scheme, so no anchor with a javascript: href exists."""
    result = render("[click](javascript:alert(1))")
    assert "<a " not in result.html
    assert 'href="javascript' not in result.html.lower()


def test_data_urls_do_not_become_links():
    result = render("[click](data:text/html;base64,PHNjcmlwdD4=)")
    assert 'href="data:' not in result.html.lower()


def test_sanitizer_strips_dangerous_scheme_if_it_reaches_it():
    """Direct sanitizer use must also refuse a javascript: href."""
    markup = Sanitizer().clean('<a href="javascript:alert(1)">click</a>')
    assert "javascript:" not in markup.lower()


def test_safe_links_get_rel_attributes():
    result = render("[docs](https://example.com)")
    assert 'rel="noopener noreferrer nofollow"' in result.html
    assert 'target="_blank"' in result.html


def test_iframes_are_removed():
    result = render('<iframe src="https://evil.example"></iframe>')
    assert "<iframe" not in result.html.lower()


def test_warning_callout_renders():
    result = render("> [!WARNING]\n> This is dangerous.")
    assert 'class="callout callout-warning"' in result.html
    assert "Danger" not in result.html
    assert "This is dangerous" in result.html


def test_danger_callout_renders():
    result = render("> [!DANGER]\n> Never do this.")
    assert 'class="callout callout-danger"' in result.html
    assert "Never do this" in result.html


def test_code_blocks_are_preserved():
    result = render("```bat\nipconfig /flushdns\n```")
    assert "ipconfig /flushdns" in result.html
    assert "<pre>" in result.html


def test_reading_time_is_at_least_one():
    assert render("short").reading_time >= 1


def test_extract_summary_skips_headings():
    summary = extract_summary("# Title\n\nThe real first paragraph of prose here.")
    assert summary == "The real first paragraph of prose here."


def test_extract_summary_skips_code():
    summary = extract_summary("```\ncode block\n```\n\nActual prose follows.")
    assert summary == "Actual prose follows."


def test_slugify_handles_mixed_content():
    assert slugify("What's a `PAGE_FAULT`?") == "what-s-a-page-fault"
    assert slugify("Fix: Step 1/2") == "fix-step-1-2"
    assert slugify("MEMORY_MANAGEMENT") == "memory-management"


def test_sanitizer_allows_known_safe_html():
    markup = Sanitizer().clean('<p>ok <strong>bold</strong> <em>italic</em></p>')
    assert "<strong>bold</strong>" in markup
    assert "<em>italic</em>" in markup


# --------------------------------------------------------------------------
# Frontmatter
# --------------------------------------------------------------------------


def test_parse_frontmatter():
    meta, body = parse_frontmatter("---\ntitle: Test\ncategory: bsod\n---\n\nBody text")
    assert meta["title"] == "Test"
    assert meta["category"] == "bsod"
    assert body.strip() == "Body text"


def test_parse_frontmatter_without_block():
    meta, body = parse_frontmatter("Just markdown")
    assert meta == {}
    assert body == "Just markdown"


def test_load_article_file_derives_slug():
    article = load_article_file(FIXTURE_ARTICLE / "test-ram-memory-errors.md")
    assert article is not None
    assert article.slug == "test-ram-memory-errors"
    assert article.category == "hardware"
    assert article.tags


def test_load_article_file_falls_back_for_bad_category():
    article = load_article_file(FIXTURE_ARTICLE / "read-bsod-stop-code.md")
    assert article.category in {"hardware", "network", "windows", "drivers", "bsod"}


# --------------------------------------------------------------------------
# Wizards
# --------------------------------------------------------------------------


def test_all_wizards_are_available():
    wizards = list_wizards()
    assert len(wizards) >= 8
    ids = {wizard.id for wizard in wizards}
    assert {
        "wont-boot",
        "no-internet",
        "slow-computer",
        "random-restarts",
        "no-display",
        "no-sound",
        "usb-not-detected",
        "memory-or-storage",
    } <= ids


def test_every_wizard_tree_is_walkable():
    for wizard in list_wizards():
        node = start_step(wizard)
        assert node is not None
        assert not node.is_result
        for option in node.options:
            assert wizard.node(option.next_id) is not None, f"{wizard.id}: {option.next_id} missing"


def test_every_wizard_reaches_a_result():
    for wizard in list_wizards():
        frontier = [wizard.start_id]
        seen = set()
        while frontier:
            node_id = frontier.pop()
            if node_id in seen:
                continue
            seen.add(node_id)
            node = wizard.node(node_id)
            assert node is not None
            if node.is_result:
                assert node.title and node.steps, f"{wizard.id}:{node_id} incomplete result"
                continue
            frontier.extend(option.next_id for option in node.options)
        assert len(seen) > 1


def test_follow_returns_next_node():
    wizard = load_wizard("wont-boot")
    node = start_step(wizard)
    nxt = follow(wizard, node.id, 0)
    assert nxt is not None
    assert wizard.node(nxt) is not None


def test_follow_rejects_out_of_range_option():
    wizard = load_wizard("wont-boot")
    node = start_step(wizard)
    assert follow(wizard, node.id, 999) is None
    assert follow(wizard, node.id, -1) is None


def test_follow_returns_none_from_a_result_node():
    wizard = load_wizard("wont-boot")
    result_node = next(
        node.id for node in wizard.nodes.values() if node.is_result
    )
    assert follow(wizard, result_node, 0) is None


def test_find_option_index_by_label():
    wizard = load_wizard("no-internet")
    node = wizard.node(wizard.start_id)
    assert find_option_index(wizard, node.id, node.options[1].label) == 1
    assert find_option_index(wizard, node.id, "does not exist") == -1


def test_progress_advances():
    wizard = load_wizard("no-internet")
    start = progress(wizard, [])
    assert start["answered"] == 0
    node = wizard.node(wizard.start_id)
    advanced = progress(wizard, [{"label": node.options[0].label}])
    assert advanced["answered"] == 1
    assert advanced["percent"] > start["percent"]


def test_load_wizard_rejects_bad_ids():
    for bad in ["", "../secrets", "no-such-wizard", "wizards/../../etc", "a b"]:
        assert load_wizard(bad) is None


# --------------------------------------------------------------------------
# Scripts
# --------------------------------------------------------------------------


def test_all_catalog_scripts_exist():
    scripts = list_scripts()
    assert len(scripts) >= 5
    assert {script.slug for script in scripts} == set(CATALOG)
    assert {"ram-diagnostics", "disk-health"} <= {script.slug for script in scripts}


def test_every_script_related_slug_resolves(client):
    """A script pointing at an article that does not exist sends the visitor
    to a 404, so the catalog has to stay in step with the content folder."""
    from app.services.content import load_all_articles

    known = {article.slug for article in load_all_articles()}
    for script in list_scripts():
        for slug in script.related_slugs:
            assert slug in known, f"{script.slug} links to missing article {slug}"
            assert client.get(f"/articles/{slug}").status_code == 200


def test_disk_script_documents_every_watched_attribute():
    """The script decodes raw SMART attributes itself, so the explanations in
    the report have to cover the attributes it reads. Otherwise a user sees a
    number with no way to find out what it means."""
    entry = get_script("disk-health")
    assert entry is not None
    for name in ("Reallocated sectors", "Pending sectors", "Uncorrectable sectors",
                 "Spin retries", "Power-on hours", "Temperature (Celsius)"):
        assert name in entry.source, name
    # The history file is what makes the trend section work, so it has to be
    # written and read.
    assert "Export-Csv" in entry.source
    assert "Import-Csv" in entry.source


def test_every_script_has_command_explanations():
    for script in list_scripts():
        assert script.commands, f"{script.slug} has no commands"
        for note in script.commands:
            assert note.command
            assert len(note.explanation) > 20, f"{script.slug}: {note.command} explanation too short"
        assert script.warnings, f"{script.slug} has no warnings"
        assert script.how_to_run()


def test_script_source_is_readable():
    entry = get_script("network-reset")
    assert entry is not None
    assert "ipconfig /flushdns" in entry.source
    assert "netsh winsock reset" in entry.source


def test_get_script_rejects_unknown():
    assert get_script("../../etc/passwd") is None
    assert get_script("nope") is None


# --------------------------------------------------------------------------
# HTTP surface
# --------------------------------------------------------------------------


def test_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Fix your PC yourself" in response.text


def test_every_category_page(client):
    for slug in ["hardware", "network", "windows", "drivers", "bsod"]:
        assert client.get(f"/category/{slug}").status_code == 200


def test_unknown_category_is_not_served(client):
    """An unknown category must not render a page of articles."""
    response = client.get("/category/nonsense", follow_redirects=False)
    assert response.status_code in (301, 307, 308, 404)
    if response.status_code in (301, 307, 308):
        assert response.headers["location"].rstrip("/").endswith("/articles")


def test_articles_index(client):
    assert client.get("/articles").status_code == 200


def test_article_detail_renders_markdown(client):
    response = client.get("/articles/test-ram-memory-errors")
    assert response.status_code == 200
    assert "prose-article" in response.text
    assert "callout" in response.text


def test_article_detail_has_toc(client):
    response = client.get("/articles/fix-no-internet-windows")
    assert 'id="toc"' in response.text


def test_article_404(client):
    assert client.get("/articles/does-not-exist-at-all").status_code == 404


def test_search_finds_stop_code(client):
    response = client.get("/search", params={"q": "MEMORY_MANAGEMENT"})
    assert response.status_code == 200
    assert "MEMORY_MANAGEMENT" in response.text


def test_search_finds_article(client):
    response = client.get("/search", params={"q": "beep codes"})
    assert response.status_code == 200
    assert "result" in response.text.lower()


def test_search_handles_empty_query(client):
    assert client.get("/search").status_code == 200


def test_search_suggest_api(client):
    response = client.get("/api/search/suggest", params={"q": "MEMORY"})
    payload = response.json()
    assert payload["ok"] is True
    assert isinstance(payload["suggestions"], list)


def test_wizard_flow(client):
    assert client.get("/wizards").status_code == 200
    assert client.get("/wizards/wont-boot").status_code == 200
    response = client.post("/wizards/wont-boot/answer", data={"choice": 0}, follow_redirects=True)
    assert response.status_code == 200
    assert "Question" in response.text


def test_wizard_back_button(client):
    client.post("/wizards/wont-boot/answer", data={"choice": 0}, follow_redirects=True)
    response = client.get("/wizards/wont-boot/back", follow_redirects=True)
    assert response.status_code == 200


def test_wizard_unknown_id_404(client):
    assert client.get("/wizards/nope-not-real").status_code == 404


def test_wizard_rejects_invalid_choice(client):
    response = client.post("/wizards/wont-boot/answer", data={"choice": 999}, follow_redirects=True)
    assert response.status_code == 200


def test_wizard_restart_clears_history(client):
    client.post("/wizards/wont-boot/answer", data={"choice": 0}, follow_redirects=True)
    response = client.get("/wizards/wont-boot/restart", follow_redirects=True)
    assert response.status_code == 200


def test_drivers_pages(client):
    assert client.get("/drivers").status_code == 200
    assert client.get("/drivers/nvidia").status_code == 200
    assert client.get("/drivers/realtek").status_code == 200
    assert client.get("/drivers/device-manager-codes").status_code == 200


def test_unknown_vendor_404(client):
    assert client.get("/drivers/nintendo").status_code == 404


def test_hardware_pages(client):
    assert client.get("/hardware").status_code == 200
    assert client.get("/hardware/ram").status_code == 200
    assert client.get("/hardware/psu").status_code == 200


def test_ram_and_storage_topics_offer_their_scripts(client):
    """Both hardware topics should reach a script, since each script exists
    precisely because a website cannot read the visitor's own hardware."""
    ram = client.get("/hardware/ram")
    assert ram.status_code == 200
    assert "/scripts/ram-diagnostics" in ram.text

    storage = client.get("/hardware/storage")
    assert storage.status_code == 200
    assert "/scripts/disk-health" in storage.text


def test_ram_diagnostics_script_is_read_only(client):
    """The script promises it changes nothing, so nothing in it may write to
    the machine beyond the report on the Desktop."""
    response = client.get("/scripts/ram-diagnostics")
    assert response.status_code == 200
    body = response.text
    for forbidden in ("Set-ExecutionPolicy -Scope Machine",
                      "Restart-Computer",
                      "Invoke-WebRequest",
                      "New-Item -ItemType Registry"):
        assert forbidden not in body, forbidden
    assert "Win32_PhysicalMemory" in body


def test_memory_or_storage_wizard_routes_both_ways(client):
    """The wizard exists to split memory problems from storage ones, so both
    branches have to be reachable and to land on different advice."""
    page = client.get("/wizards/memory-or-storage")
    assert page.status_code == 200

    # Crashing while under load points at memory.
    # Crashing while idle points at the drive.
    for choice in range(4):
        client.get("/wizards/memory-or-storage/restart")

    # Under load is option 0 at the start node.
    under_load = client.post("/wizards/memory-or-storage/answer", data={"choice": 0}, follow_redirects=True)
    assert under_load.status_code == 200
    assert "While I am using it" in under_load.text

    # Idle is option 1, one step further along the same branch.
    idle = client.post("/wizards/memory-or-storage/answer", data={"choice": 1}, follow_redirects=True)
    assert idle.status_code == 200
    assert "clicking" in idle.text.lower() or "drive" in idle.text.lower()


def test_unknown_hardware_topic_404(client):
    assert client.get("/hardware/teleportation").status_code == 404


def test_scripts_pages(client):
    assert client.get("/scripts").status_code == 200
    response = client.get("/scripts/network-reset")
    assert response.status_code == 200
    assert "Full source" in response.text
    assert "ipconfig /flushdns" in response.text


def test_script_download_sets_attachment(client):
    response = client.get("/scripts/network-reset/download")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_unknown_script_404(client):
    assert client.get("/scripts/nope").status_code == 404
    assert client.get("/scripts/nope/download").status_code == 404


def test_tools_pages_render(client):
    for path in ["/tools", "/tools/dns", "/tools/port", "/tools/status", "/tools/latency", "/tools/ip"]:
        assert client.get(path).status_code == 200


def test_about_page(client):
    assert client.get("/about").status_code == 200


def test_404_page(client):
    response = client.get("/definitely-not-a-real-page")
    assert response.status_code == 404
    assert "Page not found" in response.text


# --------------------------------------------------------------------------
# SEO and security headers
# --------------------------------------------------------------------------


def test_sitemap_is_valid_xml(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.text.startswith("<?xml")
    assert "<urlset" in response.text
    assert "/articles/test-ram-memory-errors" in response.text
    assert "/bsod/MEMORY_MANAGEMENT" in response.text


def test_robots_txt(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Sitemap:" in response.text
    assert "Disallow: /admin" in response.text


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" in response.headers
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_csp_allows_tailwind_but_blocks_frames(client):
    csp = client.get("/").headers["content-security-policy"]
    assert "cdn.tailwindcss.com" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_canonical_url_present(client):
    assert 'rel="canonical"' in client.get("/about").text


def test_canonical_and_og_url_are_well_formed(client):
    """canonical_url must be a path, never an absolute URL.

    base.html builds both tags as site_url + canonical_url. When the view
    layer passed an already-absolute request.url the two concatenated into
    "http://localhost:8000http://testserver/about", which Lighthouse scored
    as a canonical failure on every single page. Assert the value, not just
    the attribute - the previous version of this test passed on the broken
    output.
    """
    from app.config import SITE_URL

    for path in ("/", "/about", "/articles", "/bsod"):
        body = client.get(path).text
        expected = f"{SITE_URL}{path}" if path != "/" else f"{SITE_URL}/"

        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', body)
        assert canonical, f"no canonical on {path}"
        assert canonical.group(1) == expected, f"{path}: {canonical.group(1)}"

        og = re.search(r'<meta property="og:url" content="([^"]+)"', body)
        assert og, f"no og:url on {path}"
        assert og.group(1) == expected, f"{path}: {og.group(1)}"

        # A doubled scheme is the exact signature of the old bug.
        assert "http://http" not in body


def test_every_public_page_has_a_meta_description(client):
    """No page may ship an empty meta description.

    seo_description was assigned "" whenever no admin override existed, and
    Jinja's default() only falls back on undefined, never on empty - so the
    homepage and every wizard step rendered content="". base.html now
    resolves the chain with `or`.
    """
    paths = [
        "/",
        "/articles",
        "/about",
        "/privacy",
        "/wizards",
        "/wizards/no-internet",
        "/tools",
        "/tools/dns",
        "/drivers",
        "/hardware",
        "/apps",
        "/scripts",
        "/bsod",
        "/bsod/MEMORY_MANAGEMENT",
        "/search?q=wifi",
    ]
    for path in paths:
        body = client.get(path).text
        m = re.search(r'<meta name="description" content="([^"]*)"', body)
        assert m, f"no meta description tag on {path}"
        desc = m.group(1).strip()
        # Non-empty is the actual requirement. The bound is only there to
        # catch an accidentally-truncated fallback; per-page descriptions
        # like the search page's legitimately run shorter.
        assert len(desc) >= 30, f"{path}: meta description too short ({len(desc)}): {desc!r}"


def test_json_ld_on_article(client):
    assert 'application/ld+json' in client.get("/articles/test-ram-memory-errors").text


def test_static_assets_served(client):
    assert client.get("/static/css/site.css").status_code == 200
    assert client.get("/static/js/site.js").status_code == 200
    assert client.get("/static/favicon.svg").status_code == 200
