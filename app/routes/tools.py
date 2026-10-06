"""Network diagnostic tools: pages, JSON APIs and rate limiting.

All routes here are async so they share the event loop with the httpx and
dnspython calls they make.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..config import ALLOWED_PORTS, settings
from ..db import get_db
from ..deps import build_context, total_counts
from ..rate_limit import enforce, tool_limiter
from ..services import nettools
from ..services.ssrf import (
    ValidationError,
    validate_hostname,
    validate_port,
    validate_record_type,
    validate_search_query,
)
from ..templates import render

router = APIRouter()

PORT_CHOICES = [(str(port), f"{port} - {name}") for port, name in sorted(ALLOWED_PORTS.items())]
RECORD_CHOICES = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"]


def _limit(request: Request):
    """Apply the shared 10-per-minute limit. Returns a 429 response or None."""
    return enforce(
        request,
        tool_limiter,
        prefix="tool",
        message=(
            f"Rate limit reached: {settings.rate_limit_max} tool requests per "
            f"{settings.rate_limit_window} seconds. Try again shortly."
        ),
    )


def _context(request: Request, db: Session, **extra):
    return build_context(
        request,
        db,
        nav_open="tools",
        rate_limit_max=settings.rate_limit_max,
        rate_limit_window=settings.rate_limit_window,
        port_choices=PORT_CHOICES,
        record_choices=RECORD_CHOICES,
        counts=total_counts(db),
        **extra,
    )


@router.get("/tools", name="tools_index")
async def tools_index(request: Request, db: Session = Depends(get_db)):
    """Landing page for the five network tools. Making no request, so not limited."""
    return render(request, "tools_index.html", _context(request, db))


async def _safe(call, *args) -> tuple[object, str]:
    """Run a service function, converting failures into a user-facing message."""
    try:
        result = await call(*args)
    except ValidationError as exc:
        return None, str(exc)
    except Exception as exc:  # noqa: BLE001 - never surface a traceback
        return None, f"That check could not be completed: {type(exc).__name__}."
    if not result.ok:
        return None, result.error or "That check did not return a result."
    return result, ""


# ------------------------------------------------------------------- DNS


@router.get("/tools/dns", name="tool_dns")
async def tool_dns(
    request: Request,
    host: str = Query("", max_length=253),
    record_type: str = Query("A", max_length=10),
    db: Session = Depends(get_db),
):
    return await _dns_page(request, db, host, record_type)


@router.post("/tools/dns", name="tool_dns_post")
async def tool_dns_post(
    request: Request,
    host: str = Form("", max_length=253),
    record_type: str = Form("A", max_length=10),
    db: Session = Depends(get_db),
):
    limited = _limit(request)
    if limited is not None:
        return limited
    return await _dns_page(request, db, host, record_type)


async def _dns_page(request: Request, db: Session, host: str, record_type: str):
    clean_host = (host or "").strip()
    clean_type = (record_type or "A").strip().upper() or "A"
    result, error = None, ""

    if clean_host:
        result, error = await _safe(
            nettools.dns_lookup,
            clean_host,
            clean_type if clean_type in RECORD_CHOICES else "A",
        )

    return render(
        request,
        "tools_dns.html",
        _context(
            request,
            db,
            host=clean_host,
            record_type=clean_type,
            result=result,
            error=error,
        ),
    )


# --------------------------------------------------------------- public IP


@router.get("/tools/ip", name="tool_ip")
async def tool_ip(request: Request, db: Session = Depends(get_db)):
    limited = _limit(request)
    if limited is not None:
        return limited

    result, error = await _safe(nettools.public_ip_info)
    return render(request, "tools_ip.html", _context(request, db, result=result, error=error))


# ------------------------------------------------------------------ ports


@router.get("/tools/port", name="tool_port")
async def tool_port(
    request: Request,
    host: str = Query("", max_length=253),
    port: str = Query("", max_length=8),
    db: Session = Depends(get_db),
):
    return await _port_page(request, db, host, port)


@router.post("/tools/port", name="tool_port_post")
async def tool_port_post(
    request: Request,
    host: str = Form("", max_length=253),
    port: str = Form("", max_length=8),
    db: Session = Depends(get_db),
):
    limited = _limit(request)
    if limited is not None:
        return limited
    return await _port_page(request, db, host, port)


async def _port_page(request: Request, db: Session, host: str, port: str):
    clean_host = (host or "").strip()
    clean_port = (port or "").strip()
    result, error = None, ""

    if clean_host and clean_port:
        result, error = await _safe(nettools.port_check, clean_host, clean_port)
    elif clean_host or clean_port:
        error = "Enter both a host and a port."

    return render(
        request,
        "tools_port.html",
        _context(
            request, db, host=clean_host, port=clean_port, result=result, error=error
        ),
    )


# ------------------------------------------------------------- HTTP status


@router.get("/tools/status", name="tool_status")
async def tool_status(
    request: Request,
    url: str = Query("", max_length=2048),
    db: Session = Depends(get_db),
):
    return await _status_page(request, db, url)


@router.post("/tools/status", name="tool_status_post")
async def tool_status_post(
    request: Request,
    url: str = Form("", max_length=2048),
    db: Session = Depends(get_db),
):
    limited = _limit(request)
    if limited is not None:
        return limited
    return await _status_page(request, db, url)


async def _status_page(request: Request, db: Session, url: str):
    clean = (url or "").strip()
    result, error = None, ""
    if clean:
        result, error = await _safe(nettools.http_status, clean)
    return render(
        request,
        "tools_status.html",
        _context(request, db, url=clean, result=result, error=error),
    )


# ----------------------------------------------------------------- latency


@router.get("/tools/latency", name="tool_latency")
async def tool_latency(
    request: Request,
    host: str = Query("", max_length=253),
    port: str = Query("443", max_length=8),
    db: Session = Depends(get_db),
):
    return await _latency_page(request, db, host, port)


@router.post("/tools/latency", name="tool_latency_post")
async def tool_latency_post(
    request: Request,
    host: str = Form("", max_length=253),
    port: str = Form("443", max_length=8),
    db: Session = Depends(get_db),
):
    limited = _limit(request)
    if limited is not None:
        return limited
    return await _latency_page(request, db, host, port)


async def _latency_page(request: Request, db: Session, host: str, port: str):
    clean_host = (host or "").strip()
    clean_port = (port or "443").strip() or "443"
    result, error = None, ""
    if clean_host:
        result, error = await _safe(nettools.tcp_latency, clean_host, clean_port, 4)
    return render(
        request,
        "tools_latency.html",
        _context(
            request, db, host=clean_host, port=clean_port, result=result, error=error
        ),
    )


# ---------------------------------------------------------------- JSON APIs


def _json_error(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=code, content={"ok": False, "error": message})


def _json_result(result, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code if result.ok else 502,
        content={"ok": result.ok, "data": result.data, "error": result.error},
    )


async def _payload(request: Request) -> dict:
    """Accept a JSON or form body, returning {} rather than raising."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 - treat malformed JSON as empty
            return {}
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return {}
    return {key: form.get(key) for key in form.keys()}


@router.post("/api/dns", name="api_dns")
async def api_dns(request: Request):
    limited = _limit(request)
    if limited is not None:
        return limited

    body = await _payload(request)
    host = str(body.get("host", ""))
    record_type = str(body.get("record_type", "A"))[:10]

    try:
        clean = validate_hostname(validate_search_query(host) or host)
        clean_type = validate_record_type(record_type)
        result = await nettools.dns_lookup(clean, clean_type)
    except ValidationError as exc:
        return _json_error(str(exc), 422)
    return _json_result(result)


@router.post("/api/port", name="api_port")
async def api_port(request: Request):
    limited = _limit(request)
    if limited is not None:
        return limited

    body = await _payload(request)
    try:
        host = validate_hostname(str(body.get("host", "")))
        port = validate_port(body.get("port"))
        result = await nettools.port_check(host, port)
    except ValidationError as exc:
        return _json_error(str(exc), 422)
    return _json_result(result)


@router.post("/api/status", name="api_status")
async def api_status(request: Request):
    limited = _limit(request)
    if limited is not None:
        return limited

    body = await _payload(request)
    url = str(body.get("url", ""))
    try:
        result = await nettools.http_status(url)
    except ValidationError as exc:
        return _json_error(str(exc), 422)
    return _json_result(result)


@router.post("/api/latency", name="api_latency")
async def api_latency(request: Request):
    limited = _limit(request)
    if limited is not None:
        return limited

    body = await _payload(request)
    try:
        host = validate_hostname(str(body.get("host", "")))
        port = validate_port(body.get("port", 443))
        result = await nettools.tcp_latency(host, port, 4)
    except ValidationError as exc:
        return _json_error(str(exc), 422)
    return _json_result(result)
