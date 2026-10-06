"""Network diagnostic tools: DNS, public IP, port check, HTTP status, latency.

Every function here uses Python libraries only. Nothing invokes a shell, and
every target goes through :mod:`app.services.ssrf` validation first.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
import statistics
import time
from urllib.parse import urlsplit
from dataclasses import dataclass, field

import dns.asyncresolver
import dns.exception
import dns.rdatatype
import httpx

from ..config import ALLOWED_PORTS, settings
from .ssrf import (
    ValidationError,
    validate_hostname,
    validate_port,
    validate_record_type,
    validate_url,
)

RECORD_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA")

PUBLIC_IP_ENDPOINTS = (
    "https://api.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://checkip.amazonaws.com",
)

GEO_ENDPOINTS = (
    "https://ipapi.co/{ip}/json/",
    "https://ipwho.is/{ip}",
)


class ToolError(Exception):
    """A tool failed in a way worth showing the user."""


@dataclass
class ToolResult:
    ok: bool = True
    data: dict = field(default_factory=dict)
    error: str = ""


def _clean_timeout(seconds: float) -> float:
    return max(1.0, min(float(seconds), 30.0))


# --------------------------------------------------------------------------
# DNS
# --------------------------------------------------------------------------


async def dns_lookup(hostname: str, record_type: str = "A") -> ToolResult:
    """Resolve a hostname and return the records for one type."""
    host = validate_hostname(hostname)
    rdtype = validate_record_type(record_type)
    timeout = _clean_timeout(settings.dns_timeout)

    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = timeout
    resolver.timeout = timeout

    started = time.perf_counter()
    try:
        answer = await resolver.resolve(host, rdtype, raise_on_no_answer=False)
    except dns.resolver.NXDOMAIN:
        return ToolResult(ok=False, error=f"{host} does not exist in DNS (NXDOMAIN).")
    except dns.resolver.NoAnswer:
        return ToolResult(ok=False, error=f"No {rdtype} records exist for {host}.")
    except dns.resolver.NoNameservers:
        return ToolResult(
            ok=False,
            error="No nameserver answered. This is often a DNS configuration problem on the network.",
        )
    except (dns.exception.Timeout, dns.exception.DNSException, OSError) as exc:
        return ToolResult(ok=False, error=f"DNS lookup failed: {type(exc).__name__}.")
    elapsed = (time.perf_counter() - started) * 1000

    records = []
    ttl = None
    for record in answer:
        if ttl is None:
            ttl = getattr(record, "ttl", None)
        records.append(str(record).strip())

    if not records:
        return ToolResult(ok=False, error=f"No {rdtype} records found for {host}.")

    return ToolResult(
        data={
            "hostname": host,
            "record_type": rdtype,
            "records": records,
            "count": len(records),
            "ttl": ttl,
            "elapsed_ms": round(elapsed, 1),
            "resolver": "system nameservers",
        }
    )


# --------------------------------------------------------------------------
# Public IP
# --------------------------------------------------------------------------


async def _fetch_text(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = await client.get(url, headers={"User-Agent": "FixIT-Hub/1.0"})
        response.raise_for_status()
        return response.text.strip()


async def _fetch_json(url: str) -> dict:
    async with httpx.AsyncClient(
        timeout=settings.http_timeout,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = await client.get(url, headers={"User-Agent": "FixIT-Hub/1.0"})
        response.raise_for_status()
        return response.json()


async def public_ip_info() -> ToolResult:
    """Look up the caller's public IP address via well-known echo services."""
    address = None
    errors: list[str] = []
    for endpoint in PUBLIC_IP_ENDPOINTS:
        try:
            address = await _fetch_text(endpoint)
            break
        except (httpx.HTTPError, httpx.InvalidURL, ValueError, OSError) as exc:
            errors.append(f"{endpoint.split('/')[2]}: {type(exc).__name__}")

    if not address:
        return ToolResult(
            ok=False,
            error="Could not reach any public IP service. " + "; ".join(errors),
        )

    info: dict = {"ip": address}
    for template in GEO_ENDPOINTS:
        try:
            payload = await _fetch_json(template.format(ip=address))
        except (httpx.HTTPError, ValueError, OSError, KeyError):
            continue
        if not isinstance(payload, dict):
            continue
        info.update(
            {
                "city": payload.get("city") or payload.get("region") or "",
                "region": payload.get("region_name") or payload.get("region") or "",
                "country": payload.get("country") or payload.get("country_code") or "",
                "country_code": payload.get("country_code") or "",
                "org": payload.get("org") or payload.get("connection", {}).get("org", "")
                if isinstance(payload.get("connection"), dict)
                else (payload.get("org") or ""),
                "timezone": payload.get("timezone") or "",
                "asn": payload.get("asn") or "",
                "latitude": payload.get("latitude") or payload.get("lat") or "",
                "longitude": payload.get("longitude") or payload.get("lon") or "",
            }
        )
        break

    return ToolResult(data=info)


# --------------------------------------------------------------------------
# Port checker
# --------------------------------------------------------------------------


async def _tcp_connect(host: str, ip: str, port: int, timeout: float) -> tuple[str, float]:
    """Connect to the pre-validated IP while preserving SNI/Host semantics."""
    loop = asyncio.get_running_loop()
    started = time.perf_counter()
    try:
        connection = await asyncio.wait_for(
            loop.create_connection(
                lambda: _PinnedProtocol(host, ip),
                host=ip,
                port=port,
            ),
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - started) * 1000
        transport, _ = connection
        transport.close()
        return "open", round(elapsed, 1)
    except asyncio.TimeoutError:
        return "timeout", round((time.perf_counter() - started) * 1000, 1)
    except (OSError, socket.gaierror):
        elapsed = (time.perf_counter() - started) * 1000
        return "closed", round(elapsed, 1)


class _PinnedProtocol(asyncio.Protocol):
    """A plain TCP protocol that documents the pinned-IP intent."""

    def __init__(self, hostname: str, ip: str) -> None:
        self.hostname = hostname
        self.ip = ip

    def connection_made(self, transport) -> None:  # pragma: no cover - network path
        transport.close()


async def port_check(hostname: str, port_value) -> ToolResult:
    """Check one allowlisted TCP port on a validated public host."""
    from .ssrf import resolve_public_ip

    host = resolve_public_ip(validate_hostname(hostname))
    port = validate_port(port_value)
    timeout = _clean_timeout(settings.socket_timeout)

    state, elapsed = await _tcp_connect(host.hostname, host.ip, port, timeout)

    explanations = {
        "open": "The port accepted a connection. Something is listening.",
        "closed": "The host actively refused the connection. Nothing is listening, or a firewall rejected it.",
        "timeout": "No response before the timeout. The port is filtered, or the host is not responding.",
    }
    return ToolResult(
        data={
            "host": host.hostname,
            "ip": host.ip,
            "port": port,
            "service": ALLOWED_PORTS.get(port, "unknown"),
            "state": state,
            "state_label": state.capitalize(),
            "explanation": explanations[state],
            "elapsed_ms": elapsed,
        }
    )


# --------------------------------------------------------------------------
# HTTP status
# --------------------------------------------------------------------------


async def http_status(url: str, method: str = "GET") -> ToolResult:
    """Fetch a validated https URL and report its status code and timing."""
    safe_url, host, host_header = validate_url(url, require_https=True)
    safe_method = method.strip().upper()
    if safe_method not in {"GET", "HEAD"}:
        safe_method = "GET"

    # What the visitor typed, shown back to them. The IP-pinned URL is an
    # internal detail of how the request is made.
    display_url = f"https://{host_header}{_safe_url_path(safe_url)}"

    headers = {
        "User-Agent": "FixIT-Hub/1.0 (status checker)",
        "Accept": "*/*",
        "Host": host_header,
        "Accept-Encoding": "identity",
    }
    # The connection goes to the validated IP, but TLS must still present the
    # real hostname as SNI and verify the certificate against that name.
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(
            timeout=settings.http_timeout,
            follow_redirects=False,
            trust_env=False,
            verify=True,
            limits=httpx.Limits(max_connections=4),
        ) as client:
            if safe_method == "HEAD":
                request = client.build_request("HEAD", safe_url, headers=headers)
            else:
                request = client.build_request("GET", safe_url, headers=headers)
            request.extensions = {"sni_hostname": host.hostname}
            response = await client.send(request, stream=True)
            content_length = response.headers.get("content-length")
            server = response.headers.get("server")
            content_type = response.headers.get("content-type")
            status = response.status_code
            location = response.headers.get("location")
            protocol = response.http_version
            await response.aclose()
        elapsed = (time.perf_counter() - started) * 1000

        return ToolResult(
            data={
                "url": safe_url,
                "display_url": display_url,
                "hostname": host.hostname,
                "ip": host.ip,
                "method": safe_method,
                "status": status,
                "status_text": _status_text(status),
                "healthy": 200 <= status < 400,
                "server": server or "unknown",
                "content_type": content_type or "",
                "content_length": content_length,
                "redirect_to": location,
                "protocol": protocol,
                "elapsed_ms": round(elapsed, 1),
            }
        )
    except httpx.TooManyRedirects:
        return ToolResult(ok=False, error="The site sent too many redirects.")
    except httpx.ConnectError as exc:
        return ToolResult(
            ok=False,
            error=(
                f"Could not connect to {host.hostname}. It refused the connection, "
                f"or nothing is listening on that port. ({type(exc).__name__})"
            ),
        )
    except httpx.TimeoutException:
        return ToolResult(
            ok=False,
            error=(
                f"No response from {host.hostname} within "
                f"{int(settings.http_timeout)} seconds."
            ),
        )
    except httpx.HTTPStatusError as exc:
        return ToolResult(
            ok=False,
            error=(
                f"The site responded but the connection failed during TLS "
                f"negotiation ({type(exc).__name__})."
            ),
        )
    except httpx.HTTPError as exc:
        return ToolResult(ok=False, error=f"Request failed: {type(exc).__name__}.")
    except ssl.SSLError:
        return ToolResult(
            ok=False,
            error=(
                f"TLS negotiation with {host.hostname} failed. The certificate may be "
                "expired, self-signed, or the site may only accept newer TLS versions."
            ),
        )
    except (ValueError, OSError) as exc:
        return ToolResult(ok=False, error=f"Request failed: {type(exc).__name__}.")


def _safe_url_path(safe_url: str) -> str:
    """Path and query from the IP-pinned URL, for building the display URL."""
    parts = urlsplit(safe_url)
    path = parts.path if parts.path and parts.path != "/" else ""
    return f"{path}?{parts.query}" if parts.query else path


def _status_text(status: int) -> str:
    table = {
        200: "OK",
        201: "Created",
        204: "No Content",
        301: "Moved Permanently",
        302: "Found",
        304: "Not Modified",
        307: "Temporary Redirect",
        308: "Permanent Redirect",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        408: "Request Timeout",
        410: "Gone",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }
    return table.get(status, "")


# --------------------------------------------------------------------------
# Latency
# --------------------------------------------------------------------------


def _icmp_echo_not_available() -> ToolResult:
    return ToolResult(
        ok=False,
        error=(
            "ICMP ping needs elevated privileges on Windows, which this web "
            "app deliberately does not request. Use the TCP latency test "
            "instead, which needs no special privileges."
        ),
    )


async def tcp_latency(hostname: str, port_value=443, attempts: int = 4) -> ToolResult:
    """Measure TCP connect latency to a validated public host."""
    from .ssrf import resolve_public_ip

    host = resolve_public_ip(validate_hostname(hostname))
    port = validate_port(port_value)
    count = max(2, min(int(attempts), 8))
    timeout = _clean_timeout(settings.socket_timeout)

    samples: list[float] = []
    failures = 0
    for _ in range(count):
        state, elapsed = await _tcp_connect(host.hostname, host.ip, port, timeout)
        if state == "open":
            samples.append(elapsed)
        else:
            failures += 1
        await asyncio.sleep(0.15)

    if not samples:
        return ToolResult(
            ok=False,
            error=f"Could not connect to {host.hostname}:{port} on any of {count} attempts.",
        )

    samples.sort()
    data = {
        "host": host.hostname,
        "ip": host.ip,
        "port": port,
        "service": ALLOWED_PORTS.get(port, "unknown"),
        "attempts": count,
        "failures": failures,
        "min_ms": round(samples[0], 1),
        "max_ms": round(samples[-1], 1),
        "avg_ms": round(statistics.fmean(samples), 1),
        "median_ms": round(statistics.median(samples), 1),
        "jitter_ms": round(samples[-1] - samples[0], 1),
        "method": "TCP connect",
    }
    data["verdict"] = _latency_verdict(data["median_ms"])
    return ToolResult(data=data)


def _latency_verdict(median_ms: float) -> str:
    if median_ms < 30:
        return "Excellent. Typical for a nearby server on a wired connection."
    if median_ms < 80:
        return "Good. Normal for most home broadband."
    if median_ms < 150:
        return "Fair. Common on Wi-Fi or a long distance to the server."
    if median_ms < 300:
        return "Slow. Worth checking for Wi-Fi congestion or heavy background traffic."
    return "Very slow. Expect noticeable lag and poor call quality on this path."
