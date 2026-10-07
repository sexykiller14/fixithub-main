"""Application configuration.

All settings come from environment variables so the app can be configured
without touching code. Sensible development defaults are provided, but a
strong SECRET_KEY and ADMIN_PASSWORD are mandatory in production.
"""

from __future__ import annotations

import os
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

BASE_DIR = Path(__file__).resolve().parent.parent
CONTENT_DIR = BASE_DIR / "content"
DATA_DIR = BASE_DIR / "data"
WIZARDS_DIR = DATA_DIR / "wizards"
SCRIPTS_DIR = BASE_DIR / "scripts_download"

# On serverless platforms (e.g. Vercel), the root filesystem is read-only.
# Mutable files (uploads, admin hash, SQLite database) fall back to the system temp directory.
_default_apps_dir = Path(tempfile.gettempdir()) / "apps_download" if IS_SERVERLESS else BASE_DIR / "apps_download"
APPS_DIR = Path(os.environ.get("FIXITHUB_APPS_DIR", str(_default_apps_dir))).resolve()
IMAGES_DIR = APPS_DIR / "screenshots"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"

if (DATA_DIR / "admin.json").is_file():
    ADMIN_HASH_FILE = DATA_DIR / "admin.json"
elif IS_SERVERLESS:
    ADMIN_HASH_FILE = Path(tempfile.gettempdir()) / "admin.json"
else:
    ADMIN_HASH_FILE = DATA_DIR / "admin.json"

# Cookie holding the signed-in reader's opaque session token. Distinct from the
# admin cookie on purpose: a reader account must never satisfy an admin check.
USER_SESSION_COOKIE = "fixithub_user"
ADMIN_SESSION_COOKIE = "fixithub_admin"

# Site metadata used in <head>, sitemap.xml and JSON-LD.
SITE_NAME = "FixIT Hub"
SITE_TAGLINE = "Diagnose and fix PC problems yourself"
SITE_DESCRIPTION = (
    "Free, beginner-friendly technical support for Windows 10 and 11: "
    "BSOD stop code lookup with minidump analysis, guided troubleshooting "
    "wizards, driver guides, hardware diagnostics and safe network tools."
)
SITE_AUTHOR = "FixIT Hub"
SITE_URL = os.environ.get("FIXITHUB_SITE_URL", "http://localhost:8000").rstrip("/")

# Category definitions. `slug` is used in URLs, `name` in the UI.
CATEGORIES: dict[str, dict[str, str]] = {
    "hardware": {
        "name": "Hardware",
        "blurb": "RAM, SSDs, GPUs, PSUs, temperatures and beep codes",
        "icon": "cpu",
    },
    "network": {
        "name": "Network",
        "blurb": "Wi-Fi, Ethernet, DNS, VPNs and connection dropouts",
        "icon": "wifi",
    },
    "windows": {
        "name": "Windows",
        "blurb": "Updates, activation, slow performance and system files",
        "icon": "window",
    },
    "drivers": {
        "name": "Drivers",
        "blurb": "GPU, chipset, Wi-Fi and audio drivers, plus Device Manager",
        "icon": "chip",
    },
    "bsod": {
        "name": "Blue Screen (BSOD)",
        "blurb": "Stop code lookup, minidump analysis and repair paths",
        "icon": "alert",
    },
}

DIFFICULTY_LABELS = {
    "easy": "Easy",
    "moderate": "Moderate",
    "hard": "Hard",
    "advanced": "Advanced",
}

# Ports the port checker is allowed to probe. Anything else is rejected.
ALLOWED_PORTS: dict[int, str] = {
    20: "FTP-DATA",
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    67: "DHCP",
    68: "DHCP",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    465: "SMTPS",
    587: "SMTP-Submission",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    3306: "MySQL",
    3389: "RDP",
    5060: "SIP",
    5432: "PostgreSQL",
    5900: "VNC",
    5985: "WinRM",
    6379: "Redis",
    8000: "HTTP-Alt",
    8080: "HTTP-Proxy",
    8443: "HTTPS-Alt",
    27017: "MongoDB",
}

# Vendor pages. Only official vendor domains are ever linked.
VENDORS: dict[str, dict[str, str]] = {
    "nvidia": {
        "name": "NVIDIA",
        "downloads": "https://www.nvidia.com/Download/index.aspx",
        "studio": "https://www.nvidia.com/Download/driverResults.aspx/",
        "clean": "https://www.nvidia.com/Download/driverResults.aspx/",
        "note": "Use the Studio driver for photo/video and creative work, Game Ready for gaming.",
    },
    "amd": {
        "name": "AMD",
        "downloads": "https://www.amd.com/en/support",
        "studio": "https://www.amd.com/en/resources/support-articles/drivers-installation.html",
        "clean": "https://www.amd.com/en/support",
        "note": "Adrenalin Edition. Reset your PC instead of a full factory reset when offered.",
    },
    "intel": {
        "name": "Intel",
        "downloads": "https://www.intel.com/content/www/us/en/download-center/home.html",
        "studio": "https://www.intel.com/content/www/us/en/download-center/home.html",
        "clean": "https://www.intel.com/content/www/us/en/support/detect.html",
        "note": "Use Intel Driver & Support Assistant to match drivers to your exact CPU.",
    },
    "realtek": {
        "name": "Realtek",
        "downloads": "https://www.realtek.com/Download/List?cate_id=584",
        "studio": "https://www.realtek.com/Download/List?cate_id=584",
        "clean": "https://www.realtek.com/Download/List?cate_id=584",
        "note": "Drivers are usually best obtained from your laptop or motherboard vendor.",
    },
    "lenovo": {
        "name": "Lenovo",
        "downloads": "https://pcsupport.lenovo.com/us/en/",
        "studio": "https://pcsupport.lenovo.com/us/en/",
        "clean": "https://pcsupport.lenovo.com/us/en/",
        "note": "Use your serial number or Detect Product for exact model-matched drivers.",
    },
    "msi": {
        "name": "MSI",
        "downloads": "https://www.msi.com/support",
        "studio": "https://www.msi.com/support",
        "clean": "https://www.msi.com/support",
        "note": "Select your exact board model; chipset and LAN drivers are board-specific.",
    },
    "asus": {
        "name": "ASUS",
        "downloads": "https://www.asus.com/support/",
        "studio": "https://www.asus.com/support/",
        "clean": "https://www.asus.com/support/",
        "note": "Check the motherboard or laptop support page for your model.",
    },
    "microsoft": {
        "name": "Microsoft",
        "downloads": "https://www.microsoft.com/windows/download",
        "studio": "https://www.catalog.update.microsoft.com/",
        "clean": "https://support.microsoft.com/windows",
        "note": "The Microsoft Update Catalog is official and hosts signed drivers.",
    },
    "guru3d": {
        "name": "Guru3D (DDU)",
        "downloads": "https://www.guru3d.com/download/display-driver-uninstaller-download/",
        "studio": "https://www.wagnardsoft.com/",
        "clean": "https://www.guru3d.com/download/display-driver-uninstaller-download/",
        "note": "DDU is the community standard for a clean GPU driver removal.",
    },
}

# Device Manager error codes and their fixes.
DEVICE_MANAGER_CODES: list[dict] = [
    {
        "code": 1,
        "name": "The driver failed to load",
        "meaning": "Windows found hardware but the installed driver did not initialise. Usually a partial or corrupt install.",
        "fixes": [
            "Uninstall the device with 'Delete the driver software' ticked, then reboot and let Windows reinstall it.",
            "Install the driver from your laptop/motherboard vendor rather than a third-party site.",
            "Run the hardware changes troubleshooter: Settings > System > Other > Run hardware troubleshooter.",
        ],
        "difficulty": "easy",
    },
    {
        "code": 10,
        "name": "Cannot start this device",
        "meaning": "The hardware is usable but its driver reported a problem starting. Very common with GPUs after an unclean shutdown or a Windows Update driver.",
        "fixes": [
            "Roll back the driver: Device Manager > device > Properties > Driver > Roll Back Driver.",
            "If Roll Back is greyed out, remove the device, reboot and install the vendor's clean package.",
            "Use DDU in Safe Mode, then reinstall the official driver.",
            "Check the device's Resource settings for a manual IRQ conflict (older machines).",
        ],
        "difficulty": "moderate",
    },
    {
        "code": 22,
        "name": "This device is disabled",
        "meaning": "The device has been switched off in Device Manager.",
        "fixes": [
            "Right-click the device and choose Enable device.",
        ],
        "difficulty": "easy",
    },
    {
        "code": 28,
        "name": "Drivers not installed",
        "meaning": "No driver is installed for this device. Extremely common for network adapters and chipsets after a fresh Windows install without vendor drivers.",
        "fixes": [
            "Install the chipset and network drivers from your PC vendor's support site.",
            "Temporarily connect via Ethernet or a USB Wi-Fi dongle to download drivers.",
            "On a laptop, check that the device is not disabled by a physical switch or a BIOS setting.",
        ],
        "difficulty": "easy",
    },
    {
        "code": 31,
        "name": "A problem occurred and Windows stopped this device",
        "meaning": "The driver failed to load because it conflicts with another driver or is broken.",
        "fixes": [
            "Roll back or reinstall the driver.",
            "Uninstall the conflicting older driver package from the driver's Details tab.",
            "Check Reliability Monitor (perfmon /rel) for the exact failure time.",
        ],
        "difficulty": "moderate",
    },
    {
        "code": 43,
        "name": "Windows has stopped this device because it has reported problems",
        "meaning": "The driver told Windows it hit a fatal error. On NVIDIA/AMD GPUs this is very often caused by an overclock, a bad driver version, or overheating.",
        "fixes": [
            "Uninstall the GPU driver, reboot, and reinstall the latest stable driver.",
            "Remove any overclock or undervolt from MSI Afterburner or your GPU vendor app.",
            "Check GPU temperatures and clean dust from the cooler and fans.",
            "If the GPU is in a laptop, confirm it is not overheating; try a chassis-clean and reseat.",
        ],
        "difficulty": "moderate",
    },
    {
        "code": 45,
        "name": "This device is disconnected or not responding",
        "meaning": "The device stopped responding to the system, common with external drives and docking stations.",
        "fixes": [
            "Reconnect the device and run the hardware troubleshooter.",
            "Try a different port or cable; try a known-good USB port on the case itself.",
            "Update or reinstall the chipset driver, which manages USB power management.",
        ],
        "difficulty": "easy",
    },
    {
        "code": 48,
        "name": "The software for this device has been blocked",
        "meaning": "The driver is not Windows-signed or its signature is no longer trusted.",
        "fixes": [
            "Remove the device with 'Delete the driver software' ticked, then install the official signed driver.",
            "Avoid 'test signing' and unsigned driver packages from third-party sites.",
        ],
        "difficulty": "moderate",
    },
    {
        "code": 52,
        "name": "The driver was blocked because it caused Windows to fail to start",
        "meaning": "A driver that crashed during an earlier boot was quarantined to allow Windows to start.",
        "fixes": [
            "Uninstall the offending device and reinstall a working driver.",
            "If the same driver keeps blocking, boot into Safe Mode and remove it there.",
        ],
        "difficulty": "hard",
    },
    {
        "code": 54,
        "name": "The device uses a legacy driver",
        "meaning": "The driver is an old 16-bit driver that no longer works correctly on Windows.",
        "fixes": [
            "Install a modern driver from the vendor.",
            "The device may not be usable under Windows 11 24H2, which drops legacy driver support.",
        ],
        "difficulty": "moderate",
    },
    {
        "code": 141,
        "name": "GPU engine error (video hardware error)",
        "meaning": "The graphics driver crashed and Windows recovered the GPU. Often follows sleep or wake, or long display idle.",
        "fixes": [
            "Update the GPU driver to the newest stable release.",
            "Turn off hardware-accelerated GPU scheduling in Settings > System > Display > Graphics.",
            "Disable driver hardware scheduling updates in Windows Update, which can swap in a newer driver behind your back.",
        ],
        "difficulty": "moderate",
    },
    {
        "code": "no_code",
        "name": "No error code, but a yellow exclamation mark",
        "meaning": "The device is present but not working correctly. Read the Properties > General > Status text; it usually names the real problem.",
        "fixes": [
            "Follow the exact wording in the status message rather than guessing.",
            "Run Windows Update, then the vendor driver installer.",
            "Scan for hardware changes in Device Manager > View > Action.",
        ],
        "difficulty": "easy",
    },
]


def _with_explicit_driver(raw: str) -> str:
    """Normalise a Postgres URL onto the driver that is actually installed.

    A bare ``postgresql://`` or ``postgres://`` leaves the driver choice to
    SQLAlchemy, and that choice is version-dependent: from SQLAlchemy 2.1 a
    bare ``postgresql://`` resolves to psycopg 3, which is a different
    distribution from the psycopg2-binary in requirements.txt. The engine then
    fails to build with ``ModuleNotFoundError: No module named 'psycopg'`` at
    import time, which on Vercel means the function never boots rather than
    degrading in some visible way.

    Naming psycopg2 explicitly means a connection string pasted straight from
    Supabase, Neon or Vercel Postgres works unmodified, and the driver no longer
    moves underneath us on a dependency bump. A URL that already names a driver
    is returned untouched, so installing psycopg 3 and saying so still works.
    """
    for prefix in ("postgres://", "postgresql://"):
        if raw.startswith(prefix):
            return "postgresql+psycopg2://" + raw[len(prefix):]
    return raw


def _with_sslmode(raw: str) -> str:
    """Make sure a managed Postgres URL asks for TLS.

    Managed providers - Supabase, Neon, Vercel Postgres - require it, and
    several of them hand out a connection string with no ``sslmode`` in it.
    psycopg2 defaults to *prefer*, which will happily attempt plaintext and
    fail late and less clearly, so the requirement is stated outright here.

    An existing ``sslmode`` or ``ssl`` parameter is left alone, because that is
    the operator making a deliberate choice.
    """
    if not raw.startswith(("postgres://", "postgresql://", "postgresql+")):
        return raw
    if "?" not in raw:
        return f"{raw}?sslmode=require"
    query = raw.split("?", 1)[1]
    if "sslmode=" in query or "ssl=" in query:
        return raw
    separator = "&" if query else "?"
    return f"{raw}{separator}sslmode=require"


# Environment variables that hosting-provider integrations set on their own.
# Ordered by preference.
#
# POSTGRES_URL is what the Supabase and Neon Vercel Marketplace integrations
# inject, and it is the pooled, transaction-mode string (port 6543), which is
# the one that works from a serverless function. Two siblings are deliberately
# ignored: POSTGRES_URL_NON_POOLING is a direct connection to an IPv6-only
# host, which times out on Vercel, and POSTGRES_PRISMA_URL carries Prisma's
# `?pgbouncer=true&connection_limit=1` query, which is meaningless to
# SQLAlchemy.
#
# DATABASE_URL is picked up as a second choice because that is the convention
# for most managed Postgres providers. FIXITHUB_DATABASE_URL still wins over
# both, so an operator who wants to override this never has to unset anything
# in the dashboard.
_PROVIDER_DATABASE_ENV_VARS = ("POSTGRES_URL", "DATABASE_URL")


def _resolve_database_url() -> str:
    raw = os.environ.get("FIXITHUB_DATABASE_URL", "").strip()
    if raw:
        return _with_explicit_driver(_with_sslmode(raw))

    for name in _PROVIDER_DATABASE_ENV_VARS:
        candidate = os.environ.get(name, "").strip()
        if candidate:
            return _with_explicit_driver(_with_sslmode(candidate))

    if IS_SERVERLESS:
        temp_db = Path(tempfile.gettempdir()) / "fixithub.db"
        return f"sqlite:///{temp_db.as_posix()}"
    return f"sqlite:///{(DATA_DIR / 'fixithub.db').as_posix()}"


@dataclass
class Settings:
    """Runtime settings resolved from the environment."""

    secret_key: str = field(
        default_factory=lambda: os.environ.get(
            "FIXITHUB_SECRET_KEY", secrets.token_urlsafe(48)
        )
    )
    # Whether FIXITHUB_SECRET_KEY was actually supplied. Tracked separately
    # because the value itself is indistinguishable from a generated one: both
    # are 48 random bytes, so code cannot tell "configured" from "rotating".
    secret_key_configured: bool = field(
        default_factory=lambda: bool(os.environ.get("FIXITHUB_SECRET_KEY"))
    )
    admin_password_hash: str = field(
        default_factory=lambda: os.environ.get("FIXITHUB_ADMIN_PASSWORD_HASH", "")
    )
    admin_password: str = field(
        default_factory=lambda: os.environ.get("FIXITHUB_ADMIN_PASSWORD", "")
    )
    database_url: str = field(
        default_factory=_resolve_database_url
    )
    debug: bool = field(
        default_factory=lambda: os.environ.get("FIXITHUB_DEBUG", "0") == "1"
    )
    # Network tool limits
    rate_limit_max: int = field(
        default_factory=lambda: int(os.environ.get("FIXITHUB_RATE_LIMIT_MAX", "10"))
    )
    rate_limit_window: int = field(
        default_factory=lambda: int(os.environ.get("FIXITHUB_RATE_LIMIT_WINDOW", "60"))
    )
    max_upload_bytes: int = 5 * 1024 * 1024  # 5 MB hard limit for minidumps
    max_query_length: int = 200
    max_dns_name_length: int = 253
    http_timeout: float = 8.0
    dns_timeout: float = 4.0
    socket_timeout: float = 4.0
    max_response_bytes: int = 1_000_000
    secure_cookies: bool = field(
        default_factory=lambda: os.environ.get("FIXITHUB_SECURE_COOKIES", "0") == "1"
    )
    # Two-factor authentication for the admin account. Not opt-in per account
    # but escapable: if a device is lost and every recovery code is spent,
    # FIXITHUB_DISABLE_2FA=1 is the way back in. Turning it on does not
    # enrol anything; the admin has to enrol deliberately.
    disable_2fa: bool = field(
        default_factory=lambda: os.environ.get("FIXITHUB_DISABLE_2FA", "0") == "1"
    )
    # Only enable behind a reverse proxy you control, otherwise a client could
    # spoof X-Forwarded-For and defeat the rate limiter.
    trust_proxy_headers: bool = field(
        default_factory=lambda: os.environ.get("FIXITHUB_TRUST_PROXY", "0") == "1"
    )
    # Reader accounts. Off by default: turning it on means the site accepts
    # content from strangers, so it should be a deliberate choice.
    allow_registration: bool = field(
        default_factory=lambda: os.environ.get("FIXITHUB_ALLOW_REGISTRATION", "0") == "1"
    )
    # Verification email. Left unset, signup still works: the account is created
    # and an admin can verify it by hand from the dashboard.
    smtp_host: str = field(
        default_factory=lambda: os.environ.get("FIXITHUB_SMTP_HOST", "")
    )
    smtp_port: int = field(
        default_factory=lambda: int(os.environ.get("FIXITHUB_SMTP_PORT", "587"))
    )
    smtp_user: str = field(
        default_factory=lambda: os.environ.get("FIXITHUB_SMTP_USER", "")
    )
    smtp_password: str = field(
        default_factory=lambda: os.environ.get("FIXITHUB_SMTP_PASSWORD", "")
    )
    smtp_from: str = field(
        default_factory=lambda: os.environ.get("FIXITHUB_SMTP_FROM", "")
    )


settings = Settings()
