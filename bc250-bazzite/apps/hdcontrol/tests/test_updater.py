# SPDX-License-Identifier: GPL-3.0-or-later
"""The update protocol against a simulated controller: what is sent, in which pieces, and how each answer is
taken."""

from __future__ import annotations

import re

import pytest

from usb_hdcontrol import updater


class Controller:
    """Answers report 0xF5 with the status of the last command; *script* gives a list of codes per command (the last
    one repeats), so a test can make it busy, ask again or fail."""

    def __init__(self, script: dict[int, list[int]] | None = None, fail_finalize: bool = False):
        self.script = {updater.START: [0x00], updater.WRITE: [0x03], updater.VERIFY: [0x00], **(script or {})}
        self.queue: list[int] = []
        self.command = -1
        self.sent: list[bytes] = []
        self.fail_finalize = fail_finalize

    def set_feature(self, data: bytes) -> None:
        if data[1] == updater.FINALIZE and self.fail_finalize:
            raise OSError(19, "No such device")
        assert data[0] == updater.REPORT_COMMAND and len(data) == 3 + data[2] <= 60
        self.sent.append(bytes(data))
        if data[1] != self.command or data[1] == updater.WRITE:
            self.command = data[1]
            self.queue = list(self.script.get(data[1], [0x00]))

    def get_feature(self, report_id: int) -> bytes:
        assert report_id == updater.REPORT_STATUS
        code = self.queue.pop(0) if len(self.queue) > 1 else self.queue[0]
        return bytes([updater.REPORT_STATUS, self.command, code, 0])


def image(size: int = 0x8000 + 1000) -> bytes:
    return bytes(i % 251 for i in range(size))


def run(device, data=None, clock=None):
    progress = updater.Progress()
    updater.update(device, data if data is not None else image(), progress, sleep=lambda _s: None,
                   clock=clock or (lambda: 0.0))
    return progress


def test_sends_header_image_verify_and_finalize_in_57_byte_pieces():
    device = Controller()
    data = image()
    progress = run(device, data)
    commands = [report[1] for report in device.sent]
    starts = [report for report in device.sent if report[1] == updater.START]
    writes = [report for report in device.sent if report[1] == updater.WRITE]
    assert b"".join(report[3:] for report in starts) == data[:256]
    assert [len(report) - 3 for report in starts] == [57, 57, 57, 57, 28]
    assert b"".join(report[3:] for report in writes) == data            # the whole image, header included
    # 32 KiB blocks: the last piece of the first block is short, the next block starts on its own piece
    assert len(writes) == -(-0x8000 // 57) + -(-1000 // 57)
    assert len(writes[574]) - 3 == 0x8000 - 574 * 57
    assert commands[-2:] == [updater.VERIFY, updater.FINALIZE]
    assert device.sent[-1] == bytes([updater.REPORT_COMMAND, updater.FINALIZE, 0])
    assert progress.done == progress.total == len(data) and progress.step == updater.FINALIZE


def test_waits_while_busy_and_asks_again():
    device = Controller({updater.START: [0x04, 0x04, 0x00], updater.WRITE: [0x01, 0x10, 0x03],
                         updater.VERIFY: [0x10, 0x10, 0x00]})
    assert run(device).log[-1].startswith("The controller switches")


def test_a_start_answered_with_retry_goes_on_as_dualsense_updater_rs_does():
    run(Controller({updater.START: [0x10]}))


@pytest.mark.parametrize("command, code, text", [
    (updater.START, 0x02, "not newer"),
    (updater.START, 0x01, "signature"),
    (updater.START, 0x05, "erase"),
    (updater.WRITE, 0x02, "could not write"),
    (updater.VERIFY, 0x04, "damaged or not an official image"),
    (updater.VERIFY, 0x77, "unknown error (0x77) while verifying"),
])
def test_stops_at_an_error_and_never_finalizes(command, code, text):
    device = Controller({command: [code]})
    with pytest.raises(updater.UpdateError, match=re.escape(text)) as error:
        run(device)
    assert "plug it in again" in str(error.value)
    assert all(report[1] != updater.FINALIZE for report in device.sent)


def test_stops_when_the_controller_stays_busy():
    device = Controller({updater.VERIFY: [0x10]})
    ticks = iter(range(0, 10000, 10))
    with pytest.raises(updater.UpdateError, match="stayed busy"):
        run(device, clock=lambda: float(next(ticks)))


def test_a_status_for_another_step_is_an_error():
    class Confused(Controller):
        def get_feature(self, report_id):
            return bytes([updater.REPORT_STATUS, updater.VERIFY, 0, 0])
    with pytest.raises(updater.UpdateError, match="step 2, not step 0"):
        run(Confused())


def test_a_controller_that_leaves_is_an_error():
    class Gone(Controller):
        def get_feature(self, report_id):
            raise OSError(19, "No such device")
    with pytest.raises(updater.UpdateError, match="stopped answering: No such device"):
        run(Gone())


def test_a_controller_that_restarts_at_finalize_is_fine():
    assert run(Controller(fail_finalize=True)).step == updater.FINALIZE


def test_refuses_an_image_shorter_than_its_header():
    with pytest.raises(updater.UpdateError):
        run(Controller(), image(100))
