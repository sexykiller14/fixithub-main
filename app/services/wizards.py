"""JSON decision-tree wizard loading and traversal."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config import WIZARDS_DIR

MAX_HISTORY = 40


@dataclass(frozen=True)
class WizardOption:
    label: str
    next_id: str
    tag: str = ""


@dataclass
class WizardNode:
    id: str
    question: str = ""
    help: str = ""
    options: list[WizardOption] = field(default_factory=list)
    type: str = "question"
    title: str = ""
    diagnosis: str = ""
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    article_slug: str = ""
    difficulty: str = "easy"

    @property
    def is_result(self) -> bool:
        return self.type == "result"


@dataclass
class Wizard:
    id: str
    title: str
    summary: str
    icon: str
    estimated_minutes: int
    start_id: str
    nodes: dict[str, WizardNode]

    def node(self, node_id: str) -> WizardNode | None:
        return self.nodes.get(node_id)

    def depth(self, node_id: str, limit: int = 25) -> int:
        """Longest path length from a node to a result. Guards against cycles."""
        node = self.node(node_id)
        if node is None or node.is_result:
            return 0
        best = 0
        for option in node.options:
            child = self.node(option.next_id)
            if child is None:
                continue
            best = max(best, 1 + self.depth(option.next_id, limit - 1))
        return best if limit > 0 else 0


def _build_node(raw: dict, node_id: str) -> WizardNode:
    node_type = str(raw.get("type", "question"))
    if node_type == "result":
        return WizardNode(
            id=node_id,
            type="result",
            title=str(raw.get("title", "Recommendation")),
            diagnosis=str(raw.get("diagnosis", "")),
            steps=[str(s) for s in raw.get("steps", [])],
            warnings=[str(w) for w in raw.get("warnings", [])],
            article_slug=str(raw.get("article_slug", "")),
            difficulty=str(raw.get("difficulty", "easy")),
        )
    options = []
    for opt in raw.get("options", []):
        options.append(
            WizardOption(
                label=str(opt.get("label", "Continue")),
                next_id=str(opt.get("next", "")),
                tag=str(opt.get("tag", "")),
            )
        )
    return WizardNode(
        id=node_id,
        question=str(raw.get("question", "")),
        help=str(raw.get("help", "")),
        options=options,
    )


@lru_cache(maxsize=32)
def _load_wizard_file(path_str: str) -> tuple:
    raw = json.loads(Path(path_str).read_text(encoding="utf-8"))
    nodes = {
        node_id: _build_node(node_data, node_id)
        for node_id, node_data in (raw.get("nodes") or {}).items()
    }
    return (
        str(raw.get("id", Path(path_str).stem)),
        str(raw.get("title", "Wizard")),
        str(raw.get("summary", "")),
        str(raw.get("icon", "help")),
        int(raw.get("estimated_minutes", 5)),
        str(raw.get("start", "")),
        nodes,
    )


def load_wizard(wizard_id: str) -> Wizard | None:
    """Load one wizard by id, rejecting anything outside the wizards directory."""
    if not wizard_id or "/" in wizard_id or "\\" in wizard_id or ".." in wizard_id:
        return None
    if not wizard_id.replace("-", "").replace("_", "").isalnum():
        return None
    path = WIZARDS_DIR / f"{wizard_id}.json"
    if not path.is_file():
        return None
    try:
        data = _load_wizard_file(str(path.resolve()))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    wid, title, summary, icon, minutes, start, nodes = data
    if start not in nodes:
        return None
    return Wizard(wid, title, summary, icon, minutes, start, nodes)


def list_wizards() -> list[Wizard]:
    """All available wizards, ordered by the order field then title."""
    wizards: list[Wizard] = []
    if not WIZARDS_DIR.exists():
        return wizards
    for path in sorted(WIZARDS_DIR.glob("*.json")):
        wizard = load_wizard(path.stem)
        if wizard is not None:
            wizards.append(wizard)
    return wizards


def start_step(wizard: Wizard) -> WizardNode:
    node = wizard.node(wizard.start_id)
    assert node is not None  # load_wizard guarantees the start node exists
    return node


def follow(wizard: Wizard, node_id: str, option_index: int) -> str | None:
    """Return the next node id for a chosen option, or None if invalid."""
    node = wizard.node(node_id)
    if node is None or node.is_result:
        return None
    if option_index < 0 or option_index >= len(node.options):
        return None
    next_id = node.options[option_index].next_id
    return next_id if wizard.node(next_id) is not None else None


def find_option_index(wizard: Wizard, node_id: str, label: str) -> int:
    """Reverse lookup so the Back button can restore a choice by label."""
    node = wizard.node(node_id)
    if node is None:
        return -1
    for index, option in enumerate(node.options):
        if option.label == label:
            return index
    return -1


def trail_nodes(wizard: Wizard, history: list[dict]) -> list[WizardNode]:
    """Nodes along the path travelled so far, including the current one."""
    nodes: list[WizardNode] = []
    node = wizard.node(wizard.start_id)
    if node is not None:
        nodes.append(node)
    for step in history:
        label = step.get("label", "")
        index = find_option_index(wizard, node.id if node else "", label)
        if index < 0 or node is None:
            break
        nxt = wizard.node(node.options[index].next_id)
        if nxt is None:
            break
        nodes.append(nxt)
        node = nxt
    return nodes


def progress(wizard: Wizard, history: list[dict]) -> dict:
    """Progress metadata for the indicator, based on the longest path."""
    node_ids = [n.id for n in trail_nodes(wizard, history)]
    current = node_ids[-1] if node_ids else wizard.start_id
    total_steps = max(1, wizard.depth(wizard.start_id))
    done = max(0, len(node_ids) - 1)
    remaining = wizard.depth(current)
    return {
        "answered": done,
        "total": min(total_steps, max(done + remaining, done)),
        "percent": min(100, int(round((done / max(1, total_steps)) * 100))),
        "path": node_ids,
    }
