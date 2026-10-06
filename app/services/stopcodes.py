"""Stop code lookup: normalisation, database sync and resolution."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import DATA_DIR
from ..models import StopCode

STOP_CODES_FILE = DATA_DIR / "bsod_codes.json"

HEX_RE = re.compile(r"(?:0x)?([0-9a-f]{1,8})", re.IGNORECASE)


@dataclass
class StopCodeSeed:
    code_hex: str
    code_uint: int
    name: str
    meaning: str
    causes: list[str]
    fix_steps: list[str]
    difficulty: str
    when_to_call_pro: str
    related_slugs: list[str]


def parse_code_hex(code_hex: str) -> int:
    """Convert a 0x-prefixed string to an integer, validating the format."""
    cleaned = code_hex.strip()
    if cleaned.lower().startswith("0x"):
        cleaned = cleaned[2:]
    if not cleaned or not re.fullmatch(r"[0-9a-fA-F]{1,8}", cleaned):
        raise ValueError(f"Invalid stop code: {code_hex!r}")
    return int(cleaned, 16)


def load_stop_codes_file(path: Path | None = None) -> list[StopCodeSeed]:
    """Read bsod_codes.json into validated seed objects."""
    target = path or STOP_CODES_FILE
    raw = json.loads(target.read_text(encoding="utf-8"))
    seeds: list[StopCodeSeed] = []
    for item in raw:
        seeds.append(
            StopCodeSeed(
                code_hex=item["code_hex"],
                code_uint=parse_code_hex(item["code_hex"]),
                name=item["name"].strip(),
                meaning=item["meaning"].strip(),
                causes=list(item.get("causes") or []),
                fix_steps=list(item.get("fix_steps") or []),
                difficulty=str(item.get("difficulty", "moderate")).lower(),
                when_to_call_pro=item.get("when_to_call_pro", ""),
                related_slugs=list(item.get("related_slugs") or []),
            )
        )
    return seeds


def sync_stop_codes(db: Session, seeds: list[StopCodeSeed] | None = None) -> int:
    """Upsert stop codes into the database. Returns the number written."""
    data = seeds if seeds is not None else load_stop_codes_file()
    written = 0
    for seed in data:
        existing = db.scalar(select(StopCode).where(StopCode.code_uint == seed.code_uint))
        if existing is None:
            existing = StopCode(code_uint=seed.code_uint)
            db.add(existing)
        existing.code_hex = seed.code_hex
        existing.name = seed.name
        existing.meaning = seed.meaning
        existing.causes = seed.causes
        existing.fix_steps = seed.fix_steps
        existing.difficulty = seed.difficulty
        existing.when_to_call_pro = seed.when_to_call_pro
        existing.related_slugs = seed.related_slugs
        written += 1
    db.flush()
    return written


def _build_code_map() -> dict[int, str]:
    """Map stop code value to name, for the minidump analyzer."""
    mapping: dict[int, str] = {}
    if not STOP_CODES_FILE.is_file():
        return mapping
    try:
        for item in json.loads(STOP_CODES_FILE.read_text(encoding="utf-8")):
            mapping[parse_code_hex(item["code_hex"])] = item["name"]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    return mapping


CODE_TO_NAME: dict[int, str] = _build_code_map()


def normalise_query(raw: str) -> str:
    """Reduce user input to a comparable form."""
    text = (raw or "").strip().upper()
    text = text.replace("-", "_").replace(" ", "_")
    text = re.sub(r"[^A-Z0-9_]", "", text)
    return text


def lookup(db: Session, query: str) -> StopCode | None:
    """Resolve a stop code by hex value or name, tolerating user formatting.

    Accepts 0x0000007E, 7E, IRQL_NOT_LESS_OR_EQUAL and irql not less or equal.
    """
    raw = (query or "").strip()
    if not raw:
        return None

    # 1. Exact numeric value.
    #    - "0x7B" is unambiguously hex.
    #    - A token containing a hex letter, such as "7B" or "ed", is hex too.
    #    - A token of digits only, such as "126", is read as decimal, which is
    #      how the value appears in a dump or an Event Log entry.
    candidates: list[int] = []
    if re.fullmatch(r"(?i)0x[0-9a-f]{1,8}", raw):
        try:
            candidates.append(parse_code_hex(raw))
        except ValueError:
            pass
    elif re.fullmatch(r"(?i)[0-9a-f]{1,8}", raw):
        if re.fullmatch(r"\d{1,10}", raw):
            candidates.append(int(raw))
        if re.search(r"(?i)[a-f]", raw):
            try:
                candidates.append(parse_code_hex(raw))
            except ValueError:
                pass
    for value in candidates:
        if 0 <= value <= 0xFFFFFFFF:
            found = db.scalar(select(StopCode).where(StopCode.code_uint == value))
            if found is not None:
                return found

    # 2. Exact name.
    name = normalise_query(raw)
    if name:
        found = db.scalar(select(StopCode).where(func.upper(StopCode.name) == name))
        if found is not None:
            return found

    # 3. Name with underscores removed, so "irq..." style input still matches.
    compact = name.replace("_", "")
    if len(compact) >= 4:
        found = db.execute(
            select(StopCode).where(func.replace(func.upper(StopCode.name), "_", "").like(f"%{compact}%"))
        ).scalars().first()
        if found is not None:
            return found

    return None


def search(db: Session, query: str, limit: int = 15) -> list[StopCode]:
    """Fuzzy search across names and meanings for the lookup autocomplete."""
    raw = (query or "").strip()
    if len(raw) < 2:
        return []
    pattern = f"%{normalise_query(raw)}%"
    return list(
        db.execute(
            select(StopCode)
            .where(func.upper(StopCode.name).like(pattern))
            .order_by(StopCode.name)
            .limit(limit)
        ).scalars()
    )


def all_stop_codes(db: Session) -> list[StopCode]:
    return list(db.execute(select(StopCode).order_by(StopCode.code_uint)).scalars())


def popular(db: Session, limit: int = 8) -> list[StopCode]:
    return list(
        db.execute(
            select(StopCode).order_by(StopCode.view_count.desc(), StopCode.code_uint).limit(limit)
        ).scalars()
    )
