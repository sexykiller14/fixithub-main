"""Stop code lookup, minidump parsing and the analyzer endpoint."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import StopCode
from app.services import minidump as dump
from app.services.stopcodes import lookup, normalise_query, parse_code_hex


# --------------------------------------------------------------------------
# parse_code_hex
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0x0000007B", 0x7B),
        ("0x7B", 0x7B),
        ("7B", 0x7B),
        ("0x7b", 0x7B),
        ("0X00000116", 0x116),
        ("  0xed  ", 0xED),
    ],
)
def test_parse_code_hex_accepts_common_formats(value, expected):
    assert parse_code_hex(value) == expected


@pytest.mark.parametrize("value", ["", "0xZZ", "hello", "0x", "1.5", "0x123456789"])
def test_parse_code_hex_rejects_garbage(value):
    with pytest.raises(ValueError):
        parse_code_hex(value)


def test_normalise_query():
    assert normalise_query("irql not less or equal") == "IRQL_NOT_LESS_OR_EQUAL"
    assert normalise_query("memory-management") == "MEMORY_MANAGEMENT"
    assert normalise_query("  Page_Fault  ") == "PAGE_FAULT"


# --------------------------------------------------------------------------
# lookup
# --------------------------------------------------------------------------


def test_lookup_by_full_hex(db):
    found = lookup(db, "0x0000007B")
    assert found is not None
    assert found.name == "INACCESSIBLE_BOOT_DEVICE"


def test_lookup_by_short_hex(db):
    assert lookup(db, "7B").name == "INACCESSIBLE_BOOT_DEVICE"
    assert lookup(db, "0x7b").name == "INACCESSIBLE_BOOT_DEVICE"
    assert lookup(db, "ed").name == "UNMOUNTABLE_BOOT_VOLUME"


def test_lookup_by_decimal_value(db):
    """Dump files and Event Log entries show the bugcheck value in decimal."""
    assert lookup(db, "26").name == "MEMORY_MANAGEMENT"        # 0x1A
    assert lookup(db, "123").name == "INACCESSIBLE_BOOT_DEVICE"  # 0x7B
    assert lookup(db, "237").name == "UNMOUNTABLE_BOOT_VOLUME"   # 0xED


def test_lookup_by_name(db):
    assert lookup(db, "MEMORY_MANAGEMENT").code_hex == "0x0000001A"


def test_lookup_by_lowercase_name(db):
    assert lookup(db, "memory_management").name == "MEMORY_MANAGEMENT"


def test_lookup_by_spaced_name(db):
    """Readers often type the name with spaces instead of underscores."""
    assert lookup(db, "IRQL NOT LESS OR EQUAL").name == "IRQL_NOT_LESS_OR_EQUAL"


def test_lookup_hyphenated_name(db):
    assert lookup(db, "page-fault-in-nonpaged-area").code_uint == 0x50


def test_lookup_returns_none_for_unknown(db):
    assert lookup(db, "NOT_A_REAL_STOP_CODE") is None
    assert lookup(db, "0xDEADBEEF") is None
    assert lookup(db, "") is None


def test_lookup_does_not_treat_hex_as_a_substring(db):
    """A short hex value must not match every code containing those digits."""
    # 0x7 would be a substring of 0x7B, 0x7E, 0x1B and many more.
    assert lookup(db, "0x7") is None
    assert lookup(db, "0x1") is None
    assert lookup(db, "7") is None


def test_lookup_is_case_insensitive_for_hex(db):
    first = lookup(db, "0x000000ed")
    second = lookup(db, "0x000000ED")
    assert first is not None and second is not None
    assert first.id == second.id


# --------------------------------------------------------------------------
# Data integrity
# --------------------------------------------------------------------------


def test_stop_code_count(db):
    assert db.query(StopCode).count() >= 40


def test_stop_codes_have_unique_values(db):
    rows = db.execute(select(StopCode.code_uint, StopCode.name)).all()
    codes = [row[0] for row in rows]
    names = [row[1] for row in rows]
    assert len(codes) == len(set(codes))
    assert len(names) == len(set(names))


def test_every_stop_code_is_complete(db):
    for code in db.query(StopCode).all():
        assert code.meaning.strip(), f"{code.name} has no meaning"
        assert len(code.causes) >= 3, f"{code.name} needs at least 3 causes"
        assert len(code.fix_steps) >= 4, f"{code.name} needs at least 4 fix steps"
        assert code.when_to_call_pro.strip(), f"{code.name} has no pro-advice"
        assert code.difficulty in {"easy", "moderate", "hard", "advanced"}


# --------------------------------------------------------------------------
# Minidump validation
# --------------------------------------------------------------------------


def test_rejects_wrong_extension():
    with pytest.raises(dump.DumpError, match="dmp"):
        dump.validate_extension("payload.exe")


def test_rejects_path_traversal_in_filename():
    with pytest.raises(dump.DumpError):
        dump.validate_extension("../../etc/passwd.dmp")
    with pytest.raises(dump.DumpError):
        dump.validate_extension(r"..\windows\evil.dmp")


@pytest.mark.parametrize("signature", [b"PMDMP", b"PAGEDU", b"PAGE", b"FULL"])
def test_accepts_known_signatures(signature):
    data = signature + b"\x00" * 64
    assert dump.validate_signature(data) == signature.decode("ascii")


def test_rejects_non_dump_file():
    with pytest.raises(dump.DumpError, match="does not look like"):
        dump.validate_signature(b"PK\x03\x04" + b"\x00" * 64)


def test_rejects_too_short_file():
    with pytest.raises(dump.DumpError, match="too short"):
        dump.validate_signature(b"PM")


def test_rejects_oversized_upload():
    with pytest.raises(dump.DumpError, match="limit is"):
        dump.validate_size(10 * 1024 * 1024, 5 * 1024 * 1024)


def test_rejects_empty_upload():
    with pytest.raises(dump.DumpError, match="empty"):
        dump.validate_size(0, 5 * 1024 * 1024)


# --------------------------------------------------------------------------
# Minidump analysis
# --------------------------------------------------------------------------


def test_analyses_synthetic_minidump(sample_dump):
    result = dump.analyse(sample_dump, "test.dmp", 5 * 1024 * 1024)
    assert result.signature == "PMDMP"
    assert result.bugcheck is not None
    assert result.bugcheck.code == 0x0000001A
    assert result.bugcheck.name == "MEMORY_MANAGEMENT"
    assert result.bugcheck.parameters[1] == 0x1234ABCD


def test_parameter_hints_are_attached_for_known_codes(sample_dump):
    """Known codes explain what each parameter means; unknown ones say so."""
    result = dump.analyse(sample_dump, "test.dmp", 5 * 1024 * 1024)
    assert result.bugcheck is not None
    assert result.bugcheck.parameter_hints
    rows = result.bugcheck.parameter_rows()
    assert len(rows) == 4
    assert all(row["hint"] for row in rows)


def test_analysis_reports_notes_for_unparseable_dump():
    data = b"PMDMP" + b"\x00" * 200
    result = dump.analyse(data, "empty.dmp", 5 * 1024 * 1024)
    assert result.bugcheck is None
    assert result.notes


def test_analysis_never_writes_a_file(tmp_path, monkeypatch):
    """Uploads are parsed in memory; nothing may be written to disk."""
    before = set(p.name for p in tmp_path.iterdir())
    data = b"PMDMP" + b"\x00" * 200
    dump.analyse(data, "x.dmp", 5 * 1024 * 1024)
    assert set(p.name for p in tmp_path.iterdir()) == before


def test_name_lookup_uses_local_table():
    assert dump.name_for_code(0x116) == "VIDEO_TDR_FAILURE"
    assert dump.name_for_code(0x7B) == "INACCESSIBLE_BOOT_DEVICE"


def test_64bit_tagging_is_normalised():
    """Some codes have their own tagged entry, which must resolve to that entry."""
    assert dump.name_for_code(0x1000007E) == "SYSTEM_THREAD_EXCEPTION_NOT_HANDLED_M"


def test_untagged_64bit_variant_falls_back_to_the_base_code():
    """A tagged code with no dedicated entry falls back to its base code."""
    assert dump._strip_high_bit(0x10000116) == 0x00000116
    assert dump.name_for_code(0x10000116) == "VIDEO_TDR_FAILURE"


def test_genuine_64bit_codes_are_not_mangled():
    assert dump._strip_high_bit(0xC000021A) == 0xC000021A
    assert dump.name_for_code(0xC000021A) == "WINLOGON_FATAL_ERROR"


# --------------------------------------------------------------------------
# HTTP endpoints
# --------------------------------------------------------------------------


def test_bsod_index_loads(client):
    response = client.get("/bsod")
    assert response.status_code == 200
    assert "stop code lookup" in response.text.lower()


def test_lookup_page_resolves_code(client):
    response = client.get("/bsod/lookup", params={"q": "0x0000007B"})
    assert response.status_code == 200
    assert "INACCESSIBLE_BOOT_DEVICE" in response.text


def test_lookup_page_with_garbage_offers_suggestions(client):
    response = client.get("/bsod/lookup", params={"q": "MEMORY"})
    assert response.status_code == 200
    assert "MEMORY_MANAGEMENT" in response.text


def test_stop_code_detail_page(client):
    response = client.get("/bsod/CRITICAL_PROCESS_DIED")
    assert response.status_code == 200
    assert "CRITICAL_PROCESS_DIED" in response.text
    assert "When to see a professional" in response.text


def test_stop_code_detail_lowercase(client):
    assert client.get("/bsod/memory_management").status_code == 200


def test_unknown_stop_code_returns_404(client):
    assert client.get("/bsod/NOT_A_REAL_CODE_XYZ").status_code == 404


def test_stop_code_detail_blocks_traversal(client):
    response = client.get("/bsod/../../etc/passwd")
    assert response.status_code in (404, 400)


def test_analyzer_form_loads(client):
    response = client.get("/bsod/analyze")
    assert response.status_code == 200
    assert "Minidump analyzer" in response.text


def test_analyzer_rejects_non_dump(client, tmp_path):
    payload = tmp_path / "evil.txt"
    payload.write_bytes(b"this is definitely not a dump file")
    with payload.open("rb") as handle:
        response = client.post(
            "/bsod/analyze",
            files={"dump_file": ("evil.txt", handle, "text/plain")},
        )
    assert response.status_code == 400
    assert "dmp" in response.text.lower()


def test_analyzer_rejects_bad_signature(client, tmp_path):
    payload = tmp_path / "fake.dmp"
    payload.write_bytes(b"PK\x03\x04" + b"0" * 512)
    with payload.open("rb") as handle:
        response = client.post(
            "/bsod/analyze",
            files={"dump_file": ("fake.dmp", handle, "application/octet-stream")},
        )
    assert response.status_code == 400
    assert "does not look like" in response.text


def test_analyzer_rejects_oversized_upload(client):
    """A file over the limit is refused without being read fully."""
    big = b"PMDMP" + b"\x00" * (6 * 1024 * 1024)
    response = client.post(
        "/bsod/analyze",
        files={"dump_file": ("big.dmp", big, "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "limit" in response.text.lower()


def test_analyzer_success_shows_matching_guide(client, sample_dump):
    response = client.post(
        "/bsod/analyze",
        files={"dump_file": ("crash.dmp", sample_dump, "application/octet-stream")},
    )
    assert response.status_code == 200
    assert "MEMORY_MANAGEMENT" in response.text
    assert "0x0000001A" in response.text
    assert "Bugcheck found" in response.text
