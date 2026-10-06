"""Input validation and SSRF protection for the network tools.

Design notes
------------
* Nothing here ever shells out. No subprocess, no os.system, no shell strings.
* Hostnames are resolved before use and every returned address is checked.
* When a hostname resolves to several addresses, the *first* public address is
  used for the actual connection and passed to httpx as an explicit IP, with
  the original Host header and TLS SNI preserved. This closes the DNS
  rebinding window between validation and connection.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import dns.exception
import dns.rdatatype
import dns.resolver

from ..config import ALLOWED_PORTS, settings

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?!-)[a-zA-Z0-9-]{1,63}(?<!-)"
    r"(?:\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*\.?$"
)

# Reserved and special-use ranges that must never be reachable.
BLOCKED_NETWORKS: tuple[ipaddress._BaseNetwork, ...] = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",            # this network
        "10.0.0.0/8",           # private
        "100.64.0.0/10",        # carrier grade NAT
        "127.0.0.0/8",          # loopback
        "169.254.0.0/16",       # link local, incl. cloud metadata
        "172.16.0.0/12",        # private
        "192.0.0.0/24",         # IETF protocol assignments
        "192.0.2.0/24",         # documentation
        "192.88.99.0/24",       # 6to4 relay anycast
        "192.168.0.0/16",       # private
        "198.18.0.0/15",        # benchmarking
        "198.51.100.0/24",      # documentation
        "203.0.113.0/24",       # documentation
        "224.0.0.0/4",          # multicast
        "240.0.0.0/4",          # reserved, incl. 255.255.255.255
        "::/128",               # unspecified
        "::1/128",              # loopback
        "64:ff9b::/96",         # NAT64
        "100::/64",             # discard prefix
        "2001::/32",            # Teredo
        "2001:db8::/32",        # documentation
        "fc00::/7",             # unique local
        "fe80::/10",            # link local
        "ff00::/8",             # multicast
    )
)

ALLOWED_SCHEMES = {"http", "https"}


class ValidationError(ValueError):
    """Raised when user input fails validation, with a user-facing message."""


@dataclass
class ResolvedHost:
    """A hostname that has been validated and mapped to a safe IP."""

    hostname: str
    ip: str
    family: int
    all_addresses: list[str]

    @property
    def port(self) -> int:
        return 443 if self.family == 6 else 80


def is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    """True when an address is private, reserved or otherwise not routable."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    return any(ip in net for net in BLOCKED_NETWORKS)


def validate_port(value, allowed: dict[int, str] | None = None) -> int:
    """Validate a TCP port against the strict allowlist."""
    allowed_ports = ALLOWED_PORTS if allowed is None else allowed
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValidationError("Port must be a whole number.") from None
    if not 1 <= port <= 65535:
        raise ValidationError("Port must be between 1 and 65535.")
    if port not in allowed_ports:
        popular = ", ".join(str(p) for p in sorted(allowed_ports)[:12])
        raise ValidationError(
            f"Port {port} is not on the allowed list for safety. "
            f"Allowed ports include: {popular} and others."
        )
    return port


def validate_hostname(raw: str) -> str:
    """Validate and normalise a hostname or IP literal."""
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Enter a hostname or IP address.")
    if len(text) > settings.max_dns_name_length:
        raise ValidationError(
            f"Hostnames must be {settings.max_dns_name_length} characters or fewer."
        )
    if any(ch.isspace() for ch in text):
        raise ValidationError("Hostnames cannot contain spaces.")
    # Reject anything that looks like a URL, port, or injection attempt.
    if any(ch in text for ch in "/\\?#@[]%'\"<>;|&$`(){}"):
        raise ValidationError("Enter only a hostname, for example example.com")
    if text.startswith("-"):
        raise ValidationError("Enter only a hostname, for example example.com")

    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        pass
    else:
        if is_blocked_ip(address):
            raise ValidationError(
                "That address is private, local or reserved, so it cannot be checked."
            )
        return str(address)

    text = text.rstrip(".")
    lowered = text.lower()
    if not HOSTNAME_RE.match(lowered):
        raise ValidationError(
            "That does not look like a valid hostname. Use something like example.com"
        )
    if "." not in lowered:
        raise ValidationError(
            "Enter a fully qualified hostname such as example.com, not a single label."
        )
    tld = lowered.rsplit(".", 1)[1]
    if len(tld) < 2 or not tld.isalpha():
        raise ValidationError("That hostname does not end in a valid domain.")
    return lowered


def _resolve_with_dns(hostname: str) -> list[str]:
    """Resolve using dnspython so we can enforce a timeout cleanly."""
    resolver = dns.resolver.Resolver()
    resolver.lifetime = settings.dns_timeout
    resolver.timeout = settings.dns_timeout
    records: list[str] = []
    for rdtype in (dns.rdatatype.A, dns.rdatatype.AAAA):
        try:
            answer = resolver.resolve(hostname, rdtype, raise_on_no_answer=False)
        except (dns.exception.DNSException, OSError):
            continue
        for record in answer:
            records.append(str(record).strip())
    return records


def resolve_public_ip(hostname: str) -> ResolvedHost:
    """Resolve a hostname and confirm every address is publicly routable."""
    clean = validate_hostname(hostname)

    try:
        ipaddress.ip_address(clean)
    except ValueError:
        resolved = _resolve_with_dns(clean)
        if not resolved:
            # Fall back to the system resolver, then validate what it returns.
            try:
                infos = socket.getaddrinfo(clean, None, proto=socket.IPPROTO_TCP)
            except (socket.gaierror, UnicodeError, OSError):
                raise ValidationError(f"Could not resolve {clean}. Check the spelling.") from None
            resolved = sorted({info[4][0] for info in infos})
        if not resolved:
            raise ValidationError(f"Could not resolve {clean}. Check the spelling.")
    else:
        resolved = [clean]

    unique = list(dict.fromkeys(resolved))
    safe: list[str] = []
    for address in unique:
        parsed = ipaddress.ip_address(address)
        if is_blocked_ip(parsed):
            # Do not silently fall back to a different address: a hostname that
            # resolves to a private address is a deliberate SSRF attempt.
            raise ValidationError(
                f"{clean} resolves to a private or reserved address ({address}), "
                "which cannot be checked."
            )
        safe.append(address)

    first = ipaddress.ip_address(safe[0])
    return ResolvedHost(
        hostname=clean,
        ip=safe[0],
        family=first.version,
        all_addresses=safe,
    )


def validate_url(raw: str, require_https: bool = True) -> tuple[str, ResolvedHost, str]:
    """Validate a URL, resolve the host safely.

    Returns ``(safe_url, host, host_header)``. ``safe_url`` has its host swapped
    for the already-validated IP address, so the request that httpx makes
    cannot be redirected to an internal target after validation. ``host_header``
    keeps the original hostname for the Host header and TLS SNI.
    """
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Enter a URL to check.")
    if len(text) > 2048:
        raise ValidationError("URLs must be 2048 characters or fewer.")
    if any(ch.isspace() for ch in text):
        raise ValidationError("URLs cannot contain spaces.")
    if not re.match(r"(?i)^https?://", text):
        text = f"https://{text}"

    parts = urlsplit(text)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValidationError("Only http and https URLs can be checked.")
    if require_https and parts.scheme.lower() != "https":
        raise ValidationError("Only https URLs can be checked, so the request cannot be intercepted.")
    if parts.username or parts.password:
        raise ValidationError("URLs with usernames or passwords are not accepted.")

    hostname = parts.hostname or ""
    host = resolve_public_ip(hostname)

    port = 443 if host.family == 6 else 80
    if parts.port:
        raw_port = parts.port
        if raw_port != port and raw_port not in (80, 443):
            raise ValidationError("Only ports 80 and 443 can be checked.")

    netloc = f"[{host.ip}]" if host.family == 6 else host.ip
    if parts.port and parts.port != port:
        netloc = f"{netloc}:{parts.port}"
        port = parts.port

    safe_url = urlunsplit(
        (parts.scheme.lower(), netloc, parts.path or "/", parts.query, "")
    )
    host_header = hostname if not parts.port else f"{hostname}:{parts.port}"
    return safe_url, host, host_header


def validate_search_query(raw: str) -> str:
    """Trim and length-check a site search term."""
    text = (raw or "").strip()
    if len(text) > settings.max_query_length:
        raise ValidationError(
            f"Search terms must be {settings.max_query_length} characters or fewer."
        )
    return text


def validate_record_type(raw: str) -> str:
    """Validate a DNS record type against a fixed allowlist."""
    allowed = {"A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "PTR", "CAA"}
    text = (raw or "A").strip().upper()
    if text not in allowed:
        raise ValidationError(
            f"Record type must be one of: {', '.join(sorted(allowed))}"
        )
    return text
