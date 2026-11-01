# SPDX-License-Identifier: GPL-3.0-or-later
"""The device's own BIOS: its maker, version and date, and the values of its settings.

The identity is what Windows keeps of the SMBIOS tables (HKLM\\HARDWARE\\DESCRIPTION\\System\\BIOS, read only), with
no administrator. The settings are UEFI variables: Windows reads them only for a process with the "modify firmware
environment values" privilege, which only an administrator has (owner, 01-11-2026: this app's administrator step,
approved for reading). The app starts its own program again with --read-variables and two files: the request (the
variables the BIOS file's setup screens store their settings in) and the result. Windows' prompt asks for it; the
elevated copy reads those variables, writes their bytes to the result and ends. It never writes a variable: only
GetFirmwareEnvironmentVariableExW is called. A variable that may hold personal data (Wi-Fi networks, network and
boot entries, keys, passwords) is never asked for (owner, 29-10-2026: the privacy rule), by either copy.

A BIOS keeps many variables to itself once Windows runs (AMI's Setup, for one): those are "not readable" and their
settings show the file's value or default."""

from __future__ import annotations

import base64
import ctypes
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from ctypes import wintypes as w
from pathlib import Path

from .bios import Identity, Key

BIOS_KEY = r"HARDWARE\DESCRIPTION\System\BIOS"
PRIVATE = re.compile(r"wifi|wlan|bluetooth|network|vlan|lan(?!g)|tls|http|rtk|mac|serial|password|systemaccess|"
                     r"boot|driver|keys?$|^(pk|kek|db|dbx|dbt)$|legacy|usbmass|info$", re.IGNORECASE)
REQUEST, RESULT = "variables-request.json", "variables.json"
BUFFER = 64 * 1024
PRIVILEGE = "SeSystemEnvironmentPrivilege"
SE_PRIVILEGE_ENABLED = 0x2
TOKEN_ADJUST_PRIVILEGES, TOKEN_QUERY = 0x20, 0x8
ERROR_NOT_ALL_ASSIGNED, ERROR_INSUFFICIENT_BUFFER, ERROR_ENVVAR_NOT_FOUND = 1300, 122, 203
SEE_MASK_NOCLOSEPROCESS = 0x00000040
ERROR_CANCELLED = 1223
INFINITE = 0xFFFFFFFF

# The elevated copy's exit codes
READ, BAD_REQUEST, FAILED, NO_PRIVILEGE = 0, 2, 3, 4


class DeviceError(Exception):
    pass


def identity(read: Callable[[str], str] | None = None) -> tuple[Identity, str]:
    """(the device's BIOS, its model: "ROG Xbox Ally X RC73XA_RC73XA"); "" for what Windows does not report."""
    read = read or _registry
    model = read("SystemProductName") or read("BaseBoardProduct")
    return Identity(read("BIOSVendor"), read("BIOSVersion"), read("BIOSReleaseDate")), model


def _registry(name: str) -> str:
    if sys.platform != "win32":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, BIOS_KEY) as key:
            value = winreg.QueryValueEx(key, name)[0]
    except OSError:
        return ""
    return str(value).strip()


def private(key: Key) -> bool:
    """Whether a variable may hold personal data, so the app never reads it."""
    return bool(PRIVATE.search(key[1]))


def wanted(stores: Iterable[Key]) -> list[Key]:
    return [key for key in stores if not private(key)]


# --- The elevated copy -----------------------------------------------------------------------------------------

class _Luid(ctypes.Structure):
    _fields_ = [("LowPart", w.DWORD), ("HighPart", w.LONG)]


class _TokenPrivileges(ctypes.Structure):
    _fields_ = [("PrivilegeCount", w.DWORD), ("Luid", _Luid), ("Attributes", w.DWORD)]


def _enable_privilege() -> None:
    """The privilege an administrator has but that is off until a process turns it on."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = w.HANDLE
    advapi.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    advapi.LookupPrivilegeValueW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.POINTER(_Luid)]
    advapi.AdjustTokenPrivileges.argtypes = [w.HANDLE, w.BOOL, ctypes.POINTER(_TokenPrivileges), w.DWORD,
                                             ctypes.c_void_p, ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    token = w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(), TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
                                   ctypes.byref(token)):
        raise DeviceError(f"Opening the process's rights: {ctypes.FormatError(ctypes.get_last_error()).strip()}")
    try:
        privileges = _TokenPrivileges(PrivilegeCount=1, Attributes=SE_PRIVILEGE_ENABLED)
        if not advapi.LookupPrivilegeValueW(None, PRIVILEGE, ctypes.byref(privileges.Luid)):
            raise DeviceError(f"Looking up {PRIVILEGE}: {ctypes.FormatError(ctypes.get_last_error()).strip()}")
        ok = advapi.AdjustTokenPrivileges(token, False, ctypes.byref(privileges), 0, None, None)
        if not ok or ctypes.get_last_error() == ERROR_NOT_ALL_ASSIGNED:
            raise DeviceError("This process has no right to read the firmware's variables: it needs an "
                              "administrator.")
    finally:
        kernel.CloseHandle(token)


def read_variable(name: str, guid: str) -> bytes | None:
    """One UEFI variable's bytes, None when the BIOS does not let Windows read it. Needs _enable_privilege()."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFirmwareEnvironmentVariableExW.argtypes = [w.LPCWSTR, w.LPCWSTR, ctypes.c_void_p, w.DWORD,
                                                         ctypes.POINTER(w.DWORD)]
    kernel.GetFirmwareEnvironmentVariableExW.restype = w.DWORD
    size = BUFFER
    while size <= 16 * BUFFER:
        buffer = ctypes.create_string_buffer(size)
        attributes = w.DWORD()
        length = kernel.GetFirmwareEnvironmentVariableExW(name, "{" + guid + "}", buffer, size,
                                                          ctypes.byref(attributes))
        if length:
            return buffer.raw[:length]
        code = ctypes.get_last_error()
        if code != ERROR_INSUFFICIENT_BUFFER:
            return None
        size *= 4
    return None


def read_all(keys: Iterable[Key], read: Callable[[str, str], bytes | None] = read_variable) -> dict[str, object]:
    """The result the elevated copy writes: {"read": {"GUID|Name": base64}, "missing": ["GUID|Name"]}; a private
    variable is left out even when asked for."""
    found: dict[str, str] = {}
    missing: list[str] = []
    for guid, name in keys:
        if private((guid, name)):
            continue
        data = read(name, guid)
        if data is None:
            missing.append(f"{guid}|{name}")
        else:
            found[f"{guid}|{name}"] = base64.b64encode(data).decode("ascii")
    return {"read": found, "missing": missing}


def run_request(request: Path, result: Path, enable: Callable[[], None] = _enable_privilege,
                read: Callable[[str, str], bytes | None] = read_variable) -> int:
    """The elevated copy: the request's variables read and written to *result*; the exit code says how it went."""
    if request.name != REQUEST or result.name != RESULT:
        return BAD_REQUEST
    try:
        asked = json.loads(request.read_text(encoding="utf-8"))["variables"]
        keys = [(str(guid).upper(), str(name)) for guid, name in asked]
    except (OSError, ValueError, KeyError, TypeError):
        return BAD_REQUEST
    try:
        enable()
    except DeviceError:
        return NO_PRIVILEGE
    try:
        result.write_text(json.dumps(read_all(keys, read)), encoding="utf-8")
    except OSError:
        return FAILED
    return READ


# --- Asking for it ---------------------------------------------------------------------------------------------

class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("fMask", w.ULONG), ("hwnd", w.HWND), ("lpVerb", w.LPCWSTR),
                ("lpFile", w.LPCWSTR), ("lpParameters", w.LPCWSTR), ("lpDirectory", w.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", w.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", w.LPCWSTR),
                ("hkeyClass", w.HKEY), ("dwHotKey", w.DWORD), ("hIcon", w.HANDLE), ("hProcess", w.HANDLE)]


def elevated_command(request: Path, result: Path) -> list[str]:
    """This app with --read-variables: the installed program, or from a checkout Python with the package and core on
    its path (an elevated process gets the user's environment, not this one's PYTHONPATH)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--read-variables", str(request), str(result)]
    import bc250_core
    paths = [str(Path(bc250_core.__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1])]
    boot = f"import sys; sys.path[:0] = {paths!r}; from bios_reader.__main__ import main; sys.exit(main())"
    program = Path(sys.executable)
    windowless = program.with_name("pythonw.exe")
    return [str(windowless if windowless.is_file() else program), "-c", boot, "--read-variables", str(request),
            str(result)]


def _run_elevated(command: list[str]) -> int:
    """Windows' prompt, then *command* as administrator, waited for: its exit code, or ERROR_CANCELLED when the
    prompt was declined."""
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(_ShellExecuteInfo)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    run = _ShellExecuteInfo(cbSize=ctypes.sizeof(_ShellExecuteInfo), fMask=SEE_MASK_NOCLOSEPROCESS, lpVerb="runas",
                            lpFile=command[0], lpParameters=subprocess.list2cmdline(command[1:]), nShow=0)
    if not shell.ShellExecuteExW(ctypes.byref(run)):
        return ctypes.get_last_error() or ERROR_CANCELLED
    try:
        kernel.WaitForSingleObject(run.hProcess, INFINITE)
        code = w.DWORD()
        kernel.GetExitCodeProcess(run.hProcess, ctypes.byref(code))
        return code.value
    finally:
        kernel.CloseHandle(run.hProcess)


def read_settings(keys: Iterable[Key], folder: Path,
                  run: Callable[[list[str]], int] = _run_elevated) -> tuple[dict[Key, bytes], list[Key]]:
    """Read the device's variables *keys* through the elevated copy: (the ones read, the ones the BIOS keeps to
    itself). Raises DeviceError with what to tell the user. The two files are removed afterwards."""
    asked = wanted(keys)
    if not asked:
        raise DeviceError("The BIOS file's setup screens name no variable this app reads.")
    folder.mkdir(parents=True, exist_ok=True)
    request, result = folder / REQUEST, folder / RESULT
    result.unlink(missing_ok=True)
    request.write_text(json.dumps({"variables": [list(key) for key in asked]}), encoding="utf-8")
    try:
        try:
            code = run(elevated_command(request, result))
        except OSError as error:
            raise DeviceError(f"Windows did not start the read: {error}.") from error
        if code == ERROR_CANCELLED:
            raise DeviceError("Windows' prompt was declined: the settings were not read.")
        if code == NO_PRIVILEGE:
            raise DeviceError("Windows did not give the read an administrator's rights.")
        if code != READ:
            raise DeviceError(f"The settings were not read (code {code}). The app's log says why.")
        try:
            found = json.loads(result.read_text(encoding="utf-8"))
            read = {_key(text): base64.b64decode(data) for text, data in found["read"].items()}
            missing = [_key(text) for text in found["missing"]]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise DeviceError(f"The read's result could not be read: {error}") from error
    finally:
        request.unlink(missing_ok=True)
        result.unlink(missing_ok=True)
    return read, missing


def _key(text: str) -> Key:
    guid, _, name = text.partition("|")
    return guid.upper(), name
