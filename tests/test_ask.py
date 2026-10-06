"""The "Ask us anything" round trip: submit, reply, deliver.

The security properties worth protecting here are that a question is anonymous
unless the sender already had an account, that the email can never be supplied
by the caller, and that reading a reply needs the one-off token rather than
merely knowing the question id.
"""

from __future__ import annotations

import re

from app.models import Question
from tests.conftest import make_csrf


def ask(client, prompt: str = "My PC restarts every few hours"):
    return client.post("/api/ask", json={"prompt": prompt})


def csrf_from(client, path: str = "/login") -> str:
    page = client.get(path)
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', page.text)
    assert match is not None, f"no CSRF token on {path}"
    return match.group(1)


def sign_in_reader(client, email: str, password: str = "a-long-good-phrase"):
    """Sign a reader up and in, so a session cookie exists for the ask route."""
    client.post(
        "/signup",
        data={
            "email": email,
            "password": password,
            "confirm": password,
            "csrf": csrf_from(client, "/signup"),
        },
        follow_redirects=True,
    )
    client.post(
        "/login",
        data={"email": email, "password": password, "csrf": csrf_from(client)},
        follow_redirects=True,
    )


def test_submitting_a_question_returns_an_id_and_token(client):
    response = ask(client)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert isinstance(body["id"], int)
    # The token is the only way to read the reply, so it must be long and random.
    assert len(body["token"]) >= 32
    assert body["status"] == "new"


def test_question_is_stored_plain(client, db):
    body = ask(client, "Blue screen on boot").json()

    row = db.get(Question, body["id"])
    assert row is not None
    assert row.prompt == "Blue screen on boot"
    assert row.status == Question.STATUS_NEW
    assert row.reply == ""
    # The raw token must never be written down, only its hash.
    assert row.token_hash != body["token"]
    assert len(row.token_hash) == 64


def test_empty_and_whitespace_prompts_are_refused(client):
    assert ask(client, "").status_code == 400
    assert ask(client, "   \n ").status_code == 400
    # One character is below the minimum too.
    assert ask(client, "x").status_code == 400


def test_malformed_json_is_refused_not_crashed(client):
    response = client.post(
        "/api/ask",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_prompt_is_truncated_at_the_documented_limit(client, db):
    body = ask(client, "y" * 900).json()

    assert len(db.get(Question, body["id"]).prompt) == 500


def test_caller_cannot_choose_the_email(client, db):
    """The email comes from the session, so a body-supplied one is ignored."""
    response = client.post(
        "/api/ask",
        json={"prompt": "Who is this from?", "email": "victim@example.com"},
    )

    row = db.get(Question, response.json()["id"])
    assert row.email == ""
    assert row.user_id is None


def test_signed_in_sender_has_their_email_recorded(client, db):
    """The email is read from the session, so the admin can tell readers apart."""
    sign_in_reader(client, "reader-ask@example.com")

    body = ask(client, "Signed in and asking").json()

    row = db.get(Question, body["id"])
    db.refresh(row)
    assert row.email == "reader-ask@example.com"
    assert row.user_id is not None


def test_anonymous_sender_has_no_email_recorded(client, db):
    body = ask(client, "Nobody signed in here").json()

    row = db.get(Question, body["id"])
    db.refresh(row)
    assert row.email == ""
    assert row.user_id is None


def test_reading_a_reply_requires_the_token(client, db):
    body = ask(client).json()

    wrong = client.get(f"/api/ask/{body['id']}?token=not-the-token")
    missing = client.get(f"/api/ask/{body['id']}")

    # 404 rather than 403: a 403 would confirm the id exists and let anyone
    # walk the queue.
    assert wrong.status_code == 404
    assert missing.status_code == 404

    right = client.get(f"/api/ask/{body['id']}?token={body['token']}")
    assert right.status_code == 200
    assert right.json() == {"ok": True, "status": "new", "reply": ""}


def test_unknown_question_id_is_not_found(client):
    assert client.get("/api/ask/999999?token=whatever").status_code == 404


def test_one_visitor_cannot_read_another_visitors_reply(client, db):
    mine = ask(client, "My question").json()
    theirs = ask(client, "Their question").json()

    # My token against their id must not work.
    assert client.get(f"/api/ask/{theirs['id']}?token={mine['token']}").status_code == 404


def test_reply_is_hidden_until_the_admin_answers(client, admin_client, db):
    submitted = ask(client, "Why is my fan loud?").json()
    csrf = make_csrf(admin_client)

    reply = admin_client.post(
        f"/admin/questions/{submitted['id']}/reply",
        data={"reply": "That is usually a failing bearing.", "csrf": csrf},
        follow_redirects=False,
    )
    assert reply.status_code == 303

    row = db.get(Question, submitted["id"])
    db.refresh(row)
    assert row.status == Question.STATUS_ANSWERED
    assert row.reply == "That is usually a failing bearing."
    assert row.replied_at is not None

    # The visitor's token now returns the answer.
    seen = client.get(f"/api/ask/{submitted['id']}?token={submitted['token']}")
    assert seen.json() == {
        "ok": True,
        "status": "answered",
        "reply": "That is usually a failing bearing.",
    }


def test_empty_reply_is_rejected(client, admin_client, db):
    submitted = ask(client).json()
    csrf = make_csrf(admin_client)

    response = admin_client.post(
        f"/admin/questions/{submitted['id']}/reply",
        data={"reply": "   ", "csrf": csrf},
    )

    assert response.status_code == 403
    row = db.get(Question, submitted["id"])
    db.refresh(row)
    assert row.status == Question.STATUS_NEW


def test_reply_requires_admin_authentication(client, db):
    submitted = ask(client).json()

    response = client.post(
        f"/admin/questions/{submitted['id']}/reply",
        data={"reply": "Let myself in", "csrf": "anything"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    row = db.get(Question, submitted["id"])
    db.refresh(row)
    assert row.status == Question.STATUS_NEW


def test_reply_requires_a_valid_csrf_token(client, admin_client, db):
    submitted = ask(client).json()

    response = admin_client.post(
        f"/admin/questions/{submitted['id']}/reply",
        data={"reply": "Forged", "csrf": "not-the-token"},
    )

    assert response.status_code == 403
    row = db.get(Question, submitted["id"])
    db.refresh(row)
    assert row.status == Question.STATUS_NEW


def test_reopen_puts_a_question_back_in_the_queue(client, admin_client, db):
    submitted = ask(client).json()
    csrf = make_csrf(admin_client)

    admin_client.post(
        f"/admin/questions/{submitted['id']}/reply",
        data={"reply": "First attempt", "csrf": csrf},
        follow_redirects=False,
    )
    admin_client.post(
        f"/admin/questions/{submitted['id']}/reopen",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    row = db.get(Question, submitted["id"])
    db.refresh(row)
    assert row.status == Question.STATUS_NEW


def test_delete_removes_the_question(client, admin_client):
    submitted = ask(client).json()
    csrf = make_csrf(admin_client)

    response = admin_client.post(
        f"/admin/questions/{submitted['id']}/delete",
        data={"csrf": csrf},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert client.get(f"/api/ask/{submitted['id']}?token={submitted['token']}").status_code == 404


def test_submission_is_rate_limited(client):
    from app.rate_limit import ask_limiter

    ask_limiter.reset()
    statuses = [ask(client, f"Question number {n}").status_code for n in range(8)]

    assert 429 in statuses, "the endpoint accepted unlimited questions"
    assert statuses[0] == 200


def test_admin_queue_lists_the_question(admin_client, client):
    ask(client, "A distinctive question for the queue")

    page = admin_client.get("/admin/questions")
    assert page.status_code == 200
    assert "A distinctive question for the queue" in page.text


def test_admin_queue_is_not_public(client):
    response = client.get("/admin/questions", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_dashboard_badges_the_pending_count(admin_client, client, db):
    ask(client, "Dashboard badge check")

    page = admin_client.get("/admin/dashboard")
    assert page.status_code == 200

    # Compared against the real pending total rather than a fixed number,
    # because earlier tests in this file leave unanswered rows behind.
    pending = db.query(Question).filter(
        Question.status == Question.STATUS_NEW
    ).count()
    assert pending >= 1
    assert re.search(rf"Questions\s*\(\s*{pending}\s*\)", page.text)
    assert "Dashboard badge check" in page.text


def test_the_reply_card_has_no_nested_forms(admin_client, client):
    """A <form> inside a <form> is invalid HTML and browsers drop the inner one.

    The card has a reply form plus separate reopen and delete forms, so this
    guards the layout, not the logic.
    """
    from html.parser import HTMLParser

    class FormNesting(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.nested = False

        def handle_starttag(self, tag, attrs):
            if tag != "form":
                return
            if self.depth > 0:
                self.nested = True
            self.depth += 1

        def handle_endtag(self, tag):
            if tag == "form":
                self.depth -= 1

    ask(client, "Check the card markup")
    ask(client, "And a second one")

    parser = FormNesting()
    parser.feed(admin_client.get("/admin/questions").text)

    assert parser.nested is False


def test_widget_is_served_on_every_page(client):
    page = client.get("/")

    assert page.status_code == 200
    assert "/static/js/ask-widget.js" in page.text