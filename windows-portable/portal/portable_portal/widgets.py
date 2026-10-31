# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's own widgets on the portable window: the strip under the tiles (what the focused app is and does,
with its pills), the details page of an app, the Settings page (the portal's own version and update) and the ROG
Xbox Ally X's Operating Mode page. The tabs
(LB and RB step through the categories) are core's Tabs. Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from bc250_core.portable import (AMBER, BODY, DIM, PICTURE_RULES, TEXT, VEIL_MAX, VEIL_STEP, InfoPill, Pane, Row,
                                 Tabs, px, text_label)

from .operating_mode import BY_LETTER, MODES

WALLPAPER_FOLDER = r"%LOCALAPPDATA%\windows-portable-suite\wallpapers"   # as the user finds it
NAME = 24                               # pt: the name at the top of a pane


class AppPane(Pane):
    """The strip under the tiles: the focused app's name, its versions and one line of what it does. What A and Y
    do (Install or Open, Update) is in the window's legend, never a pill (owner, 29-10-2026: one way everywhere):
    main and other keep their texts for it."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column.setContentsMargins(px(24), px(14), px(24), px(14))
        row = QHBoxLayout()
        row.setSpacing(px(12))
        texts = QVBoxLayout()
        texts.setSpacing(px(2))
        self.name = text_label("", 22, QFont.Weight.ExtraBold)
        self.versions = text_label("", BODY + 1, color=DIM)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        for label in (self.name, self.versions, self.summary, self.status):
            texts.addWidget(label)
        row.addLayout(texts, 1)
        self.main = self.other = ""                     # A's and Y's text in the legend; "" for none
        self.column.addLayout(row)

    def fill(self, name: str, versions: str, summary: str, status: str, main: str, other: str) -> None:
        """The texts, and A's and Y's in the legend: "" for none (no Y without an update)."""
        self.name.setText(name)
        self.versions.setText(versions)
        self.summary.setText(summary)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.main, self.other = main, other


def _rows(grid: QGridLayout, rows: Sequence[tuple[str, str]]) -> None:
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()                           # gone now, not when Qt deletes it later
            widget.deleteLater()
    for r, (label, value) in enumerate(rows):
        grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
        shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
        grid.addWidget(shown, r, 1)
    grid.setColumnStretch(1, 1)


class DetailsPane(Pane):
    """An app's details page (X): its versions, where it is and what it does; A Open and Y Remove are in the
    window's legend (open, remove: their texts, "" for none)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.name = text_label("", NAME, QFont.Weight.ExtraBold)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.name)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.open = self.remove = ""                    # A's and Y's text in the legend; "" for none

    def fill(self, name: str, summary: str, rows: Sequence[tuple[str, str]], status: str, can_open: bool,
             can_remove: bool, remove_text: str = "Remove") -> None:
        self.name.setText(name)
        self.summary.setText(summary)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.open = "Open" if can_open else ""
        self.remove = remove_text if can_remove else ""


class SuitePane(Pane):
    """The Settings page (Menu): the portal's own version, the newest release on GitHub and what it changes, with Update
    (Y) when there is a newer one; and the suite's settings, a row each that A changes (owner, 28-10-2026: the
    wallpaper on or off; 29-10-2026: the sound on or off; 30-10-2026: which wallpaper, and its transparency). What
    each does is behind the information icon (Menu), not in lines under the rows (owner, 30-10-2026: no long lines
    of text where the space is not there). They had a page of their own on View until View became the suite's Exit
    app (owner, 29-10-2026)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        self.name = text_label("", NAME, QFont.Weight.ExtraBold)
        heading.addWidget(self.name)
        heading.addStretch()
        self.info = InfoPill("Settings", "")
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.version = text_label("", BODY + 1, color=DIM)
        self.column.addWidget(self.version)
        self.column.addSpacing(px(12))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.column.addSpacing(px(16))
        self.wallpaper = Row("Wallpaper: Built-in")
        self.transparency = Row("Transparency: 59 %")
        self.sound = Row("Sound: On")
        self.xbox = Row("Xbox menu: Add")
        self.mode = Row("Operating mode: Turbo")
        self.mode.hide()                                # on the ROG Xbox Ally X only
        for row in (self.wallpaper, self.transparency, self.sound, self.xbox, self.mode):
            self.column.addWidget(row)
            self.column.addSpacing(px(6))
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.action = ""                                # Y's text in the legend: Check again, Update to x.y.z
        self.refused: dict[str, str] = {}
        self._explain()

    def fill(self, name: str, version: str, rows: Sequence[tuple[str, str]], status: str, action: str) -> None:
        self.name.setText(name)
        self.version.setText(version)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.action = action

    def _explain(self) -> None:
        """The information icon's text: each setting, where your own wallpapers go and by which rules, the pictures in
        that folder that cannot be one with why, the Xbox menu only where the Xbox app is, and the buttons at the
        bottom (owner, 30-10-2026)."""
        parts = [
            "Wallpaper: a picture behind the tiles, in every app of the suite (each from its next start). The A button "
            "picks the next: Off (the plain dark background), Built-in (the suite's own picture), then each of your "
            "own pictures, by file name.",
            f"Your own pictures go in {WALLPAPER_FOLDER} (paste it in File Explorer's address bar): {PICTURE_RULES}. A "
            "picture is cropped to the screen, never stretched.",
        ]
        if self.refused:
            parts.append("Not used: " + "; ".join(f"{name} ({why})" for name, why in self.refused.items()) + ".")
        parts += [f"Transparency: how much of the dark background lies over the wallpaper, so the text stays easy to "
                  f"read. The A button adds {VEIL_STEP} %, up to {VEIL_MAX} %, then starts at 0 %.",
                  "Sound: the portal's intro sound, for the suite."]
        if self.xbox.isVisibleTo(self):
            parts.append("Xbox menu: the suite in the Xbox app's library, so Xbox mode starts it from its home. The A "
                         "button adds it, and on In the menu takes it out again; the Xbox app closes for a moment.")
        if self.mode.isVisibleTo(self):
            parts.append("Operating mode: the ROG Xbox Ally X's mode, as Armoury Crate's Command Center offers them. "
                         "The A button opens its page.")
        parts += ["Every setting is kept for the next start.",
                  "The buttons at the bottom: A changes the setting with the focus. Y looks for a newer portal on "
                  "GitHub (Check again), or downloads and installs it (Update to x.y.z). RT starts Steam's library in "
                  "Big Picture, Steam first when it does not run (where Steam is installed). Menu (☰) shows this. B "
                  "goes back to the tiles. View (⧉) exits the portal."]
        self.info.info = "\n\n".join(parts)

    def set_wallpaper(self, name: str, refused: dict[str, str] | None = None) -> None:
        """The Wallpaper row: *name* (Off, Built-in or a picture's); *refused*: the pictures in the folder that cannot be
        one, each with the rule it breaks, for the information."""
        self.wallpaper.set_text(f"Wallpaper: {name}")
        self.refused = dict(refused or {})
        self._explain()

    def set_transparency(self, percent: int) -> None:
        self.transparency.set_text(f"Transparency: {percent} %")

    def set_sound(self, on: bool) -> None:
        self.sound.set_text(f"Sound: {'On' if on else 'Off'}")

    def set_xbox(self, state: str) -> None:
        """The Xbox menu row: "" without the Xbox app (hidden), else what it says after "Xbox menu: "."""
        self.xbox.setVisible(bool(state))
        if state:
            self.xbox.set_text(f"Xbox menu: {state}")
        self._explain()

    def set_mode(self, name: str) -> None:
        """The Operating mode row: "" off the ROG Xbox Ally X (hidden), else the active mode's name."""
        self.mode.setVisible(bool(name))
        if name:
            self.mode.set_text(f"Operating mode: {name}")
        self._explain()


class ModePane(Pane):
    """The ROG Xbox Ally X's Operating Mode page (owner, 31-10-2026): Silent, Performance, Turbo and Windows, a row each
    with its watts for the power source the device is on now; A sets the mode with the focus. Under them the Watt
    limits row installs or removes the helper that writes the watts. Shown only on the Ally X, from the Settings
    page's Operating mode row."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Operating Mode", NAME, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("Operating Mode", "")
        heading.addWidget(self.info, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(heading)
        self.source = text_label("", BODY + 1, color=DIM)
        self.column.addWidget(self.source)
        self.column.addSpacing(px(16))
        self.rows: dict[str, Row] = {}
        for mode in MODES:
            row = Row(mode.name)
            self.rows[mode.letter] = row
            self.column.addWidget(row)
            self.column.addSpacing(px(6))
        self.column.addSpacing(px(10))
        self.helper = Row("Watt limits: Install")
        self.column.addWidget(self.helper)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.info.info = "\n\n".join([
            "The ROG Xbox Ally X's operating modes, as Armoury Crate's Command Center offers them. Each row shows the "
            "mode's watt limits on the power source the device is on now: sustained, slow and fast. Armoury Crate "
            "keeps one set for the charger and one for the battery.",
            "Silent: the least power, the coolest and the quietest. Performance: the middle. Turbo: the most power; on "
            "battery it drains the battery fastest, and in a game that already reaches its frame cap it buys nothing. "
            "Windows: back to Windows' own Balanced power plan, with Windows' power mode left as you chose it.",
            "The A button sets the mode with the focus: its power plan and Windows' power mode, at once, and its watt "
            "limits through the helper. The letter in the header, before the battery (S, P, T or W), is read from the "
            "plan and the power mode.",
            "Watt limits: only an administrator may write the watts, so a small helper does, installed once with "
            "Windows' administrator prompt (the A button on Install). It also sets the mode picked here again a few "
            "seconds after the charger is plugged in or out, after Armoury Crate has set its own, and after a "
            "restart, once you sign in. The A button on "
            "Installed removes it, with the same prompt; uninstalling the suite removes it too. Without it, a mode "
            "set here leaves the watts as Armoury Crate set them.",
            "Command Center keeps its own record of the mode, so it may show another mode after a change here.",
            "The buttons at the bottom: A sets the mode with the focus, or installs or removes the helper. Menu (☰) shows this. B goes back to Settings. "
            "View (⧉) exits the portal."])

    def fill(self, source: str, rows: Sequence[tuple[str, str, bool]], status: str, helper: str = "") -> None:
        """*source*: the power source line; *rows*: (letter, watts, active) per mode; *status*: the last outcome;
        *helper*: the Watt limits row's state (Install, Installed), "" to hide it."""
        self.helper.setVisible(bool(helper))
        if helper:
            self.helper.set_text(f"Watt limits: {helper}")
        self.source.setText(source)
        for letter, watts, active in rows:
            self.rows[letter].set_text(f"{BY_LETTER[letter].name}: {watts}" + ("  (active)" if active else ""))
        self.status.setText(status)
        self.status.setVisible(bool(status))


__all__ = ["AppPane", "DetailsPane", "ModePane", "SuitePane", "Tabs", "TEXT"]
