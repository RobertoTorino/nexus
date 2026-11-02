# SPDX-License-Identifier: GPL-3.0-or-later
"""The screen: finding it, its serial port and its protocol. No Qt, so it is tested on its own. The protocol is the
BC250 suite's USB IPS3.5 (bc250-bazzite/apps/ips35/usb_ips35/screen.py), the port Windows' own.

Turzx's USB IPS screens (the Turing Smart Screen 3.5" and the UsbMonitor 3.5", 5" and 7" of the same family) are USB
serial devices (CDC-ACM, USB ID 1a86:5722): Windows gives them its in-box usbser driver, which makes them a COM port
(COM3 on the owner's Ally X through its dock, 02-11-2026), so they need no driver of their own and no administrator.
The port's name is the device's own setting, PortName in its Device Parameters (read-only, in any Windows language).

Each command is 6 bytes: four 10-bit values (x, y, end x, end y) packed into the first five bytes, then the command.
A picture is a DISPLAY_BITMAP command for a rectangle followed by its pixels, RGB565 little-endian, row by row, so a
part of the screen can be redrawn on its own. On the owner's Turing 3.5" (22-10-2026 on the BC-250, 02-11-2026 on the
Ally X): no answer to HELLO, a full screen of 320x480 takes 1.8 s (about 166 KB/s), a partial update works, and
brightness runs from 0 (brightest) to 255 (darkest).

The screen does not resynchronize by itself: a picture cut off halfway (the app killed while sending) leaves it
waiting for the rest, and everything sent after that, commands included, lands in that picture, shifted. reset()
floods the port with the RESET command byte, as much as the largest picture: while the screen still waits for pixels
the bytes fill them, and then whatever 6 bytes it reads as a command are RESET. The screen restarts (it leaves USB and
is back about 2 s later) in a clean state; on Windows the write then fails at once (ERROR_GEN_FAILURE).

A command must be a USB transfer of its own: the screen takes the command from the start of a 64-byte USB packet and
drops the rest of that packet (the owner's Turing 3.5", 22-10-2026). Port.write therefore returns only once a write
has gone out (WriteFile on a port opened without overlapped I/O, then FlushFileBuffers), and draw() writes the command
and the pixels apart."""

from __future__ import annotations

import ctypes
import sys
import time
from dataclasses import dataclass

VENDOR, PRODUCT = "1a86", "5722"
HARDWARE_ID = f"USB\\VID_{VENDOR.upper()}&PID_{PRODUCT.upper()}"   # the start of its instance ID

RESET, CLEAR, SCREEN_OFF, SCREEN_ON, SET_BRIGHTNESS, SET_ORIENTATION, DISPLAY_BITMAP, HELLO = (
    101, 102, 108, 109, 110, 121, 197, 69)
PORTRAIT = 0                                    # the screen's own orientation; the app turns its picture itself
HELLO_TIMEOUT_S = 1.0
WRITE_TIMEOUT_MS = 10_000                       # a whole 7" screen is about 7 s at the screen's speed
BAUD = 115200                                   # CDC-ACM ignores the speed; set as the vendor's app does


@dataclass(frozen=True)
class Model:
    name: str
    short: str                                  # for the cards and the pane
    width: int                                  # in the screen's portrait orientation
    height: int


TURING_35 = Model('Turing Smart Screen 3.5"', 'Turing 3.5"', 320, 480)
# The UsbMonitor screens answer HELLO with six times their size code; the Turing 3.5" does not answer.
MODELS = {bytes([1] * 6): Model('UsbMonitor 3.5"', 'UsbMonitor 3.5"', 320, 480),
          bytes([2] * 6): Model('UsbMonitor 5"', 'UsbMonitor 5"', 480, 800),
          bytes([3] * 6): Model('UsbMonitor 7"', 'UsbMonitor 7"', 600, 1024)}


FLOOD_BYTES = max(m.width * m.height for m in MODELS.values()) * 2 + 6     # the largest picture, with its command


def model_for(reply: bytes) -> Model:
    return MODELS.get(reply[:6], TURING_35)


@dataclass(frozen=True)
class Found:
    """A screen on USB: its COM port and its instance ID (which holds the device's serial number: never shown or
    logged)."""
    port: str                                   # COM3
    instance: str


# Windows' errors: the port is gone (unplugged), a write failed (the screen left USB), another program has the port
ERROR_FILE_NOT_FOUND, ERROR_ACCESS_DENIED, ERROR_GEN_FAILURE, ERROR_SHARING_VIOLATION = 2, 5, 31, 32
IN_USE = (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION)

CR_SUCCESS = 0
CM_GETIDLIST_FILTER_ENUMERATOR, CM_GETIDLIST_FILTER_PRESENT = 0x1, 0x100


def present(enumerator: str = "USB") -> list[str]:
    """The instance IDs of the present USB devices, through Windows' Configuration Manager (cfgmgr32)."""
    if sys.platform != "win32":
        return []
    from ctypes import wintypes as w
    cfg = ctypes.WinDLL("cfgmgr32")
    cfg.CM_Get_Device_ID_List_SizeW.argtypes = [ctypes.POINTER(w.ULONG), w.LPCWSTR, w.ULONG]
    cfg.CM_Get_Device_ID_ListW.argtypes = [w.LPCWSTR, ctypes.c_void_p, w.ULONG, w.ULONG]
    flags = CM_GETIDLIST_FILTER_ENUMERATOR | CM_GETIDLIST_FILTER_PRESENT
    size = w.ULONG()
    if cfg.CM_Get_Device_ID_List_SizeW(ctypes.byref(size), enumerator, flags) != CR_SUCCESS:
        return []
    buffer = ctypes.create_unicode_buffer(size.value + 1)
    if cfg.CM_Get_Device_ID_ListW(enumerator, buffer, len(buffer), flags) != CR_SUCCESS:
        return []
    return [part for part in ctypes.wstring_at(ctypes.addressof(buffer), len(buffer)).split("\0") if part]


def port_name(instance: str) -> str:
    """The COM port usbser gave the device ("" when it has none yet)."""
    if sys.platform != "win32":
        return ""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            f"SYSTEM\\CurrentControlSet\\Enum\\{instance}\\Device Parameters") as key:
            value, _kind = winreg.QueryValueEx(key, "PortName")
    except OSError:
        return ""
    return str(value) if str(value).upper().startswith("COM") else ""


def find(devices=present, port_of=port_name) -> list[Found]:
    """The screens plugged in that have a COM port, by USB ID (a composite device's interface too: ...&MI_00)."""
    found = []
    for instance in devices():
        head = instance.upper()
        if head == HARDWARE_ID or head.startswith(HARDWARE_ID + "\\") or head.startswith(HARDWARE_ID + "&"):
            port = port_of(instance)
            if port:
                found.append(Found(port, instance))
    return found


def command(cmd: int, x: int = 0, y: int = 0, ex: int = 0, ey: int = 0) -> bytes:
    return bytes([x >> 2, ((x & 3) << 6) + (y >> 4), ((y & 15) << 4) + (ex >> 6),
                  ((ex & 63) << 2) + (ey >> 8), ey & 255, cmd])


def brightness_command(percent: int) -> bytes:
    """0..100 % as the screen's 255 (darkest) .. 0 (brightest)."""
    percent = max(0, min(100, percent))
    return command(SET_BRIGHTNESS, round(255 - percent * 255 / 100))


def orientation_command(model: Model, orientation: int = PORTRAIT) -> bytes:
    buf = bytearray(16)
    buf[5] = SET_ORIENTATION
    buf[6] = orientation + 100
    buf[7:11] = bytes([model.width >> 8, model.width & 255, model.height >> 8, model.height & 255])
    return bytes(buf)


def bitmap_command(x: int, y: int, width: int, height: int) -> bytes:
    return command(DISPLAY_BITMAP, x, y, x + width - 1, y + height - 1)


class PortError(OSError):
    """The port could not be opened or written; winerror says why (IN_USE: another program has it)."""

    def __init__(self, code: int, what: str):
        super().__init__(code, f"{what} failed: {ctypes.FormatError(code).strip() if sys.platform == 'win32' else code}")
        self.winerror = code

    @property
    def in_use(self) -> bool:
        return self.winerror in IN_USE


class _DCB(ctypes.Structure):
    _fields_ = [("DCBlength", ctypes.c_uint32), ("BaudRate", ctypes.c_uint32), ("flags", ctypes.c_uint32),
                ("wReserved", ctypes.c_uint16), ("XonLim", ctypes.c_uint16), ("XoffLim", ctypes.c_uint16),
                ("ByteSize", ctypes.c_ubyte), ("Parity", ctypes.c_ubyte), ("StopBits", ctypes.c_ubyte),
                ("XonChar", ctypes.c_char), ("XoffChar", ctypes.c_char), ("ErrorChar", ctypes.c_char),
                ("EofChar", ctypes.c_char), ("EvtChar", ctypes.c_char), ("wReserved1", ctypes.c_uint16)]


class _Timeouts(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in ("ReadIntervalTimeout", "ReadTotalTimeoutMultiplier",
                                                     "ReadTotalTimeoutConstant", "WriteTotalTimeoutMultiplier",
                                                     "WriteTotalTimeoutConstant")]


DCB_BINARY, DCB_DTR_ON, DCB_RTS_ON = 0x1, 0x1 << 4, 0x1 << 12      # raw bytes, DTR and RTS on, no flow control
GENERIC_READ_WRITE, OPEN_EXISTING, PURGE_ALL = 0xC0000000, 3, 0xF
MAXDWORD = 0xFFFFFFFF


def _kernel():
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.WriteFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    kernel.ReadFile.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD), ctypes.c_void_p]
    kernel.FlushFileBuffers.argtypes = [w.HANDLE]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.GetCommState.argtypes = [w.HANDLE, ctypes.POINTER(_DCB)]
    kernel.SetCommState.argtypes = [w.HANDLE, ctypes.POINTER(_DCB)]
    kernel.SetCommTimeouts.argtypes = [w.HANDLE, ctypes.POINTER(_Timeouts)]
    kernel.PurgeComm.argtypes = [w.HANDLE, w.DWORD]
    return kernel


class Port:
    """The screen's COM port, raw, opened for this app alone. A write returns once it has gone out to the screen, so
    the next write starts a new USB transfer (see above); an unplugged screen raises PortError."""

    def __init__(self, name: str):
        if sys.platform != "win32":
            raise PortError(ERROR_FILE_NOT_FOUND, "Opening the port")
        self._k = _kernel()
        handle = self._k.CreateFileW(f"\\\\.\\{name}", GENERIC_READ_WRITE, 0, None, OPEN_EXISTING, 0, None)
        if not handle or handle == ctypes.c_void_p(-1).value:
            raise PortError(ctypes.get_last_error(), f"Opening {name}")
        self.handle = handle
        try:
            dcb = _DCB(DCBlength=ctypes.sizeof(_DCB))
            if not self._k.GetCommState(handle, ctypes.byref(dcb)):
                raise PortError(ctypes.get_last_error(), "Reading the port's settings")
            dcb.BaudRate, dcb.ByteSize, dcb.Parity, dcb.StopBits = BAUD, 8, 0, 0
            dcb.flags = DCB_BINARY | DCB_DTR_ON | DCB_RTS_ON
            if not self._k.SetCommState(handle, ctypes.byref(dcb)):
                raise PortError(ctypes.get_last_error(), "Setting the port")
            # A read returns what came within its timeout; a write that cannot go out ends with an error
            timeouts = _Timeouts(MAXDWORD, MAXDWORD, round(HELLO_TIMEOUT_S * 1000), 0, WRITE_TIMEOUT_MS)
            self._k.SetCommTimeouts(handle, ctypes.byref(timeouts))
            self._k.PurgeComm(handle, PURGE_ALL)
        except OSError:
            self._k.CloseHandle(handle)
            raise

    def write(self, data: bytes) -> None:
        from ctypes import wintypes as w
        buffer = ctypes.create_string_buffer(bytes(data), len(data))
        done = w.DWORD()
        if not self._k.WriteFile(self.handle, buffer, len(data), ctypes.byref(done), None):
            raise PortError(ctypes.get_last_error(), "Writing to the screen")
        if done.value != len(data):
            raise PortError(ERROR_GEN_FAILURE, f"Writing to the screen ({done.value} of {len(data)} bytes)")
        self._k.FlushFileBuffers(self.handle)

    def read(self, size: int, timeout: float) -> bytes:
        """What the screen sends within the port's read timeout (HELLO_TIMEOUT_S; *timeout* as on Linux)."""
        from ctypes import wintypes as w
        data, end = b"", time.monotonic() + timeout
        while len(data) < size and time.monotonic() < end:
            buffer = ctypes.create_string_buffer(size - len(data))
            got = w.DWORD()
            if not self._k.ReadFile(self.handle, buffer, len(buffer), ctypes.byref(got), None) or not got.value:
                break
            data += buffer.raw[:got.value]
        return data

    def close(self) -> None:
        if getattr(self, "handle", None):
            self._k.CloseHandle(self.handle)
            self.handle = None


class Screen:
    """The commands, on a Port (or anything with write and read whose every write is a transfer of its own)."""

    def __init__(self, port):
        self.port = port
        self.model = TURING_35

    def reset(self) -> None:
        """Restarts the screen, also from a picture cut off halfway. The port is gone afterwards: the write usually
        ends with an error as the screen leaves USB."""
        self.port.write(bytes([RESET]) * FLOOD_BYTES)

    def hello(self) -> Model:
        self.port.write(bytes([HELLO] * 6))
        self.model = model_for(self.port.read(6, HELLO_TIMEOUT_S))
        return self.model

    def start(self) -> None:
        """The screen in its portrait orientation and switched on."""
        self.port.write(orientation_command(self.model))
        self.port.write(command(SCREEN_ON))

    def brightness(self, percent: int) -> None:
        self.port.write(brightness_command(percent))

    def power(self, on: bool) -> None:
        self.port.write(command(SCREEN_ON if on else SCREEN_OFF))

    def draw(self, frame: bytes, rect: tuple[int, int, int, int]) -> None:
        """Sends *rect* (x, y, width, height) of *frame*, a whole screen of RGB565 little-endian."""
        x, y, width, height = rect
        stride = self.model.width
        if len(frame) != stride * self.model.height * 2:
            raise ValueError(f"a frame of {len(frame)} bytes for a screen of {stride}x{self.model.height}")
        rows = (frame[(row * stride + x) * 2:(row * stride + x + width) * 2] for row in range(y, y + height))
        self.port.write(bitmap_command(x, y, width, height))
        self.port.write(b"".join(rows))
