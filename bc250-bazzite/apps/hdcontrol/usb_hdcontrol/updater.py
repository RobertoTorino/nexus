# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from dualsense-updater-rs (src/update.rs, src/hid.rs and src/protocol.rs), MIT, Copyright 2026 nchie; the
# MIT notice is in the README's License section.
"""The firmware update, over USB, as Sony's Windows app does it: feature report 0xF4 carries a command and up to 57
bytes, report 0xF5 answers with the command's status, polled until the controller is done.

1. Start: the image's 256-byte header. The controller checks it (its CMAC, the version) and erases the flash.
2. Write: the whole image, header included, in blocks of 32 KiB, each sent in 57-byte pieces.
3. Verify: the controller checks the image it received.
4. Finalize: the controller switches to the new firmware and restarts; it leaves USB and comes back.

What dualsense-updater-rs found on a DualSense: an update commits even when verify and finalize are never sent, and an
image for another controller fails the check. So the app checks the image before step 1, and never stops halfway."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from .hidraw import Device

REPORT_COMMAND = 0xF4
REPORT_STATUS = 0xF5
START, WRITE, VERIFY, FINALIZE = 0, 1, 2, 3
STEP_NAMES = {START: "Starting", WRITE: "Writing", VERIFY: "Verifying", FINALIZE: "Finishing"}
PIECE = 0x39
BLOCK = 0x8000
HEADER = 256
POLL_S = 0.01
TIMEOUT_S = 60.0                    # one status: the start erases the flash first

# Status codes, per command. 0x04 at the start and 0x10 at verify mean "still busy"; 0x01 and 0x10 while writing
# "ask again"; 0x03 while writing "send the next piece". dualsense-updater-rs goes on after a start that answers 0x10
# ("retry") as after 0x00, and so does the app.
START_BUSY = {0x04}
START_OK = {0x00, 0x10}
START_ERRORS = {0x01: "The controller refused the image's header: its signature does not match.",
                0x02: "The controller refused the image: it is not newer than the firmware it runs.",
                0x03: "The controller refused the image's header: it is not meant for this controller.",
                0x05: "The controller could not erase its flash for the update.",
                0x06: "The controller did not receive the image's header.",
                0x11: "The controller refused the image's header: its parameters are wrong."}
WRITE_BUSY = {0x01, 0x10}
WRITE_NEXT = {0x00, 0x03}
WRITE_ERRORS = {0x02: "The controller could not write the image to its flash.",
                0x04: "The controller had not started the update.",
                0x11: "The controller refused a piece of the image: its parameters are wrong."}
VERIFY_BUSY = {0x10}
VERIFY_ERRORS = {0x01: "The image's header failed the controller's check.",
                 0x02: "The image is not newer than the firmware the controller runs.",
                 0x03: "The image is not meant for this controller.",
                 0x04: "The image failed the controller's check: it is damaged or not an official image.",
                 0x11: "The image's parameters are wrong."}
AFTER_ERROR = (" Unplug the controller and plug it in again: the window then shows which firmware it runs, and the "
               "update can be tried again.")


class UpdateError(Exception):
    pass


@dataclass
class Progress:
    """Read by the window while the update runs in its thread: plain values, written in order."""
    step: int = START
    done: int = 0                   # bytes of the image sent
    total: int = 0
    log: list[str] = field(default_factory=list)

    def note(self, text: str) -> None:
        self.log.append(text)


def _send(device: Device, command: int, data: bytes = b"") -> None:
    device.set_feature(bytes([REPORT_COMMAND, command, len(data)]) + data)


def _status(device: Device, command: int, busy: set[int], sleep: Callable[[float], None],
            clock: Callable[[], float]) -> int:
    deadline = clock() + TIMEOUT_S
    while True:
        answer = device.get_feature(REPORT_STATUS)
        if len(answer) < 3 or answer[0] != REPORT_STATUS:
            raise UpdateError(f"The controller's status report is malformed ({answer.hex()}).")
        if answer[1] != command:
            raise UpdateError(f"The controller answered for step {answer[1]}, not step {command}.")
        if answer[2] not in busy:
            return answer[2]
        if clock() > deadline:
            raise UpdateError(f"The controller stayed busy for {TIMEOUT_S:.0f} s in step {STEP_NAMES[command]}.")
        sleep(POLL_S)


def _failed(code: int, errors: dict[int, str], step: str) -> UpdateError:
    text = errors.get(code, f"The controller reported an unknown error (0x{code:02x}) while {step}.")
    return UpdateError(text + AFTER_ERROR)


def update(device: Device, image: bytes, progress: Progress | None = None,
           sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic) -> None:
    """Sends *image* to the controller; raises UpdateError with what the controller said. Returns once the
    controller was told to finalize; it then restarts by itself."""
    progress = progress or Progress()
    progress.total = len(image)
    if len(image) < HEADER:
        raise UpdateError("The image is shorter than its header.")
    try:
        progress.step = START
        # The header goes in pieces of 57 bytes too: the command report has room for no more.
        for offset in range(0, HEADER, PIECE):
            _send(device, START, image[offset:min(offset + PIECE, HEADER)])
        code = _status(device, START, START_BUSY, sleep, clock)
        if code not in START_OK:
            raise _failed(code, START_ERRORS, "starting")
        progress.note("The controller took the header.")

        progress.step = WRITE
        for block in range(0, len(image), BLOCK):
            chunk = image[block:block + BLOCK]
            for offset in range(0, len(chunk), PIECE):
                _send(device, WRITE, chunk[offset:offset + PIECE])
                code = _status(device, WRITE, WRITE_BUSY, sleep, clock)
                if code not in WRITE_NEXT:
                    raise _failed(code, WRITE_ERRORS, "writing")
                progress.done = block + min(offset + PIECE, len(chunk))
        progress.note("The controller received the image.")

        progress.step = VERIFY
        _send(device, VERIFY)
        code = _status(device, VERIFY, VERIFY_BUSY, sleep, clock)
        if code != 0x00:
            raise _failed(code, VERIFY_ERRORS, "verifying")
        progress.note("The controller verified the image.")
    except OSError as exc:
        raise UpdateError(f"The controller stopped answering: {exc.strerror or exc}. Leave it plugged in; if it "
                          "does not come back, unplug it and plug it in again.") from exc

    progress.step = FINALIZE
    try:
        _send(device, FINALIZE)
    except OSError:
        pass                        # the controller may restart before it acknowledges
    progress.note("The controller switches to the new firmware and restarts.")
