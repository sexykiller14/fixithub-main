"""Minidump (.dmp) analysis: signature validation and bugcheck extraction.

Safety properties
-----------------
* The upload is size-capped while streaming, so a lying Content-Length header
  cannot exhaust memory.
* Only bytes are parsed. Nothing is ever written to disk and nothing from the
  upload is executed. The minidump format is data, not code.
* Signature checking happens before any parser sees the buffer.
* Every parsing step is individually guarded, so one unexpected library version
  cannot turn into a 500.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field

# Header signatures Windows uses.
SIGNATURE_MINIDUMP = b"PMDMP"   # user-mode minidump
SIGNATURE_PAGEDU = b"PAGEDU"    # 32-bit kernel dump
SIGNATURE_PAGE = b"PAGE"        # 64-bit kernel dump
SIGNATURE_FULL = b"FULL"        # complete dump
VALID_SIGNATURES = (
    SIGNATURE_MINIDUMP,
    SIGNATURE_PAGEDU,
    SIGNATURE_PAGE,
    SIGNATURE_FULL,
)

# Stream type IDs used by the manual parser.
STREAM_SYSTEM_INFO = 7
STREAM_BUGCHECK = 16

# Parameter explanations for the codes users actually encounter.
PARAMETER_HINTS: dict[int, tuple[str, ...]] = {
    0x0000000A: (
        "Memory address that was accessed illegally",
        "IRQL at the time of the fault",
        "Type of access: read or write",
        "Address being read or written",
    ),
    0x0000001A: (
        "Type of memory corruption",
        "Address of the corrupted area",
        "0 means hardware RAM, 2 means a paging or mapped file",
        "The corrupting driver, if identified",
    ),
    0x0000003B: (
        "Exception code, such as 0xC0000005 for an access violation",
        "Address of the faulting instruction",
        "Unused",
        "Unused",
    ),
    0x00000050: (
        "Memory address that was accessed illegally",
        "Type of access: 0 read, 1 write, 2 execute",
        "The address that was accessed",
        "Unused",
    ),
    0x00000116: (
        "Failure type: 2 is a timeout, 3 is a driver crash",
        "The device object that hung",
        "Internal driver error code",
        "Unused",
    ),
    0x00000124: (
        "Machine check exception type",
        "Error record identifying whether CPU, memory or PCIe caused it",
        "High 32 bits of the address involved",
        "Low 32 bits of the address involved",
    ),
    0x0000017E: (
        "Microcode revision the OS expected",
        "Microcode revision the BIOS supplied",
        "Unused",
        "Unused",
    ),
    0x00000133: (
        "The driver that ran too long, or 0 if unknown",
        "Reserved",
        "High 32 bits of the DPC runtime in 100ns units",
        "Low 32 bits of the DPC runtime",
    ),
    0x0000007B: (
        "Unused",
        "Status code describing the failure, such as 0xC0000034 for a missing driver",
        "Unused",
        "Unused",
    ),
    0x000000EF: (
        "The process object that could not start",
        "Unused",
        "Unused",
        "Unused",
    ),
    0x000000ED: (
        "The device that reported the error",
        "NTSTATUS error code",
        "Unused",
        "Unused",
    ),
    0x000000C4: (
        "The subcode identifying which check failed",
        "The verifier function that failed",
        "The parameters passed to it",
        "Unused",
    ),
    0x000000EA: (
        "The driver that hung, or 0 if unknown",
        "Unused",
        "Unused",
        "Unused",
    ),
}

# Codes we accept from an unlabelled 32-bit field. A random integer inside a
# dump stream is almost never one of these, which keeps false positives away.
KNOWN_BUGCHECK_CODES = {
    0x0000000A, 0x00000012, 0x00000018, 0x00000019, 0x0000001A, 0x0000001E,
    0x00000022, 0x00000023, 0x00000024, 0x0000003B, 0x0000003D, 0x00000043,
    0x0000004C, 0x0000004E, 0x0000004F, 0x00000050, 0x00000051, 0x00000053,
    0x0000005C, 0x0000006B, 0x00000077, 0x0000007A, 0x0000007B, 0x0000007E,
    0x0000007F, 0x0000008B, 0x0000008E, 0x00000092, 0x00000093, 0x0000009B,
    0x0000009C, 0x0000009F, 0x000000A0, 0x000000A2, 0x000000A5, 0x000000B4,
    0x000000B9, 0x000000BE, 0x000000C1, 0x000000C2, 0x000000C4, 0x000000C5,
    0x000000C7, 0x000000CC, 0x000000D0, 0x000000D1, 0x000000D4, 0x000000D6,
    0x000000DE, 0x000000EA, 0x000000EB, 0x000000ED, 0x000000EF, 0x000000F0,
    0x000000F3, 0x000000F4, 0x000000F5, 0x000000F7, 0x000000FA, 0x000000FE,
    0x00000101, 0x00000102, 0x00000106, 0x00000109, 0x0000010E, 0x00000113,
    0x00000116, 0x00000117, 0x00000119, 0x0000011B, 0x00000120, 0x00000124,
    0x0000012B, 0x0000012C, 0x00000133, 0x00000139, 0x0000013B, 0x0000013D,
    0x00000140, 0x00000144, 0x00000145, 0x00000147, 0x00000154, 0x00000164,
    0x0000017E, 0x0000018B, 0x0000018C, 0x00000190, 0x00000191, 0x00000196,
    0x0000019C, 0x000001CF, 0x000001D0, 0x000001D5, 0x000001D8, 0x000001DE,
    0x00020001, 0xC0000218, 0xC000021A, 0xDEADDEAD,
}


class DumpError(Exception):
    """Raised for rejected or unparsable uploads, with a user-facing message."""


@dataclass
class Bugcheck:
    code: int
    name: str
    hex_code: str
    parameters: list[int] = field(default_factory=list)
    parameter_hints: list[str] = field(default_factory=list)
    os_build: str = ""
    os_version: str = ""

    @property
    def short_hex(self) -> str:
        return "0x%X" % self.code

    def parameter_rows(self) -> list[dict]:
        rows = []
        for index, value in enumerate(self.parameters[:4]):
            rows.append(
                {
                    "index": index + 1,
                    "hex": "0x%016X" % (value & 0xFFFFFFFFFFFFFFFF),
                    "decimal": value,
                    "hint": self.parameter_hints[index] if index < len(self.parameter_hints) else "",
                }
            )
        return rows


@dataclass
class DumpAnalysis:
    filename: str
    size_bytes: int
    signature: str
    bugcheck: Bugcheck | None
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    parse_method: str = ""


def validate_size(size: int, max_bytes: int) -> None:
    if size <= 0:
        raise DumpError("That file is empty.")
    if size > max_bytes:
        raise DumpError(
            f"That file is {size / 1024 / 1024:.1f} MB. The limit is "
            f"{max_bytes // 1024 // 1024} MB."
        )


def validate_extension(filename: str) -> str:
    lowered = (filename or "").strip().lower()
    if not lowered.endswith(".dmp"):
        raise DumpError("Only .dmp files are accepted.")
    # Reject path components so a filename can never be used as a path.
    if any(part in lowered for part in ("/", "\\", "..")):
        raise DumpError("Invalid filename.")
    return lowered.rsplit("/", 1)[-1][-120:]


def validate_signature(data: bytes) -> str:
    if len(data) < 8:
        raise DumpError("That file is too short to be a dump file.")
    head = data[:8]
    for signature in VALID_SIGNATURES:
        if head.startswith(signature):
            return signature.decode("ascii")
    found = head[:4].decode("ascii", errors="replace")
    raise DumpError(
        f"That does not look like a Windows dump file. Its header reads "
        f"'{found}' rather than PMDMP, PAGEDU or PAGE."
    )


def _parse_with_library(data: bytes) -> tuple[int, list[int], str, str] | None:
    """Parse using the minidump library, defensively probing its API surface."""
    try:
        from minidump.minidumpfile import MinidumpFile
    except ImportError:
        return None

    dump = None
    for loader in ("parse_buff", "parse"):
        try:
            method = getattr(MinidumpFile, loader, None)
            if method is None:
                continue
            if loader == "parse_buff":
                candidate = method(data)
            else:
                candidate = method(io.BytesIO(data))
        except Exception:  # noqa: BLE001 - the library raises many types
            continue
        if candidate is not None:
            dump = candidate
            break

    if dump is None:
        return None

    code: int | None = None
    parameters: list[int] = []
    build = ""
    version = ""

    system_info = getattr(dump, "system_info", None)
    if system_info is not None:
        for attribute in ("bugcheck_code", "bug_check_code", "bugcheck"):
            value = getattr(system_info, attribute, None)
            if isinstance(value, int) and not isinstance(value, bool):
                code = value
                break
        for attribute in ("bugcheck_code_parameters", "bug_check_code_parameters", "parameters"):
            value = getattr(system_info, attribute, None)
            if isinstance(value, (list, tuple)):
                parameters = [p for p in value if isinstance(p, int)]
                break
        build_value = getattr(system_info, "build_number", None)
        if not isinstance(build_value, int):
            build_value = getattr(system_info, "native_major_build_number", None)
        if isinstance(build_value, int):
            build = str(build_value)
        product = getattr(system_info, "product_name", None) or getattr(
            system_info, "product_type", None
        )
        if product:
            version = str(product)

    bugcheck_stream = getattr(dump, "bugcheck", None)
    if code is None and bugcheck_stream is not None:
        for attribute in ("code", "bugcheck_code"):
            value = getattr(bugcheck_stream, attribute, None)
            if isinstance(value, int) and not isinstance(value, bool):
                code = value
                break
        value = getattr(bugcheck_stream, "parameters", None)
        if isinstance(value, (list, tuple)):
            parameters = [p for p in value if isinstance(p, int)]

    if code is None:
        return None
    return code, parameters[:4], build, version


def _parse_manually(data: bytes) -> tuple[int, list[int], str, str] | None:
    """Walk the stream directory directly, independent of library version.

    A user-mode minidump has this layout::

        offset 0   4 bytes   signature "PMDM" (the file's first five bytes read PMDMP)
        offset 4   4 bytes   version
        offset 8   4 bytes   number of streams
        offset 12  4 bytes   RVA of the stream directory
        offset 16  4 bytes   checksum
        offset 20  4 bytes   timestamp
        offset 24  8 bytes   flags
        then       12 bytes per stream: type, size, RVA

    A kernel dump has the 4-byte signature followed by an 8-byte kernel pointer,
    so its stream count sits at offset 12 instead. Both are handled below.
    """
    if len(data) < 32:
        return None

    signature = data[:4]
    if signature == b"PMDM":
        try:
            stream_count = struct.unpack_from("<I", data, 8)[0]
            directory_rva = struct.unpack_from("<I", data, 12)[0]
        except struct.error:
            return None
        # The directory normally follows the 32-byte header, but the recorded RVA
        # is authoritative whenever it points inside the file.
        if 32 <= directory_rva < len(data):
            directory_offset = directory_rva
        else:
            directory_offset = 32
    elif signature in {b"PAGE", b"FULL", b"PAGU"}:
        try:
            stream_count = struct.unpack_from("<I", data, 8)[0]
            directory_rva = struct.unpack_from("<I", data, 16)[0]
        except struct.error:
            return None
        directory_offset = directory_rva if 0 < directory_rva < len(data) else 88
    else:
        return None

    code: int | None = None
    parameters: list[int] = []
    build = ""
    version = ""

    for index in range(min(stream_count, 512)):
        entry_offset = directory_offset + index * 12
        if entry_offset + 12 > len(data):
            break
        try:
            stream_type, _size, rva = struct.unpack_from("<III", data, entry_offset)
        except struct.error:
            break
        if rva < 0 or rva + 8 > len(data):
            continue

        try:
            if stream_type == STREAM_SYSTEM_INFO:
                major, minor, build_number = struct.unpack_from("<HHH", data, rva)
                if build_number:
                    build = str(build_number)
                    version = f"{major}.{minor} build {build_number}"
                if code is None:
                    for offset in range(rva + 8, min(rva + 96, len(data)) - 8, 4):
                        (candidate,) = struct.unpack_from("<I", data, offset)
                        if candidate in KNOWN_BUGCHECK_CODES:
                            code = candidate
                            for pindex in range(4):
                                ppos = offset + 4 + pindex * 8
                                if ppos + 8 <= len(data):
                                    (value,) = struct.unpack_from("<Q", data, ppos)
                                    parameters.append(value)
                            break
            elif stream_type == STREAM_BUGCHECK and code is None:
                (candidate,) = struct.unpack_from("<I", data, rva)
                if candidate in KNOWN_BUGCHECK_CODES:
                    code = candidate
                    for pindex in range(4):
                        ppos = rva + 4 + pindex * 8
                        if ppos + 8 <= len(data):
                            (value,) = struct.unpack_from("<Q", data, ppos)
                            parameters.append(value)
        except struct.error:
            continue

    if code is None:
        return None
    return code, parameters[:4], build, version


# 64-bit Windows tags some bugchecks by setting bit 28, so
# SYSTEM_THREAD_EXCEPTION_NOT_HANDLED is recorded as 0x1000007E.
_64BIT_TAG_BIT = 1 << 28


def _strip_high_bit(code: int) -> int:
    """Reduce a recorded code to the value the reference table is keyed on.

    Only bit 28 is cleared, and only when the full value is not itself a known
    code, so a genuine 64-bit-specific code such as 0xC000021A is left alone.
    """
    from .stopcodes import CODE_TO_NAME

    if code in CODE_TO_NAME:
        return code
    if code & _64BIT_TAG_BIT:
        return code & ~_64BIT_TAG_BIT
    return code


def name_for_code(code: int) -> str:
    """Look up a stop code name in the local reference table."""
    from .stopcodes import CODE_TO_NAME

    return CODE_TO_NAME.get(_strip_high_bit(code), "")


def analyse(data: bytes, filename: str, max_bytes: int) -> DumpAnalysis:
    """Validate and parse an uploaded dump. Raises DumpError when rejected."""
    safe_name = validate_extension(filename)
    validate_size(len(data), max_bytes)
    signature = validate_signature(data)

    analysis = DumpAnalysis(
        filename=safe_name,
        size_bytes=len(data),
        signature=signature,
        bugcheck=None,
        warnings=[
            "Parsed in memory only. This file is never saved and nothing inside it is executed.",
            "Dump files can contain fragments of filenames and file contents, so treat yours as private.",
        ],
    )

    parsed = None
    for parser, label in (
        (_parse_with_library, "minidump library"),
        (_parse_manually, "built-in parser"),
    ):
        try:
            parsed = parser(data)
        except Exception:  # noqa: BLE001 - any parser failure falls through
            parsed = None
        if parsed is not None:
            analysis.parse_method = label
            break

    if parsed is None:
        analysis.notes.append(
            "The file has a valid Windows dump signature, but the bugcheck code could not "
            "be read from it. That is normal for partial or kernel dumps rather than "
            "user-mode minidumps. Look up the stop code from the blue screen itself."
        )
        return analysis

    code, parameters, build, version = parsed
    code = _strip_high_bit(int(code))
    name = name_for_code(code)

    analysis.bugcheck = Bugcheck(
        code=code,
        name=name or "UNKNOWN_STOP_CODE",
        hex_code="0x%08X" % code,
        parameters=[int(p) & 0xFFFFFFFFFFFFFFFF for p in (parameters or [])],
        parameter_hints=list(PARAMETER_HINTS.get(code, ())),
        os_build=build,
        os_version=version,
    )
    if not name:
        analysis.notes.append(
            "We do not have a written guide for this stop code yet. The code and its "
            "parameters below are still useful when searching Microsoft's documentation "
            "or posting a support question."
        )
    return analysis
