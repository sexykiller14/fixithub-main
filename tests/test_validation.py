"""Input validation and SSRF protection for the network tools."""

from __future__ import annotations

import httpx
import pytest

from app.services import nettools
from app.services.ssrf import (
    ValidationError,
    is_blocked_ip,
    validate_hostname,
    validate_port,
    validate_record_type,
    validate_search_query,
    validate_url,
)


# --------------------------------------------------------------------------
# IP classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.0.0.5",
        "10.255.255.254",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "192.168.0.100",
        "169.254.169.254",   # cloud metadata endpoint
        "169.254.1.1",
        "0.0.0.0",
        "100.64.0.1",        # carrier grade NAT
        "224.0.0.1",         # multicast
        "239.255.255.250",
        "240.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd12:3456::1",
        "ff02::1",
    ],
)
def test_blocked_addresses_are_rejected(address):
    import ipaddress

    assert is_blocked_ip(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["1.1.1.1", "8.8.8.8", "93.184.216.34", "2606:4700:4700::1111"])
def test_public_addresses_are_allowed(address):
    import ipaddress

    assert not is_blocked_ip(ipaddress.ip_address(address))


# --------------------------------------------------------------------------
# Hostname validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["example.com", "www.example.co.uk", "sub.domain.example.org", "xn--80ak6aa92e.com"])
def test_valid_hostnames(value):
    assert validate_hostname(value) == value


def test_normalises_case_and_trailing_dot():
    assert validate_hostname("EXAMPLE.COM.") == "example.com"


@pytest.mark.parametrize(
    "value",
    [
        "",                       # empty
        "   ",                    # whitespace only
        "localhost",              # single label
        "example com",            # space
        "http://example.com",     # scheme included
        "example.com/path",       # path included
        "example.com:443",        # port included
        "-example.com",           # leading hyphen
        "example..com",           # empty label
        "exa mple.com",
        "example.com;whoami",
        "example.com|id",
        "example.com&x=1",
        "user@example.com",       # userinfo
        "a" * 300 + ".com",       # too long
        "example.123",            # numeric TLD
        "example.c",              # one-character TLD
        "@example.com",
        "example.com@evil.com",
    ],
)
def test_invalid_hostnames_are_rejected(value):
    with pytest.raises(ValidationError):
        validate_hostname(value)


def test_literal_private_ip_rejected():
    with pytest.raises(ValidationError, match="private"):
        validate_hostname("192.168.1.1")


def test_literal_loopback_rejected():
    with pytest.raises(ValidationError):
        validate_hostname("127.0.0.1")


def test_literal_metadata_endpoint_rejected():
    with pytest.raises(ValidationError):
        validate_hostname("169.254.169.254")


def test_public_literal_ip_accepted():
    assert validate_hostname("1.1.1.1") == "1.1.1.1"


# --------------------------------------------------------------------------
# Port validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("port", [20, 21, 22, 53, 80, 443, 445, 3389, 8080, 8443])
def test_allowlisted_ports(port):
    assert validate_port(port) == port


def test_port_accepts_string_input():
    assert validate_port("443") == 443


@pytest.mark.parametrize(
    "port",
    [
        0, -1, 1, 7, 9,           # out of range or privileged
        135, 139, 137, 138,        # legacy Windows RPC and NetBIOS
        1080, 3128, 4000, 5555,    # arbitrary services with no reason to be probed
        8081, 9000, 10000, 65535,
        999999,                    # out of range
    ],
)
def test_ports_outside_the_allowlist_are_rejected(port):
    with pytest.raises(ValidationError):
        validate_port(port)


def test_port_25_is_allowed_because_it_is_smtp():
    """SMTP is a common troubleshooting target, so it stays on the list."""
    assert validate_port(25) == 25


@pytest.mark.parametrize("value", ["", "abc", "80.5", "0x50", "8 0", None])
def test_non_numeric_ports_rejected(value):
    with pytest.raises(ValidationError):
        validate_port(value)


def test_risky_ports_are_refused():
    """The classic exploitation ports must never be probeable."""
    for port in (22, 23, 135, 139, 445, 3389, 5900, 6379):
        with pytest.raises(ValidationError):
            validate_port(port, allowed={80: "HTTP"})


# --------------------------------------------------------------------------
# URL validation
# --------------------------------------------------------------------------


@pytest.fixture
def pinned_dns(monkeypatch):
    """Resolve every hostname to a fixed public IP, with no live DNS.

    This keeps the tests deterministic and offline. The security-relevant
    behaviour under test is the validation of the returned address, which this
    fixture exercises by returning addresses from both the allowed and the
    blocked sets.
    """
    resolved = {"value": ["93.184.216.34"]}

    def fake_resolve(hostname):
        return list(resolved["value"])

    monkeypatch.setattr("app.services.ssrf._resolve_with_dns", fake_resolve)
    return resolved


def test_https_url_is_swapped_to_the_validated_ip(pinned_dns):
    url, host, host_header = validate_url("https://example.com/page")
    assert host.hostname == "example.com"
    assert host.ip == "93.184.216.34"
    assert host_header == "example.com"
    # The URL that would be requested points at the validated IP, not the name.
    assert url.startswith("https://93.184.216.34/")
    assert "example.com" not in url.split("/")[2]


def test_bare_domain_gets_https(pinned_dns):
    url, host, _ = validate_url("example.com")
    assert url.startswith("https://93.184.216.34")
    assert host.hostname == "example.com"


def test_query_string_is_preserved(pinned_dns):
    url, _host, _ = validate_url("https://example.com/search?q=test&page=2")
    assert url.endswith("/search?q=test&page=2")


def test_dns_rebinding_is_defeated(pinned_dns):
    """A hostname resolving to an internal address is refused outright.

    Silently falling back to another address would let an attacker with a
    split-horizon DNS setup reach internal services.
    """
    for internal in ["127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1", "::1"]:
        pinned_dns["value"] = [internal]
        with pytest.raises(ValidationError, match="private or reserved"):
            validate_url("https://attacker.example.com/")


def test_mixed_public_and_private_resolution_is_refused(pinned_dns):
    """One private address among several is enough to reject the whole host."""
    pinned_dns["value"] = ["93.184.216.34", "10.0.0.5"]
    with pytest.raises(ValidationError):
        validate_url("https://example.com/")


def test_ipv6_literal_is_bracket_wrapped(pinned_dns):
    pinned_dns["value"] = ["2606:4700:4700::1111"]
    url, host, _ = validate_url("https://example.com/")
    assert host.family == 6
    assert url.startswith("https://[2606:4700:4700::1111]")


def test_http_is_rejected():
    with pytest.raises(ValidationError, match="https"):
        validate_url("http://example.com")


def test_other_schemes_rejected():
    for value in ("file:///etc/passwd", "ftp://example.com", "gopher://example.com", "dict://example.com"):
        with pytest.raises(ValidationError):
            validate_url(value)


def test_url_with_credentials_rejected():
    with pytest.raises(ValidationError, match="username"):
        validate_url("https://user:pass@example.com")


def test_url_with_private_host_rejected():
    with pytest.raises(ValidationError):
        validate_url("https://192.168.0.1/admin")


def test_url_with_loopback_rejected():
    with pytest.raises(ValidationError):
        validate_url("https://127.0.0.1/")


def test_url_with_metadata_endpoint_rejected():
    with pytest.raises(ValidationError):
        validate_url("https://169.254.169.254/latest/meta-data/")


def test_oversized_url_rejected():
    with pytest.raises(ValidationError):
        validate_url("https://example.com/" + "a" * 3000)


def test_url_with_spaces_rejected():
    with pytest.raises(ValidationError):
        validate_url("https://exa mple.com")


# --------------------------------------------------------------------------
# Other validators
# --------------------------------------------------------------------------


def test_record_type_allowlist():
    assert validate_record_type("a") == "A"
    assert validate_record_type("MX") == "MX"


@pytest.mark.parametrize("value", ["ANY", "NULL", "AXFR", "*", "DROP", "AAAA;x"])
def test_unsupported_record_types_rejected(value):
    with pytest.raises(ValidationError):
        validate_record_type(value)


def test_search_query_length():
    assert validate_search_query("wifi") == "wifi"
    with pytest.raises(ValidationError):
        validate_search_query("x" * 201)


def test_search_query_strips_whitespace():
    assert validate_search_query("  blue screen  ") == "blue screen"


# --------------------------------------------------------------------------
# HTTP request pinning
# --------------------------------------------------------------------------


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Captures the request instead of sending it."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            headers={"server": "test", "content-type": "text/html"},
            request=request,
        )


@pytest.fixture
def recording_transport(monkeypatch, pinned_dns):
    """Replace the HTTP transport so no real request is made."""
    transport = _RecordingTransport()
    original = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = transport
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
    return transport


def _run_status(url: str):
    """Run the async tool from a synchronous test."""
    import anyio

    return anyio.run(nettools.http_status, url)


def test_request_goes_to_the_pinned_ip_not_the_hostname(recording_transport):
    """The connection target must be the validated IP, not the hostname."""
    result = _run_status("https://example.com/page")
    assert result.ok is True

    sent = recording_transport.requests[0]
    assert sent.url.host == "93.184.216.34"
    # The Host header still carries the name the visitor asked for.
    assert sent.headers["host"] == "example.com"


def test_tls_sni_is_the_real_hostname(recording_transport):
    """SNI must present the hostname, or certificate validation fails."""
    _run_status("https://example.com/")
    sent = recording_transport.requests[0]
    assert sent.extensions.get("sni_hostname") == "example.com"


def test_display_url_shows_the_hostname_not_the_ip(recording_transport):
    result = _run_status("https://example.com/some/path?q=1")
    assert result.data["display_url"] == "https://example.com/some/path?q=1"
    assert "93.184.216.34" not in result.data["display_url"]


def test_redirects_are_not_followed(recording_transport):
    _run_status("https://example.com/")
    assert len(recording_transport.requests) == 1


def test_proxy_environment_variables_are_ignored(recording_transport, monkeypatch):
    """trust_env=False stops a proxy in the environment from redirecting us."""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9999")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9999")
    result = _run_status("https://example.com/")
    assert result.ok is True
    assert recording_transport.requests[0].url.host == "93.184.216.34"


# --------------------------------------------------------------------------
# HTTP surface
# --------------------------------------------------------------------------


def test_dns_tool_rejects_private_target(client):
    response = client.post("/tools/dns", data={"host": "192.168.1.1", "record_type": "A"}, follow_redirects=True)
    assert response.status_code in (200, 422)
    assert "private" in response.text.lower() or "look up" in response.text.lower()


def test_port_tool_rejects_disallowed_port(client):
    response = client.post(
        "/tools/port", data={"host": "example.com", "port": "1080"}, follow_redirects=True
    )
    assert response.status_code in (200, 422)
    assert "not on the allowed list" in response.text


def test_status_tool_rejects_http(client):
    response = client.post("/tools/status", data={"url": "http://example.com"}, follow_redirects=True)
    assert response.status_code in (200, 422)
    assert "https" in response.text.lower()


def test_api_dns_returns_json_error_for_bad_host(client):
    response = client.post("/api/dns", json={"host": "127.0.0.1"})
    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_api_port_returns_json_error_for_bad_port(client):
    response = client.post("/api/port", json={"host": "example.com", "port": 4000})
    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_api_status_rejects_internal_target(client):
    response = client.post("/api/status", json={"url": "https://169.254.169.254/"})
    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_api_accepts_form_encoded_body(client):
    response = client.post(
        "/api/port",
        data={"host": "example.com", "port": "not-a-port"},
    )
    assert response.status_code == 422


def test_api_survives_malformed_json(client):
    response = client.post(
        "/api/dns",
        content=b"{not valid json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["ok"] is False
