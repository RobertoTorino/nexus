# SPDX-License-Identifier: GPL-3.0-or-later
"""R3's on-screen keyboard (owner, 05-11-2026): KWin's virtual keyboard on the session bus, with the bus faked."""

from __future__ import annotations

import pytest

from bc250_portal import keyboard


class FakeKWin:
    """KWin's org.kde.kwin.VirtualKeyboard: its properties, forceActivate() (it shows only in mode 2, as on the
    owner's board with a controller) and Set."""

    def __init__(self, available=True, mode=1, error=""):
        self.properties = {"available": available, "visible": False, "active": False, "mode": mode}
        self.error, self.calls = error, []

    def __call__(self, interface, method, arguments):
        self.calls.append((interface, method, [a.variant() if hasattr(a, "variant") else a for a in arguments]))
        if self.error:
            raise keyboard.KeyboardError(self.error)
        if method == "Get":
            return [self.properties[arguments[1]]]
        if method == "forceActivate":
            self.properties["active"] = True
            self.properties["visible"] = self.properties["mode"] == keyboard.ANY_INPUT
        elif method == "Set":
            name, value = arguments[1], self.calls[-1][2][2]
            self.properties[name] = value
            if name == "active" and not value:
                self.properties["visible"] = False
        return []


def test_r3_shows_the_keyboard_for_any_input_and_hides_it_with_the_users_mode_back():
    kwin = FakeKWin(mode=1)
    board = keyboard.OnScreenKeyboard(kwin)
    assert board.toggle() is True
    assert kwin.properties["visible"] and kwin.properties["mode"] == keyboard.ANY_INPUT and board.user_mode == 1
    assert board.toggle() is False
    assert not kwin.properties["visible"] and kwin.properties["mode"] == 1 and board.user_mode is None


def test_a_keyboard_closed_some_other_way_and_the_portal_closing():
    kwin = FakeKWin(mode=1)
    board = keyboard.OnScreenKeyboard(kwin)
    board.toggle()
    kwin.properties["visible"] = False                          # closed with its own button
    assert board.toggle() is True and board.user_mode == 1      # shown again; the user's mode still kept
    board.restore()                                             # the portal closes
    assert kwin.properties["mode"] == 1
    calls = len(kwin.calls)
    board.restore()
    assert len(kwin.calls) == calls                             # nothing changed: nothing to put back


def test_a_desktop_set_to_any_input_is_left_alone():
    kwin = FakeKWin(mode=keyboard.ANY_INPUT)
    board = keyboard.OnScreenKeyboard(kwin)
    assert board.toggle() is True and board.user_mode is None
    assert not any(c[1] == "Set" and c[2][1] == "mode" for c in kwin.calls)


def test_no_keyboard_chosen_or_no_kwin_says_what_to_do():
    kwin = FakeKWin(available=False)
    with pytest.raises(keyboard.KeyboardError, match="System Settings, Keyboard, Virtual Keyboard"):
        keyboard.OnScreenKeyboard(kwin).toggle()
    assert not any(method in ("forceActivate", "Set") for _, method, _ in kwin.calls)
    with pytest.raises(keyboard.KeyboardError, match="no such service"):
        keyboard.OnScreenKeyboard(FakeKWin(error="no such service")).toggle()
