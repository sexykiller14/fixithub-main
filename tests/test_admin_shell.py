"""The admin shell: one sidebar, one top bar, one content column.

The panel had 21 pages and no shared navigation partial, so each page hand-rolled
its own container and header. That produced seven different container widths,
four header shapes, and five pages with no route back to the dashboard. These
tests hold the shared shell in place: every admin page uses it, and it renders
the navigation and the landmarks that the rest of the markup depends on.
"""

import re

import pytest

# Every admin page that should sit inside the shell. admin_login is excluded on
# purpose: the login form is deliberately chrome-free, so an admin who is locked
# out has no navigation to click.
SHELL_PAGES = [
    "/admin/dashboard",
    "/admin/articles",
    "/admin/stop-codes",
    "/admin/apps",
    "/admin/comments",
    "/admin/questions",
    "/admin/ads",
    "/admin/seo",
    "/admin/emails",
    "/admin/links",
    "/admin/announcement",
    "/admin/restore",
    "/admin/change-password",
    "/admin/articles/new",
    "/admin/stop-codes/new",
    "/admin/apps/new",
]


@pytest.mark.parametrize("path", SHELL_PAGES)
def test_every_admin_page_uses_the_shared_shell(admin_client, path):
    response = admin_client.get(path)
    assert response.status_code == 200, f"{path} returned {response.status_code}"
    assert 'data-admin-nav' in response.text, f"{path} is not using the shared shell"
    assert 'id="admin-sidebar"' in response.text, f"{path} has no sidebar"


@pytest.mark.parametrize("path", SHELL_PAGES)
def test_no_admin_page_reintroduces_its_own_container(admin_client, path):
    """The old per-page wrapper is gone.

    The shell supplies its own padding, so a page carrying max-w-* px-4 py-10
    is back to inventing its own layout.
    """
    response = admin_client.get(path)
    body = response.text
    assert not re.search(r'class="mx-auto max-w-\dxl px-4[^"]*py-10"', body), (
        f"{path} still has its own page container; the shell owns that now"
    )


def test_the_sidebar_links_to_every_admin_section(admin_client):
    response = admin_client.get("/admin/dashboard")
    body = response.text
    sidebar = body.split('id="admin-sidebar"', 1)[1].split("</aside>", 1)[0]

    for href in (
        "/admin/dashboard",
        "/admin/articles",
        "/admin/stop-codes",
        "/admin/apps",
        "/admin/comments",
        "/admin/questions",
        "/admin/ads",
        "/admin/seo",
        "/admin/announcement",
        "/admin/links",
        "/admin/emails",
        "/admin/backup",
        "/admin/restore",
        "/admin/change-password",
    ):
        assert f'href="{href}"' in sidebar, f"the sidebar has no link to {href}"


def test_the_sidebar_marks_the_current_page(admin_client):
    """The active link carries aria-current, which is what the CSS keys off."""
    response = admin_client.get("/admin/articles")
    body = response.text
    sidebar = body.split('id="admin-sidebar"', 1)[1].split("</aside>", 1)[0]

    active = re.findall(r'<a href="([^"]+)"[^>]*aria-current="page"', sidebar)
    assert "/admin/articles" in active, f"no active link on /admin/articles; found {active}"


def test_the_page_has_exactly_one_main_and_one_h1(admin_client):
    response = admin_client.get("/admin/dashboard")
    body = response.text
    # base.html and admin_base.html each provide a <main>, so a page that kept
    # its own would render two.
    assert body.count("<main") == 1, "more than one <main> on the page"
    assert body.count("<h1") == 1, "the page title should appear exactly once"


def test_the_public_header_is_not_rendered_in_the_admin(admin_client):
    """The admin replaces the public header rather than stacking under it."""
    response = admin_client.get("/admin/dashboard")
    assert "Mobile navigation" not in response.text, (
        "the public mobile nav is still on an admin page"
    )


def test_the_admin_carries_a_dark_mode_toggle(admin_client):
    response = admin_client.get("/admin/dashboard")
    assert 'id="theme-toggle"' in response.text, "the admin has no dark mode toggle"


def test_sign_out_is_reachable_without_scrolling_a_button_wall(admin_client):
    """Sign out lives in the sidebar and the profile menu, both in the shell."""
    response = admin_client.get("/admin/dashboard")
    body = response.text
    assert body.count('action="/admin/logout"') >= 2, (
        "expected sign out in both the sidebar and the profile dropdown"
    )


def test_the_shell_carries_a_csrf_token_for_signing_out(admin_client):
    response = admin_client.get("/admin/dashboard")
    sidebar = response.text.split('id="admin-sidebar"', 1)[1].split("</aside>", 1)[0]
    assert 'name="csrf"' in sidebar, "the sign-out form in the sidebar has no CSRF token"


def test_the_login_page_stays_chrome_free(client):
    """A locked-out admin must not see a navigation they cannot use."""
    response = client.get("/admin")
    assert response.status_code == 200
    assert 'data-admin-nav' not in response.text
    assert 'name="password"' in response.text