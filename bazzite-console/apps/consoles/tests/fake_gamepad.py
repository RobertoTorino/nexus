# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stand-in for gamepad.Sdl: controllers whose readings the test sets, which can come and go."""

from __future__ import annotations

import threading
from dataclasses import replace

from consoles_link.gamepad import GamepadError, PadInfo, Reading, Sample


class FakePad:
    def __init__(self, name: str, reading: Reading | None = None):
        self.name = name
        self.reading = reading or Reading()
        self.connected = True
        self.closed = False
        self.info: PadInfo | None = None
        self.battery = ("on battery", 80)


class FakeSdl:
    """pads: id -> FakePad, changed by the test while the reader runs. init_error makes init() fail."""

    def __init__(self, pads: dict[int, FakePad] | None = None, init_error: str | None = None):
        self.pads = pads if pads is not None else {}
        self.init_error = init_error
        self.lock = threading.Lock()
        self.updates = 0
        self.quit_called = False
        self.samples: list[Sample] = []           # sensor samples for the next update()
        self.outputs: list[tuple] = []            # (call, pad name, values) for rumble, led and player
        self.rumble_error: str | None = None       # SDL's reason for not sending a rumble

    def __call__(self) -> FakeSdl:                  # used as the reader's backend factory
        return self

    def init(self) -> None:
        if self.init_error:
            raise GamepadError(self.init_error)

    def quit(self) -> None:
        self.quit_called = True

    def update(self) -> list[Sample]:
        self.updates += 1
        with self.lock:
            samples, self.samples = self.samples, []
        return samples

    def gamepad_ids(self) -> list[int]:
        with self.lock:
            return [pad_id for pad_id, pad in self.pads.items() if pad.connected]

    def open(self, pad_id: int):
        return self.pads.get(pad_id)

    def close(self, pad: FakePad) -> None:
        pad.closed = True

    def connected(self, pad: FakePad) -> bool:
        return pad.connected

    def name(self, pad: FakePad) -> str:
        return pad.name

    def rumble(self, pad: FakePad, low: int, high: int, milliseconds: int) -> str | None:
        self.outputs.append(("rumble", pad.name, (low, high, milliseconds)))
        return self.rumble_error

    def led(self, pad: FakePad, rgb: tuple[int, int, int]) -> None:
        self.outputs.append(("led", pad.name, rgb))

    def player(self, pad: FakePad, index: int) -> None:
        self.outputs.append(("player", pad.name, index))

    def info(self, pad: FakePad) -> PadInfo:
        return pad.info or PadInfo(pad.name)

    def battery(self, pad: FakePad) -> tuple[str, int]:
        return pad.battery

    def read(self, pad: FakePad) -> Reading:
        with self.lock:
            return replace(pad.reading)


class FakeTracker:
    """A stand-in for the native core's OrientationTracker: keeps the last values, the orientation counts samples."""

    def __init__(self):
        self.gyro, self.accel, self.updates = (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), []

    def update(self, gyro, accel, timestamp_us, accel_zero=(0.0, 0.0, 0.0), accel_zero_applied=False):
        self.gyro, self.accel = tuple(gyro), tuple(accel)
        if not accel_zero_applied:
            self.accel = tuple(a - z for a, z in zip(self.accel, accel_zero))
        self.updates.append((self.gyro, self.accel, timestamp_us, accel_zero_applied))

    @property
    def orientation(self):
        return (0.0, 0.0, float(len(self.updates)), 1.0)
