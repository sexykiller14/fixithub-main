"""Catalogue of downloadable diagnostic scripts.

Scripts live as real files in /scripts_download so users can read them before
downloading. This module holds the explanatory metadata: what each script does,
which commands it runs, and a plain-English note for every command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..config import SCRIPTS_DIR

CONTENT_TYPES = {
    ".ps1": "application/octet-stream",
    ".bat": "application/octet-stream",
    ".txt": "text/plain; charset=utf-8",
}

MAX_SCRIPT_BYTES = 256 * 1024


@dataclass
class CommandNote:
    command: str
    explanation: str
    modifies: bool = False
    warning: str = ""


@dataclass
class ScriptInfo:
    slug: str
    title: str
    filename: str
    summary: str
    purpose: list[str]
    requirements: list[str]
    commands: list[CommandNote]
    warnings: list[str]
    related_slugs: list[str] = field(default_factory=list)
    difficulty: str = "easy"
    estimated_minutes: int = 5

    @property
    def extension(self) -> str:
        return Path(self.filename).suffix.lower()

    @property
    def language(self) -> str:
        return "PowerShell" if self.extension == ".ps1" else "Command Prompt"

    def how_to_run(self) -> list[str]:
        if self.extension == ".ps1":
            return [
                "Right-click the downloaded file and choose Run with PowerShell, or",
                "open PowerShell as Administrator, then run:",
                f".\\{self.filename}",
                "If PowerShell blocks it, run this once and then try again:",
                "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass",
            ]
        return [
            "Open the folder containing the file, then",
            "right-click the file and choose Run as administrator, or",
            "open Command Prompt as Administrator and run:",
            self.filename,
        ]


CATALOG: dict[str, dict] = {
    "network-reset": {
        "filename": "fixit-network-reset.bat",
        "title": "Network reset",
        "summary": "Resets the TCP/IP stack, Winsock catalog and DNS cache, then renews your network connection.",
        "purpose": [
            "Rebuild Windows network settings that have become corrupted",
            "Fix connections that drop out or refuse to reconnect",
            "Recover after a failed VPN or virtual network adapter install",
        ],
        "requirements": [
            "Administrator rights",
            "An internet connection is not required",
            "Your VPN and virtual machine software may need reinstalling afterwards",
        ],
        "commands": [
            {
                "command": "ipconfig /flushdns",
                "explanation": "Clears the cache of previously resolved website names, so your computer looks them up again from scratch.",
                "modifies": True,
            },
            {
                "command": "ipconfig /release",
                "explanation": "Releases the current IP address your computer is using, telling the network it no longer needs it.",
                "modifies": True,
            },
            {
                "command": "ipconfig /renew",
                "explanation": "Asks the router or DHCP server for a fresh IP address and configuration, re-establishing the connection.",
                "modifies": True,
            },
            {
                "command": "netsh winsock reset",
                "explanation": "Rebuilds the Winsock catalog, which is the list of network components Windows uses. This fixes many broken connections.",
                "modifies": True,
                "warning": "A restart is required afterwards, and VPN software must be reinstalled.",
            },
            {
                "command": "netsh int ip reset",
                "explanation": "Resets TCP/IP settings back to their defaults, undoing manual IP, gateway or DNS changes.",
                "modifies": True,
                "warning": "A restart is required afterwards.",
            },
        ],
        "warnings": [
            "This script changes network settings. It is safe, but your VPN client and virtual machine networks may need reinstalling afterwards.",
            "Restart your computer after running it, or the Winsock and TCP/IP resets will not take effect.",
            "Read the script before running it. You should be able to see exactly which commands it runs.",
        ],
        "related_slugs": ["fix-no-internet-windows", "fix-dns-problems-windows", "fix-ethernet-not-working"],
    },
    "system-file-repair": {
        "filename": "fixit-system-file-repair.ps1",
        "title": "System file repair",
        "summary": "Repairs the Windows component store and protected system files using DISM and SFC, in the correct order.",
        "purpose": [
            "Repair system files damaged by an interrupted update or a failed antivirus scan",
            "Fix a large number of unexplained Windows errors",
            "Prepare Windows before a larger repair or upgrade",
        ],
        "requirements": [
            "Administrator rights",
            "10 to 30 minutes of uninterrupted time",
            "Several GB of free space on the system drive",
        ],
        "commands": [
            {
                "command": "DISM /Online /Cleanup-Image /CheckHealth",
                "explanation": "A quick check for whether the component store is flagged as repairable. Takes under a minute.",
            },
            {
                "command": "DISM /Online /Cleanup-Image /ScanHealth",
                "explanation": "Scans the component store for corruption. This takes several minutes but finds problems CheckHealth misses.",
            },
            {
                "command": "DISM /Online /Cleanup-Image /RestoreHealth",
                "explanation": "Downloads replacement copies of damaged system files from Windows Update and reinstalls them. This is the step that actually repairs things, and it is why you should have an internet connection.",
                "modifies": True,
                "warning": "Needs an internet connection. Can take 20 minutes or more on a slow connection.",
            },
            {
                "command": "sfc /scannow",
                "explanation": "Scans every protected system file and replaces any that do not match the known good copies. Run this after DISM, not before, because DISM repairs what SFC needs.",
                "modifies": True,
            },
        ],
        "warnings": [
            "Do not close the window while it is running. Interrupting DISM can leave the component store worse than before.",
            "Run as Administrator, or the commands will refuse to work.",
            "If DISM reports that it cannot repair, the source files are damaged too and you will need installation media.",
        ],
        "related_slugs": ["repair-windows-system-files", "fix-windows-update-failing", "critical-process-died"],
    },
    "system-report": {
        "filename": "fixit-system-report.ps1",
        "title": "Collect system info report",
        "summary": "Writes a plain text report of your hardware, Windows version, recent critical events and installed drivers, so you can share it with support.",
        "purpose": [
            "Give someone helping you the exact details they need",
            "Capture crash details and recent errors from the Event Log",
            "Record driver versions before and after a change",
        ],
        "requirements": [
            "No administrator rights needed, though running as administrator gives more detail",
            "Takes a couple of minutes",
            "The report is saved to your Desktop",
        ],
        "commands": [
            {
                "command": "Get-ComputerInfo",
                "explanation": "Reads the system's hardware and Windows version details from Windows itself.",
            },
            {
                "command": "Get-CimInstance Win32_Processor / Win32_PhysicalMemory",
                "explanation": "Reads your CPU and installed memory details directly from the hardware.",
            },
            {
                "command": "Get-CimInstance Win32_DiskDrive",
                "explanation": "Reads the model, size and interface of each drive, which identifies whether it is an SSD or a mechanical drive.",
            },
            {
                "command": "Get-CimInstance Win32_PhysicalDisk | Get-StorageReliabilityCounter",
                "explanation": "Reads SMART wear and error counters, which reveal whether a drive is failing.",
            },
            {
                "command": "Get-WinEvent -FilterHashtable @{LogName='System'; Level=1,2}",
                "explanation": "Reads the Event Log for critical errors and warnings from the last few days.",
            },
            {
                "command": "Get-CimInstance Win32_PnPSignedDriver",
                "explanation": "Lists every driver with its version and date, which is how mismatched drivers get spotted.",
            },
        ],
        "warnings": [
            "The report contains your computer name, user name and serial numbers. Read it before you share it online.",
            "This script only reads information. It does not change any settings.",
            "Save the report somewhere you can find it, since it opens in Notepad when it finishes.",
        ],
        "related_slugs": ["collect-system-info-report", "windows-device-manager-error-codes", "check-disk-health-ssd-hdd"],
    },
    "disk-health": {
        "filename": "fixit-disk-health.ps1",
        "title": "Disk health check",
        "summary": "Decodes the raw SMART attributes of every drive, grades each one, compares against your last run to show whether bad-sector counts are climbing, and scans each volume without changing anything.",
        "purpose": [
            "Check whether a drive is failing before it takes your data with it",
            "See whether reallocated or pending sectors are climbing between runs, which is the earliest reliable warning",
            "Find filesystem errors without making any changes",
            "Confirm a new drive is healthy before you rely on it",
        ],
        "requirements": [
            "Administrator rights for the SMART counters and the volume scan",
            "A few minutes, considerably longer on large drives",
            "Keeps a small counter history file on your Desktop so the next run can show a trend",
        ],
        "commands": [
            {
                "command": "Get-PhysicalDisk",
                "explanation": "Lists each physical drive with its media type, so you can confirm whether it is an SSD or a mechanical drive.",
            },
            {
                "command": "Get-StorageReliabilityCounter -PhysicalDisk",
                "explanation": "Reads a summary of SMART health: temperature, power-on hours, wear and read/write errors. Useful as a second opinion on the raw attribute table.",
            },
            {
                "command": "Get-CimInstance MSStorageDriver_FailurePredictData",
                "explanation": "Reads the raw SMART attribute table from the drive itself, which is where reallocated, pending and uncorrectable sector counts actually live. This script decodes the six vendor bytes of each attribute itself, because Windows reports the table as an opaque byte array.",
            },
            {
                "command": "Get-CimInstance MSStorageDriver_FailurePredictStatus",
                "explanation": "Reads the drive's own self-assessment, which is the same prediction your BIOS shows at startup.",
            },
            {
                "command": "Import-Csv / Export-Csv",
                "explanation": "Reads and writes the counter history file. Comparing each run against the last one is how a drive that is slowly degrading gets caught before it fails outright.",
            },
            {
                "command": "Get-Volume",
                "explanation": "Lists every volume with its drive letter and free space, so you can check each one.",
            },
            {
                "command": "Repair-Volume -Scan",
                "explanation": "Runs a read-only scan of a volume. It reports errors but changes nothing, which is what you want when checking a drive holding important files.",
                "warning": "This scans only. It will not repair anything, which is intentional so your data is safe. On a large volume it takes several minutes.",
            },
            {
                "command": "Get-WinEvent -ProviderName disk, Ntfs, StorPort",
                "explanation": "Reads storage errors from the Event Log. Event 51 means Windows could not read part of a volume, and event 157 means a drive vanished without being shut down, which points at either a loose cable or a failing drive.",
            },
        ],
        "warnings": [
            "If SMART reports failures, back up your files immediately. A failing drive can stop working at any moment.",
            "Do not run chkdsk with /f on a failing drive. Repair writes to the drive and can destroy the data you have not yet recovered.",
            "This script is deliberately read-only. Use our other guides if you then need to repair something.",
            "A counter that climbs between two runs matters more than a single high reading. Keep the report and run it again in a month.",
            "USB drives and NVMe drives often hide the raw SMART table entirely. The script says so rather than reporting a false all-clear.",
        ],
        "related_slugs": ["check-disk-health-ssd-hdd", "fix-unmountable-boot-volume", "hdd-to-ssd-upgrade-guide"],
    },
    "ram-diagnostics": {
        "filename": "fixit-ram-diagnostics.ps1",
        "title": "RAM diagnostics",
        "summary": "Reports your memory layout, tells you whether an XMP or EXPO profile is actually enabled, checks whether your modules are paired for dual channel, and reads past memory test results and hardware error events.",
        "purpose": [
            "Find out whether your memory is running at its rated speed or its much slower default",
            "Check that your modules sit in the right slots for dual channel",
            "Read the result of any Windows memory test you have already run",
            "Rule the CPU, board and power supply in or out before blaming a memory module",
        ],
        "requirements": [
            "Administrator rights to read the Event Log, everything else works without",
            "Takes under a minute",
            "Nothing is tested and nothing is changed",
        ],
        "commands": [
            {
                "command": "Get-CimInstance Win32_PhysicalMemory",
                "explanation": "Reports each memory module's slot, capacity, rated speed and configured speed. Comparing Speed against ConfiguredClockSpeed is how the script tells whether an XMP or EXPO profile is active, without entering the BIOS.",
            },
            {
                "command": "Get-CimInstance Win32_PhysicalMemoryArray",
                "explanation": "Reports how many slots the board has and its maximum supported capacity, which shows whether adding more memory is even possible.",
            },
            {
                "command": "Get-CimInstance Win32_OperatingSystem",
                "explanation": "Reports total and free physical memory, so you can tell a memory capacity problem apart from a faulty module.",
            },
            {
                "command": "Get-WinEvent -ProviderName MemoryDiagnostics-Results",
                "explanation": "Reads the result of any Windows Memory Diagnostic run. Note that this built-in test is weak and often passes faulty memory, so a clean result is not proof your RAM is good.",
            },
            {
                "command": "Get-WinEvent -ProviderName Microsoft-Windows-WHEA-Logger",
                "explanation": "Reads hardware error events. These report CPU, memory and PCIe faults, and are worth checking before replacing a memory module, because the real fault is often elsewhere.",
            },
        ],
        "warnings": [
            "This script does not test your memory. It only describes it. The commands to run a real test are printed at the end of the report, with an explanation of each.",
            "It does not enable your XMP or EXPO profile for you. That is a BIOS setting, and it is described in the RAM stability guide rather than done automatically.",
            "The report contains your computer name and memory serial numbers. Read it before sharing it with anyone.",
            "If you also have a failing drive, back it up before running any memory test that restarts the machine.",
        ],
        "related_slugs": ["test-ram-memory-errors", "ram-stability-xmp-expo", "upgrade-ram-laptop-desktop"],
    },
}


@dataclass
class ScriptEntry:
    info: ScriptInfo
    source: str


def _entry(slug: str) -> ScriptEntry | None:
    meta = CATALOG.get(slug)
    if meta is None:
        return None
    filename = meta["filename"]
    path = SCRIPTS_DIR / filename
    if not path.is_file():
        return None
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(source.encode("utf-8")) > MAX_SCRIPT_BYTES:
        return None
    info = ScriptInfo(
        slug=slug,
        title=meta["title"],
        filename=filename,
        summary=meta["summary"],
        purpose=list(meta["purpose"]),
        requirements=list(meta["requirements"]),
        commands=[CommandNote(**note) for note in meta["commands"]],
        warnings=list(meta["warnings"]),
        related_slugs=list(meta.get("related_slugs", [])),
        difficulty=meta.get("difficulty", "easy"),
        estimated_minutes=meta.get("estimated_minutes", 5),
    )
    return ScriptEntry(info=info, source=source)


def list_scripts() -> list[ScriptInfo]:
    return [_entry(slug).info for slug in CATALOG if _entry(slug) is not None]


def get_script(slug: str) -> ScriptEntry | None:
    return _entry(slug)


def script_path(slug: str) -> Path | None:
    entry = _entry(slug)
    if entry is None:
        return None
    return SCRIPTS_DIR / entry.info.filename
