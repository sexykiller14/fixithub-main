"""TOTP checked against the RFC's own vectors, not against itself.

app/services/totp.py is hand-written RFC 6238 rather than a library call, which
means a wrong constant truncation would pass any test that used the same code
to generate its expectations. So the expectations come from RFC 6238 appendix
B and are pinned here as literals.

The RFC's secrets are the ASCII string "12345678901234567890" in base32, and
its 8-digit codes are truncated to 6 here because that is what every
authenticator app displays.
"""

import base64
from datetime import datetime, timezone

import pytest

from app.services import totp

# base32("12345678901234567890") - the secret all six vectors use.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")

# (unix timestamp, RFC's 8-digit code) from RFC 6238 appendix B.
RFC_VECTORS = [
    (59, "94287082"),
    (1111111109, "07081804"),
    (1111111111, "14050471"),
    (1234567890, "89005924"),
    (2000000000, "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize("timestamp,expected", RFC_VECTORS)
def test_matches_the_rfc_6238_vectors(timestamp, expected):
    assert totp.code_at(RFC_SECRET, timestamp) == expected[-totp.DIGITS:]


def test_the_secret_is_long_enough_and_base32():
    secret = totp.generate_secret()
    # 20 bytes -> 32 base32 characters.
    assert len(secret) == 32
    assert "=" not in secret, "the padding should be stripped for display"
    # Must round-trip through the decoder, padding restored.
    assert len(totp._secret_bytes(secret)) == 20


def test_secrets_are_unique():
    assert totp.generate_secret() != totp.generate_secret()


def test_a_current_code_verifies():
    secret = totp.generate_secret()
    now = datetime.now(timezone.utc).timestamp()
    assert totp.verify(secret, totp.code_at(secret, now), now)


def test_a_code_from_the_future_or_past_outside_the_window_fails():
    secret = totp.generate_secret()
    now = 1_700_000_000.0
    far_off = now + totp.STEP_SECONDS * 10
    assert not totp.verify(secret, totp.code_at(secret, far_off), now)


def test_one_step_of_drift_is_tolerated():
    """A phone with a slow clock is the normal case, not an attack."""
    secret = totp.generate_secret()
    now = 1_700_000_000.0
    previous = totp.code_at(secret, now - totp.STEP_SECONDS)
    assert totp.verify(secret, previous, now)


def test_the_wrong_code_is_rejected():
    secret = totp.generate_secret()
    now = 1_700_000_000.0
    good = totp.code_at(secret, now)
    wrong = "000000" if good != "000000" else "111111"
    assert not totp.verify(secret, wrong, now)


@pytest.mark.parametrize("junk", ["", "abcdef", "12345", "1234567", "12345678x", "  "])
def test_malformed_input_is_rejected_without_raising(junk):
    assert not totp.verify(RFC_SECRET, junk, 59)


def test_the_provisioning_uri_carries_what_an_app_reads():
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP")
    assert uri.startswith("otpauth://totp/")
    assert "secret=JBSWY3DPEHPK3PXP" in uri
    assert "issuer=FixIT%20Hub" in uri
    assert "digits=6" in uri
    assert "period=30" in uri


def test_the_uri_quotes_the_account_name():
    """The account goes into the label, so & and ? must be encoded.

    The literal word "evil" is still present in the URI - it is encoded as
    %3E for the > - what must not happen is a bare & or ? that would let the
    value start a new query parameter and so forge the issuer.
    """
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", account="a&issuer=evil")

    # Exactly one unencoded '?' - the one separating the label from the query.
    assert uri.count("?") == 1, "the account name injected a query separator"
    # The & inside the account is encoded, so the issuer parameter is ours.
    assert "%26" in uri
    query = uri.split("?", 1)[1]
    assert query.count("issuer=") == 1
    assert query.startswith("secret="), "the query no longer starts with the secret"


# --------------------------------------------------------------------------
# Storage, in the database
# --------------------------------------------------------------------------
#
# The enrolment is a database row rather than a file, so these tests share the
# suite's session-scoped database. An autouse fixture empties the row between
# them, and no fixture points at a temporary data directory any more.


@pytest.fixture
def enrolled():
    """An enrolled secret with recovery codes."""
    secret = totp.generate_secret()
    codes = totp.generate_recovery_codes(5)
    totp.save(secret, codes)
    return secret, codes


def test_save_then_is_enrolled(enrolled):
    assert totp.is_enrolled()


def test_nothing_is_enrolled_on_a_clean_install():
    assert not totp.is_enrolled()


def test_the_enrolment_survives_a_new_process(enrolled):
    """The reason the secret is a row and not a file.

    On Vercel the filesystem is read-only and is discarded on every deploy, so a
    file-based enrolment appeared to succeed and then stopped validating after
    the next cold start. Reading it back through a fresh session, the way a new
    function instance would, is what proves that is fixed.
    """
    from app.db import SessionLocal
    from app.models import AdminTwoFactor

    _secret, _codes = enrolled
    with SessionLocal() as probe:
        row = probe.get(AdminTwoFactor, 1)

    assert row is not None, "the enrolment was not written to the database"
    assert row.secret
    assert row.recovery_hashes, "recovery codes were not stored"


def test_recovery_codes_are_stored_hashed_not_in_the_clear(enrolled):
    """A readable copy would defeat the point of a recovery code."""
    _secret, codes = enrolled
    from app.db import SessionLocal
    from app.models import AdminTwoFactor

    with SessionLocal() as probe:
        row = probe.get(AdminTwoFactor, 1)

    stored = list(row.recovery_hashes)
    for code in codes:
        assert code not in stored, f"{code} was stored in the clear"
        assert code not in str(stored), f"{code} appears in the clear in the row"
    assert len(stored) == len(codes)


def test_a_recovery_code_is_accepted_once_and_only_once(enrolled):
    _secret, codes = enrolled
    assert totp.consume_recovery_code(codes[0])
    assert not totp.consume_recovery_code(codes[0]), "a recovery code was reusable"
    assert totp.remaining_recovery_codes() == 4


def test_other_recovery_codes_still_work_after_one_is_used(enrolled):
    _secret, codes = enrolled
    assert totp.consume_recovery_code(codes[0])
    assert totp.consume_recovery_code(codes[1])


def test_a_wrong_recovery_code_is_refused_and_changes_nothing(enrolled):
    _secret, _codes = enrolled
    assert not totp.consume_recovery_code("AAAAA-BBBBB")
    assert totp.remaining_recovery_codes() == 5


def test_recovery_codes_avoid_ambiguous_characters(enrolled):
    _secret, codes = enrolled
    for code in codes:
        assert not set(code.upper()) & set("O0I1"), f"{code} contains an ambiguous character"


def test_clear_removes_the_enrolment(enrolled, tmp_path):
    totp.clear()
    assert not totp.is_enrolled()
    assert not (tmp_path / "admin_2fa.json").exists()


def test_a_corrupt_file_reads_as_not_enrolled(tmp_path, monkeypatch):
    """A bad write must not lock the admin out of their own panel."""
    monkeypatch.setattr(totp, "DATA_DIR", tmp_path)
    (tmp_path / "admin_2fa.json").write_text("{not json", encoding="utf-8")
    assert not totp.is_enrolled()
    assert totp.remaining_recovery_codes() == 0
    # And consuming one is a refusal, not a crash.
    assert not totp.consume_recovery_code("AAAAA-BBBBB")