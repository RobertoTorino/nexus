# SPDX-License-Identifier: GPL-3.0-or-later
"""Giving the camera's boot loader Microsoft's own WinUSB driver, as Device Manager does when you pick "WinUsb Device"
by hand: winusb.inf's generic model (section WINUSB, USB\\MS_COMP_WINUSB), which ships with Windows and is signed by
Microsoft, so no certificate and no driver of anyone else's. It takes an administrator: the app starts itself again
with --bind and the boot loader's instance ID, which Windows' prompt asks for (owner, 31-10-2026: the one
administrator step of the app). The elevated copy binds only a boot loader (05a9:0580) and ends. After that a user
opens the boot loader without an administrator, on that USB port; another port asks once more.

The steps (setupapi and newdev, ctypes): open the device; a device that never had a driver has no class yet, so it
gets the USB devices' class (as a string, the way Windows keeps it); the class driver list is built from winusb.inf
alone; the WINUSB model is selected by its section and hardware ID (its description is translated); DiInstallDevice
installs it."""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from collections.abc import Callable
from ctypes import wintypes as w
from pathlib import Path

USB_DEVICE_CLASS = "{88BAE032-5A81-49F0-BC3D-A4FF138216D6}"
INF = r"%SystemRoot%\INF\winusb.inf"
SECTION, HARDWARE_ID = "WINUSB", "USB\\MS_COMP_WINUSB"
BOOT_LOADER = re.compile(r"USB\\VID_05A9&PID_0580\\[^\\]+", re.IGNORECASE)
DI_ENUMSINGLEINF = 0x00010000
DI_FLAGSEX_ALLOWEXCLUDEDDRVS = 0x00000800
SPDIT_CLASSDRIVER = 1
SPDRP_CLASSGUID = 8
SEE_MASK_NOCLOSEPROCESS = 0x00000040
ERROR_CANCELLED = 1223
INFINITE = 0xFFFFFFFF

# The elevated copy's exit codes
BOUND, NOT_A_BOOT_LOADER, FAILED = 0, 2, 3


class DriverError(Exception):
    pass


class _DevInfoData(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("ClassGuid", ctypes.c_ubyte * 16), ("DevInst", w.DWORD),
                ("Reserved", ctypes.c_size_t)]


class _InstallParams(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("Flags", w.DWORD), ("FlagsEx", w.DWORD), ("hwndParent", w.HWND),
                ("InstallMsgHandler", ctypes.c_void_p), ("InstallMsgHandlerContext", ctypes.c_void_p),
                ("FileQueue", ctypes.c_void_p), ("ClassInstallReserved", ctypes.c_size_t), ("Reserved", w.DWORD),
                ("DriverPath", w.WCHAR * 260)]


class _DriverInfo(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("DriverType", w.DWORD), ("Reserved", ctypes.c_size_t),
                ("Description", w.WCHAR * 256), ("MfgName", w.WCHAR * 256), ("ProviderName", w.WCHAR * 256),
                ("DriverDate", w.FILETIME), ("DriverVersion", ctypes.c_ulonglong)]


class _DriverDetail(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("InfDate", w.FILETIME), ("CompatIDsOffset", w.DWORD),
                ("CompatIDsLength", w.DWORD), ("Reserved", ctypes.c_size_t), ("SectionName", w.WCHAR * 256),
                ("InfFileName", w.WCHAR * 260), ("DrvDescription", w.WCHAR * 256), ("HardwareID", w.WCHAR * 1)]


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("fMask", w.ULONG), ("hwnd", w.HWND), ("lpVerb", w.LPCWSTR),
                ("lpFile", w.LPCWSTR), ("lpParameters", w.LPCWSTR), ("lpDirectory", w.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", w.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", w.LPCWSTR),
                ("hkeyClass", w.HKEY), ("dwHotKey", w.DWORD), ("hIcon", w.HANDLE), ("hProcess", w.HANDLE)]


def _setup():
    api = ctypes.WinDLL("setupapi", use_last_error=True)
    api.SetupDiCreateDeviceInfoList.restype = ctypes.c_void_p
    api.SetupDiCreateDeviceInfoList.argtypes = [ctypes.c_void_p, w.HWND]
    api.SetupDiOpenDeviceInfoW.argtypes = [ctypes.c_void_p, w.LPCWSTR, w.HWND, w.DWORD, ctypes.c_void_p]
    for name in ("SetupDiGetDeviceInstallParamsW", "SetupDiSetDeviceInstallParamsW", "SetupDiSetSelectedDriverW"):
        getattr(api, name).argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    api.SetupDiSetDeviceRegistryPropertyW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, ctypes.c_void_p,
                                                      w.DWORD]
    api.SetupDiBuildDriverInfoList.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD]
    api.SetupDiEnumDriverInfoW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.c_void_p]
    api.SetupDiGetDriverInfoDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                                w.DWORD, ctypes.POINTER(w.DWORD)]
    api.SetupDiDestroyDeviceInfoList.argtypes = [ctypes.c_void_p]
    newdev = ctypes.WinDLL("newdev", use_last_error=True)
    newdev.DiInstallDevice.argtypes = [w.HWND, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, w.DWORD,
                                       ctypes.POINTER(w.BOOL)]
    return api, newdev


def _check(ok, what: str) -> None:
    if not ok:
        code = ctypes.get_last_error()
        raise DriverError(f"{what}: {ctypes.FormatError(code).strip()} ({code})")


def _winusb_model(api, devs, data) -> _DriverInfo | None:
    params = _InstallParams(cbSize=ctypes.sizeof(_InstallParams))
    _check(api.SetupDiGetDeviceInstallParamsW(devs, ctypes.byref(data), ctypes.byref(params)), "Reading the device")
    params.Flags |= DI_ENUMSINGLEINF
    params.FlagsEx |= DI_FLAGSEX_ALLOWEXCLUDEDDRVS
    params.DriverPath = str(Path(INF.replace("%SystemRoot%", _windows())))
    _check(api.SetupDiSetDeviceInstallParamsW(devs, ctypes.byref(data), ctypes.byref(params)), "Pointing at winusb.inf")
    _check(api.SetupDiBuildDriverInfoList(devs, ctypes.byref(data), SPDIT_CLASSDRIVER), "Listing winusb.inf")
    index = 0
    while True:
        model = _DriverInfo(cbSize=ctypes.sizeof(_DriverInfo))
        if not api.SetupDiEnumDriverInfoW(devs, ctypes.byref(data), SPDIT_CLASSDRIVER, index, ctypes.byref(model)):
            return None
        buffer = ctypes.create_string_buffer(8192)
        detail = _DriverDetail.from_buffer(buffer)
        detail.cbSize = ctypes.sizeof(_DriverDetail)
        needed = w.DWORD()
        if api.SetupDiGetDriverInfoDetailW(devs, ctypes.byref(data), ctypes.byref(model), buffer, len(buffer),
                                           ctypes.byref(needed)):
            hardware_id = ctypes.wstring_at(ctypes.addressof(buffer) + _DriverDetail.HardwareID.offset)
            if detail.SectionName.upper() == SECTION and hardware_id.upper() == HARDWARE_ID:
                return model
        index += 1


def _windows() -> str:
    return os.environ.get("SystemRoot", r"C:\Windows")


def bind(instance: str) -> None:
    """WinUSB on the boot loader *instance*; raises DriverError with what went wrong. Needs an administrator."""
    if not BOOT_LOADER.fullmatch(instance):
        raise DriverError(f"Not the camera's boot loader: {instance}")
    api, newdev = _setup()
    devs = api.SetupDiCreateDeviceInfoList(None, None)
    _check(devs and devs != ctypes.c_void_p(-1).value, "Starting the setup")
    try:
        data = _DevInfoData(cbSize=ctypes.sizeof(_DevInfoData))
        _check(api.SetupDiOpenDeviceInfoW(devs, instance, None, 0, ctypes.byref(data)), "Finding the camera")
        if not any(data.ClassGuid):         # it never had a driver: the USB devices' class first
            text = ctypes.create_unicode_buffer(USB_DEVICE_CLASS)
            _check(api.SetupDiSetDeviceRegistryPropertyW(devs, ctypes.byref(data), SPDRP_CLASSGUID, text,
                                                         ctypes.sizeof(text)), "Giving the camera its class")
        model = _winusb_model(api, devs, data)
        if model is None:
            raise DriverError("winusb.inf has no WinUsb Device model on this Windows")
        _check(api.SetupDiSetSelectedDriverW(devs, ctypes.byref(data), ctypes.byref(model)), "Selecting WinUSB")
        reboot = w.BOOL()
        _check(newdev.DiInstallDevice(None, devs, ctypes.byref(data), ctypes.byref(model), 0, ctypes.byref(reboot)),
               "Installing WinUSB")
    finally:
        api.SetupDiDestroyDeviceInfoList(devs)


def elevated_command(instance: str) -> list[str]:
    """This app with --bind *instance*: the installed program, or from a checkout Python with the package and core on
    its path (an elevated process gets the user's environment, not this one's PYTHONPATH)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--bind", instance]
    import bc250_core
    paths = [str(Path(bc250_core.__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1])]
    boot = f"import sys; sys.path[:0] = {paths!r}; from usb_hd_cam.__main__ import main; sys.exit(main())"
    program = Path(sys.executable)
    windowless = program.with_name("pythonw.exe")
    return [str(windowless if windowless.is_file() else program), "-c", boot, "--bind", instance]


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


def ask(instance: str, run: Callable[[list[str]], int] = _run_elevated) -> str:
    """Allow access: the elevated copy binds WinUSB to *instance*. "" when it did, else what to tell the user."""
    try:
        code = run(elevated_command(instance))
    except OSError as error:
        return f"Windows did not start the driver's install: {error}."
    if code == BOUND:
        return ""
    if code == ERROR_CANCELLED:
        return "Windows' prompt was declined: the camera still has no driver."
    if code == NOT_A_BOOT_LOADER:
        return "That is not the camera's boot loader any more: look for the camera again."
    return f"Windows did not install the driver (code {code}). The app's log says why."
