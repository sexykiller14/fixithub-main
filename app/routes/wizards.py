"""Guided troubleshooting wizards."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import build_context, total_counts
from ..models import Article
from ..services import wizards as wz
from ..templates import render

router = APIRouter()

MAX_HISTORY = 30
MAX_LABEL = 200


def _session_key(wizard_id: str) -> str:
    return f"wizard:{wizard_id}"


def _load_history(request: Request, wizard_id: str) -> list[dict]:
    raw = request.session.get(_session_key(wizard_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    # Only well-formed steps are kept, so tampered session data cannot break traversal.
    clean: list[dict] = []
    for step in data[:MAX_HISTORY]:
        if isinstance(step, dict) and isinstance(step.get("label"), str):
            clean.append({"label": step["label"][:MAX_LABEL]})
    return clean


def _save_history(request: Request, wizard_id: str, history: list[dict]) -> None:
    request.session[_session_key(wizard_id)] = json.dumps(history[-MAX_HISTORY:])


@router.get("/wizards", name="wizards_index")
def wizards_index(request: Request, db: Session = Depends(get_db)):
    context = build_context(
        request,
        db,
        nav_open="wizards",
        wizards=wz.list_wizards(),
        counts=total_counts(db),
    )
    return render(request, "wizards_index.html", context)


@router.get("/wizards/{wizard_id}", name="wizard")
def wizard(request: Request, wizard_id: str, db: Session = Depends(get_db)):
    wizard = wz.load_wizard(wizard_id)
    if wizard is None:
        return _not_found(request, db)

    # A fresh visit starts the wizard over.
    request.session.pop(_session_key(wizard_id), None)

    node = wz.start_step(wizard)
    context = build_context(
        request,
        db,
        nav_open="wizards",
        wizard=wizard,
        node=node,
        history=[],
        progress=wz.progress(wizard, []),
        all_wizards=wz.list_wizards(),
        counts=total_counts(db),
    )
    return render(request, "wizard_step.html", context)


@router.get("/wizards/{wizard_id}/back", name="wizard_back")
def wizard_back(request: Request, wizard_id: str, db: Session = Depends(get_db)):
    wizard = wz.load_wizard(wizard_id)
    if wizard is None:
        return _not_found(request, db)

    history = _load_history(request, wizard_id)
    if history:
        history.pop()

    _save_history(request, wizard_id, history)
    return RedirectResponse(f"/wizards/{wizard_id}/step", status_code=303)


@router.get("/wizards/{wizard_id}/step", name="wizard_step")
def wizard_step(request: Request, wizard_id: str, db: Session = Depends(get_db)):
    """Render the current node from the history stored in the session."""
    wizard = wz.load_wizard(wizard_id)
    if wizard is None:
        return _not_found(request, db)

    history = _load_history(request, wizard_id)
    nodes = wz.trail_nodes(wizard, history)
    if not nodes:
        return RedirectResponse(f"/wizards/{wizard_id}", status_code=303)

    node = nodes[-1]
    context = build_context(
        request,
        db,
        nav_open="wizards",
        wizard=wizard,
        node=node,
        history=history,
        progress=wz.progress(wizard, history),
        answered_questions=[n.question for n in nodes[:-1]],
        all_wizards=wz.list_wizards(),
        counts=total_counts(db),
    )
    if node.is_result:
        context["article"] = _related_article(db, node.article_slug)
    return render(request, "wizard_step.html", context)


@router.post("/wizards/{wizard_id}/answer", name="wizard_answer")
def wizard_answer(
    request: Request,
    wizard_id: str,
    choice: int = Form(0),
    db: Session = Depends(get_db),
):
    wizard = wz.load_wizard(wizard_id)
    if wizard is None:
        return _not_found(request, db)

    history = _load_history(request, wizard_id)
    nodes = wz.trail_nodes(wizard, history)
    current = nodes[-1]

    if current.is_result:
        return RedirectResponse(f"/wizards/{wizard_id}/step", status_code=303)

    option_index = choice if 0 <= choice < len(current.options) else 0
    next_id = wz.follow(wizard, current.id, option_index)
    if next_id is None:
        return RedirectResponse(f"/wizards/{wizard_id}", status_code=303)

    history.append({"label": current.options[option_index].label[:MAX_LABEL]})
    _save_history(request, wizard_id, history)
    return RedirectResponse(f"/wizards/{wizard_id}/step", status_code=303)


@router.get("/wizards/{wizard_id}/restart", name="wizard_restart")
def wizard_restart(request: Request, wizard_id: str):
    """Clear the saved history and return to the first question.

    This only discards progress in the visitor's own session, so it is a safe
    GET and needs no CSRF token.
    """
    wizard = wz.load_wizard(wizard_id)
    if wizard is None:
        return RedirectResponse("/wizards", status_code=303)
    request.session.pop(_session_key(wizard_id), None)
    return RedirectResponse(f"/wizards/{wizard_id}", status_code=303)


def _related_article(db: Session, slug: str):
    if not slug:
        return None
    return db.query(Article).filter(Article.slug == slug).first()


def _not_found(request: Request, db: Session):
    return render(
        request,
        "404.html",
        build_context(
            request,
            db,
            nav_open="wizards",
            robots="noindex, nofollow",
            status_code=404,
            error_title="Wizard not found",
            error_message="That troubleshooting wizard does not exist.",
        ),
        status_code=404,
    )
