# SPDX-License-Identifier: GPL-3.0-or-later
"""The screen: finding it, its serial port and its protocol. No Qt, so it is tested on its own.

Turzx's USB IPS screens (the Turing Smart Screen 3.5" and the UsbMonitor 3.5", 5" and 7" of the same family) are USB
serial devices (CDC-ACM, USB ID 1a86:5722): the kernel's cdc_acm driver makes them /dev/ttyACM<n>, so they need no
driver of their own. The Windows "driver" is only Microsoft's usbser.inf.

Each command is 6 bytes: four 10-bit values (x, y, end x, end y) packed into the first five bytes, then the command.
A picture is a DISPLAY_BITMAP command for a rectangle followed by its pixels, RGB565 little-endian, row by row, so a
part of the screen can be redrawn on its own. On the owner's Turing 3.5" (22-10-2026): no answer to HELLO, a full
screen of 320x480 takes 1.85 s (about 166 KB/s), a partial update works, and brightness runs from 0 (brightest)
to 255 (darkest).

The screen does not resynchronise by itself: a picture cut off halfway (the app killed while sending, on the owner's
board 22-10-2026) leaves it waiting for the rest, and everything sent after that, commands included, lands in that
picture, shifted. reset() floods the port with the RESET command byte, as much as the largest picture: while the
screen still waits for pixels the bytes fill them, and then whatever 6 bytes it reads as a command are RESET. The
screen restarts (it leaves USB and is back about 2 s later) in a clean state.

A command must be a USB transfer of its own: the screen takes the command from the start of a 64-byte USB packet and
drops the rest of that packet. With a picture's pixels in the same write, its first 58 bytes (29 pixels) were lost:
the picture showed 29 columns to the left, wrapped around, and the screen then took the next command as the missing
pixels, so every update after it landed wrong (the owner's Turing 3.5", 22-10-2026). Port.write therefore waits until
each write has gone out (tcdrain), and draw() writes the command and the pixels apart."""

from __future__ import annotations

import os
import select
import time
from dataclasses import dataclass
from pathlib import Path

VENDOR, PRODUCT = "1a86", "5722"

RESET, CLEAR, SCREEN_OFF, SCREEN_ON, SET_BRIGHTNESS, SET_ORIENTATION, DISPLAY_BITMAP, HELLO = (
    101, 102, 108, 109, 110, 121, 197, 69)
PORTRAIT = 0                                    # the screen's own orientation; the app turns its picture itself
HELLO_TIMEOUT_S = 1.0


@dataclass(frozen=True)
class Model:
    name: str
    short: str                                  # for the window's header
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
    """A screen on USB: its port and what it says about itself."""
    port: Path                                  # /dev/ttyACM<n>
    product: str
    serial: str

    @property
    def usable(self) -> bool:
        """Can this user open the port: the udev rule (or the dialout group) gives access."""
        return os.access(self.port, os.R_OK | os.W_OK)


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except (OSError, ValueError):
        return ""


def find(sys_root: Path | str = "/sys", dev: Path | str = "/dev") -> list[Found]:
    """The screens plugged in, by USB ID: each tty's device is a USB interface, its parent folder the USB device."""
    found = []
    for tty in sorted(Path(sys_root, "class/tty").glob("ttyACM*")):
        usb = (tty / "device").resolve().parent
        if _read(usb / "idVendor") == VENDOR and _read(usb / "idProduct") == PRODUCT:
            found.append(Found(Path(dev, tty.name), _read(usb / "product"), _read(usb / "serial")))
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


class Port:
    """The screen's serial port, raw. A write returns once it has gone out to the screen, so the next write starts a
    new USB transfer (see above); an unplugged screen raises OSError."""

    def __init__(self, path: Path | str):
        import termios                          # Linux only; the rest of this module imports on Windows too
        self._drain = termios.tcdrain
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
        try:
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = attrs[1] = attrs[3] = 0          # raw: no input or output processing, no echo
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL | termios.CRTSCTS
            attrs[4] = attrs[5] = termios.B115200       # CDC-ACM ignores the speed; set as the Windows app does
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            termios.tcflush(self.fd, termios.TCIOFLUSH)
        except OSError:
            os.close(self.fd)
            raise

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(self.fd, view):]
        self._drain(self.fd)

    def read(self, size: int, timeout: float) -> bytes:
        data = b""
        end = time.monotonic() + timeout
        while len(data) < size and (left := end - time.monotonic()) > 0:
            if select.select([self.fd], [], [], left)[0]:
                chunk = os.read(self.fd, size - len(data))
                if not chunk:
                    break
                data += chunk
        return data

    def close(self) -> None:
        try:
            os.close(self.fd)
        except OSError:
            pass


class Screen:
    """The commands, on a Port (or anything with write and read whose every write is a transfer of its own)."""

    def __init__(self, port):
        self.port = port
        self.model = TURING_35

    def reset(self) -> None:
        """Restarts the screen, also from a picture cut off halfway. The port is gone afterwards: the write usually
        ends with OSError as the screen leaves USB."""
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

