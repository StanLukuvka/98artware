"""Checks that a Windows executable can actually load on Windows 98.

A modern toolchain will quietly produce a file that fails there with a vague
error, so this is verified on the host rather than discovered inside the VM.
"""

from __future__ import annotations

import struct
from pathlib import Path

MAX_SUBSYSTEM_VERSION = (4, 10)

# Every import the agent uses, each confirmed present in Windows 98.
ALLOWED_IMPORTS = {
    "KERNEL32.dll": {
        "CloseHandle",
        "CreateEventA",
        "CreateFileA",
        "CreateProcessA",
        "CreateThread",
        "CreateToolhelp32Snapshot",
        "EnterCriticalSection",
        "ExitProcess",
        "GetCommState",
        "GetFileSize",
        "GetLastError",
        "GetModuleFileNameA",
        "GetModuleHandleA",
        "GetOverlappedResult",
        "GetProcAddress",
        "GetProcessHeap",
        "GetTickCount",
        "HeapAlloc",
        "HeapFree",
        "InitializeCriticalSection",
        "LeaveCriticalSection",
        "LoadLibraryA",
        "Process32First",
        "Process32Next",
        "ReadFile",
        "ResetEvent",
        "SetCommState",
        "SetCommTimeouts",
        "SetFilePointer",
        "SetLastError",
        "SetUnhandledExceptionFilter",
        "SetupComm",
        "Sleep",
        "WriteFile",
        "lstrcmpA",
    },
    "USER32.dll": {
        "CreateWindowExA",
        "DefWindowProcA",
        "DispatchMessageA",
        "EnumChildWindows",
        "EnumWindows",
        "GetClassNameA",
        "GetMessageA",
        "GetWindowRect",
        "GetWindowTextA",
        "GetWindowThreadProcessId",
        "IsWindowVisible",
        "KillTimer",
        "PostMessageA",
        "RedrawWindow",
        "RegisterClassA",
        "SendMessageTimeoutA",
        "SetTimer",
        "TranslateMessage",
    },
    "GDI32.dll": {"GdiFlush"},
}

# Every import the picture window (VIEW.EXE) uses, each present in Windows 98.
VIEWER_IMPORTS = {
    "KERNEL32.dll": {
        "ExitProcess",
        "GetCommandLineA",
        "GetModuleHandleA",
    },
    "USER32.dll": {
        "BeginPaint",
        "CreateWindowExA",
        "DefWindowProcA",
        "DispatchMessageA",
        "EndPaint",
        "GetClientRect",
        "GetMessageA",
        "InvalidateRect",
        "LoadCursorA",
        "LoadIconA",
        "LoadImageA",
        "PostQuitMessage",
        "RegisterClassA",
        "ShowWindow",
        "TranslateMessage",
        "UpdateWindow",
    },
    "GDI32.dll": {
        "BitBlt",
        "CreateCompatibleDC",
        "DeleteDC",
        "GetObjectA",
        "SelectObject",
    },
}


class PEError(ValueError):
    pass


def read_imports(path: Path) -> tuple[tuple[int, int], dict[str, set[str]]]:
    """Return the (major, minor) subsystem version and the import table."""
    data = Path(path).read_bytes()
    if data[:2] != b"MZ":
        raise PEError(f"{path} is not an executable")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe : pe + 4] != b"PE\0\0":
        raise PEError(f"{path} has no PE header")
    section_count, optional_size = struct.unpack_from("<H12xH", data, pe + 6)
    optional = pe + 24
    if struct.unpack_from("<H", data, optional)[0] != 0x10B:
        raise PEError(f"{path} is not a 32-bit image")
    version = struct.unpack_from("<HH", data, optional + 48)
    import_rva = struct.unpack_from("<I", data, optional + 104)[0]

    sections = []
    for i in range(section_count):
        base = optional + optional_size + i * 40
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
            "<IIII", data, base + 8
        )
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def offset(rva: int) -> int:
        for virtual_address, size, raw_pointer in sections:
            if virtual_address <= rva < virtual_address + size:
                return raw_pointer + rva - virtual_address
        raise PEError(f"address {rva:#x} is outside every section")

    def text(rva: int) -> str:
        start = offset(rva)
        return data[start : data.index(b"\0", start)].decode("ascii")

    imports: dict[str, set[str]] = {}
    entry = offset(import_rva)
    while True:
        lookup, _, _, name_rva, thunks = struct.unpack_from("<IIIII", data, entry)
        if not name_rva:
            return version, imports
        names = imports.setdefault(text(name_rva), set())
        slot = offset(lookup or thunks)
        while thunk := struct.unpack_from("<I", data, slot)[0]:
            if not thunk & 0x80000000:
                names.add(text(thunk + 2))
            slot += 4
        entry += 20


def check_agent(path: Path) -> None:
    """Raise PEError if the agent would not load on Windows 98."""
    check_program(path, ALLOWED_IMPORTS)


def check_viewer(path: Path) -> None:
    """Raise PEError if the picture window would not load on Windows 98."""
    check_program(path, VIEWER_IMPORTS)


def check_program(path: Path, allowed: dict[str, set[str]]) -> None:
    """Raise PEError if a program needs a newer Windows or an unreviewed import."""
    version, imports = read_imports(path)
    if version > MAX_SUBSYSTEM_VERSION:
        raise PEError(f"{path} needs Windows {version[0]}.{version[1]}")
    for dll, names in imports.items():
        unknown = names - allowed.get(dll, set())
        if unknown:
            raise PEError(
                f"{path} imports unreviewed functions from {dll}: {sorted(unknown)}"
            )
