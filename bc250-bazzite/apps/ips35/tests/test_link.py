# SPDX-License-Identifier: GPL-3.0-or-later
"""The link thread against a fake screen: reset first, then connect; no screen; no access; only changes sent; and a
screen that is unplugged and comes back."""

from __future__ import annotations

from pathlib import Path

import pytest

from usb_ips35 import link as link_module, screen
from usb_ips35.link import Link
from conftest import FakePort, wait_until

FOUND = screen.Found(Path("/dev/ttyACM0"), "UsbMonitor", "USB35INCHIPSV2")
W, H = screen.TURING_35.width, screen.TURING_35.height


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    monkeypatch.setattr(link_module, "RETRY_S", 0.01)
    monkeypatch.setattr(link_module, "RESET_WAIT_S", 0.01)


class Usable(screen.Found):
    @property
    def usable(self) -> bool:
        return True


class Ports:
    """Hands out FakePorts: the first one is the reset, which ends as the screen leaves USB."""

    def __init__(self, *ports: FakePort):
        self.ports = list(ports)
        self.opened: list[FakePort] = []

    def __call__(self, path):
        port = self.ports.pop(0) if self.ports else FakePort()
        self.opened.append(port)
        return port


def start(ports: Ports, find=lambda: [Usable(*vars(FOUND).values())]) -> tuple[Link, list]:
    states = []
    link = Link(find=find, open_port=ports)
    link.state_changed.connect(states.append)
    link.start()
    return link, states


def kinds(states) -> list[str]:
    return [s.kind for s in states]


def test_resets_then_connects_and_sends_only_changes(qapp):
    ports = Ports(FakePort(fail_after=0), FakePort())
    link, states = start(ports)
    try:
        assert wait_until(qapp, lambda: "connected" in kinds(states))
        assert kinds(states)[:2] == ["resetting", "connected"]
        assert states[-1].model == screen.TURING_35
        port = ports.opened[1]
        frame = bytes(W * H * 2)
        link.show(frame, W, H)
        assert wait_until(qapp, lambda: screen.bitmap_command(0, 0, W, H) in port.data)
        changed = bytearray(frame)
        changed[(10 * W + 5) * 2:(10 * W + 5) * 2 + 2] = b"\xff\xff"
        link.show(bytes(changed), W, H)
        assert wait_until(qapp, lambda: screen.bitmap_command(5, 10, 1, 1) in port.data)
        link.set_brightness(100)
        assert wait_until(qapp, lambda: screen.brightness_command(100) in port.writes)
    finally:
        link.stop()
    assert port.writes[-1] == screen.command(screen.SCREEN_OFF)       # dark when the app quits
    assert all(p.closed for p in ports.opened)


def test_stop_without_switching_off(qapp):
    ports = Ports(FakePort(fail_after=0), FakePort())
    link, states = start(ports)
    assert wait_until(qapp, lambda: "connected" in kinds(states))
    link.stop(screen_off=False)
    assert screen.command(screen.SCREEN_OFF) not in ports.opened[1].writes


def test_no_screen(qapp):
    link, states = start(Ports(), find=lambda: [])
    try:
        assert wait_until(qapp, lambda: kinds(states)[-1:] == ["searching"])
    finally:
        link.stop()


def test_no_access(qapp, tmp_path):
    found = screen.Found(tmp_path / "ttyACM0", "UsbMonitor", "")     # a port this user cannot open
    ports = Ports()
    link, states = start(ports, find=lambda: [found])
    try:
        assert wait_until(qapp, lambda: "no-access" in kinds(states))
        assert states[-1].found == found and not ports.opened
    finally:
        link.stop()


def test_unplugged_screen_is_reset_and_drawn_again(qapp):
    # Connected, then the screen goes after a few writes; it comes back, is reset again and gets the whole frame.
    ports = Ports(FakePort(fail_after=0), FakePort(fail_after=4), FakePort(fail_after=0), FakePort())
    link, states = start(ports)
    try:
        link.show(bytes(W * H * 2), W, H)
        assert wait_until(qapp, lambda: "error" in kinds(states))
        assert wait_until(qapp, lambda: kinds(states).count("connected") == 2)
        assert kinds(states).count("resetting") == 2
        link.show(bytes(W * H * 2), W, H)
        assert wait_until(qapp, lambda: screen.bitmap_command(0, 0, W, H) in ports.opened[3].data)
    finally:
        link.stop()
