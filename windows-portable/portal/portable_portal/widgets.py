# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's own widgets on the portable window: the strip under the tiles (what the focused app is and does,
with its pills), the details page of an app, the Settings page (the portal's own version and update) and the ROG
XBOX Ally X's Performance Mode page (the Operating Mode page until 05-11-2026). The tabs
(LB and RB step through the categories) are core's Tabs. Direction D's portal screen (the owner's, 26-10-2026)."""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from bc250_core.portable import (AMBER, BODY, DIM, LEGEND, ON_AMBER, PICTURE_RULES, RADIUS, RAISED, TEXT, VEIL_MAX,
                                 VEIL_STEP, InfoPill, Pane, Row, Tabs, font, px, text_label)

from .operating_mode import BY_LETTER, MODES
from .weather import MATCHES, Place

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


class UpdateBanner(QLabel):
    """The banner on the tabs' line while a newer portal is out (owner, 01-11-2026: the update was hidden on the
    Settings page): amber with dark capitals, gone once there is no update. A tap does what Y does."""

    pressed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFont(font(BODY, QFont.Weight.ExtraBold))
        self.setStyleSheet(f"color: {ON_AMBER}; background: {AMBER}; border-radius: {px(RADIUS)}px;"
                           f" padding: {px(6)}px {px(16)}px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit()
        super().mousePressEvent(event)


class PageMarker(QLabel):
    """Under the tiles while a tab has more apps than one page holds: which page shows, "Page 1 of 2". The d-pad
    turns the page past the tiles' left or right edge; a tap turns to the next page, from the last to the first."""

    pressed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFont(font(LEGEND, QFont.Weight.DemiBold))
        self.setStyleSheet(f"color: {DIM}; background: transparent;")
        self.hide()

    def set_page(self, page: int, pages: int) -> None:
        self.setText(f"Page {page + 1} of {pages}")
        self.setVisible(pages > 1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self.pressed.emit()
        super().mousePressEvent(event)


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
    (Y) when there is a newer one (the app by app list behind the information icon: owner, 01-11-2026, eight apps'
    lines ran over each other); and the suite's settings, a row each that A changes (owner, 28-10-2026: the
    wallpaper on or off; 29-10-2026: the sound on or off; 30-10-2026: which wallpaper, and its transparency). What
    each does is behind the information icon (Menu), not in lines under the rows (owner, 30-10-2026: no long lines
    of text where the space is not there). They had a page of their own on View until View became the suite's Exit
    app (owner, 29-10-2026). Two columns under a heading each (owner, 06-11-2026: ten rows lay too close, the focused
    one's edge was cut off): the d-pad moves up and down a column, left and right between them."""

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
        self.xbox = Row("XBOX menu: Add")
        self.mode = Row("Performance mode: Turbo")
        self.mode.hide()                                # on the ROG XBOX Ally X only
        self.screen_row = Row("Screen: Display 1")
        self.screen_row.hide()                          # with a second screen attached
        # Windows' display setup for XBOX mode, which runs on the main screen only (owner, 05-11-2026): always shown,
        # as with the TV alone Windows sees one screen, and the way back has to stay at hand
        self.tv = Row("Play on the TV")
        self.handheld = Row("Play on the handheld")
        self.both = Row("Play on both screens")
        self.xbox_mode = Row("XBOX mode ↔ Desktop")       # Win + F11 (owner, 05-11-2026)
        # The clock and the weather at the top (owner, 06-11-2026)
        self.hours = Row("Clock: 24 hours")
        self.seconds = Row("Seconds: Off")
        self.zone = Row("Time zone: CET")
        self.place = Row("Location: Off")
        columns = QHBoxLayout()
        columns.setSpacing(px(20))
        for heading, rows in (("Look and clock", (self.wallpaper, self.transparency, self.sound, self.hours,
                                                  self.seconds, self.zone, self.place)),
                              ("Screens and device", (self.xbox, self.mode, self.screen_row, self.tv, self.handheld,
                                                      self.both, self.xbox_mode))):
            column = QVBoxLayout()
            column.setSpacing(px(8))
            column.addWidget(text_label(heading, BODY + 1, QFont.Weight.Bold, DIM))
            for row in rows:
                column.addWidget(row)
            column.addStretch()
            columns.addLayout(column, 1)
        self.column.addLayout(columns, 1)
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.action = ""                                # Y's text in the legend: Check again, Update to x.y.z
        self.refused: dict[str, str] = {}
        self.brings = ""                                # what a newer portal changes, app by app, for the information
        self._explain()

    def fill(self, name: str, version: str, rows: Sequence[tuple[str, str]], status: str, action: str,
             brings: str = "") -> None:
        """*brings*: a newer portal's changes, one line per app, in the information (Menu), "" for none."""
        self.name.setText(name)
        self.version.setText(version)
        _rows(self.grid, rows)
        self.status.setText(status)
        self.status.setVisible(bool(status))
        self.action = action
        if brings != self.brings:
            self.brings = brings
            self._explain()

    def _explain(self) -> None:
        """The information icon's text: each setting, where your own wallpapers go and by which rules, the pictures in
        that folder that cannot be one with why, the XBOX menu only where the XBOX app is, and the buttons at the
        bottom (owner, 30-10-2026)."""
        parts = [f"The update brings:\n{self.brings}"] if self.brings else []
        parts += [
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
                  "Sound: the portal's intro sound and a short one on each controller button, for the suite.",
                  "Clock: the time at the top in 24 hours (17:04) or 12 hours (5:04 PM). Seconds: with or without them. "
                  "Time zone: CET is Amsterdam time (CEST in summer), or UTC; its name follows the time. The A button "
                  "switches each.",
                  "Location: a place, whose weather shows at the top before the date: its symbol and the temperature, "
                  "looked up again every 15 minutes. The A button opens its page: type part of the name (R3 opens "
                  "Windows' touch keyboard) and A searches; the d-pad picks a place and A takes it, or Off for none. "
                  "Weather data by Open-Meteo.com."]
        if self.xbox.isVisibleTo(self):
            parts.append("XBOX menu: the suite in the XBOX app's library, so XBOX mode starts it from its home. The A "
                         "button adds it, and on In the menu takes it out again; the XBOX app closes for a moment.")
        if self.mode.isVisibleTo(self):
            parts.append("Performance mode: the ROG XBOX Ally X's mode, as Armoury Crate's Command Center offers them. "
                         "The A button opens its page.")
        if self.screen_row.isVisibleTo(self):
            parts.append("Screen: the screen the portal is on, with a second screen attached (a TV or a monitor). The A "
                         "button, or LT on any page, moves it to the next screen: the portal starts again there, sized "
                         "for it, after a download or an install has finished. The suite's apps open on that screen "
                         "from then on, while it is attached. Win + Shift + the left or right arrow key, shown at the "
                         "bottom left, moves a window of the suite as well.")
        parts.append("Play on the TV: Windows shows its picture on the second screen only (a TV or a monitor), so XBOX "
                     "mode, the portal, the games and the sound are all there; the handheld's screen goes dark. XBOX "
                     "mode runs on the main screen only, and with both screens on, the TV stays empty. Play on the "
                     "handheld: the handheld's screen only again, and its speakers. Play on both screens: the same "
                     "picture on both, XBOX mode too. Each changes Windows' display setting for everything on the "
                     "handheld, as Win + P does, and the portal then starts again, sized for the screen.")
        parts.append("XBOX mode ↔ Desktop: Windows' switch between XBOX mode and the desktop (Win + F11), either way. "
                     "Coming back to XBOX mode after the desktop, Windows may ask whether to restart for better "
                     "performance: its own question, answered with the controller.")
        parts += ["Every setting is kept for the next start.",
                  "The buttons at the bottom: A changes the setting with the focus. Y looks for a newer portal on "
                  "GitHub (Check again), or downloads and installs it (Update to x.y.z). RT starts Steam's library in "
                  "Big Picture, Steam first when it does not run (where Steam is installed). R3 (the right stick "
                  "pressed) shows Windows' touch keyboard, or hides it. Menu (☰) shows this. B "
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
        """The XBOX menu row: "" without the XBOX app (hidden), else what it says after "XBOX menu: "."""
        self.xbox.setVisible(bool(state))
        if state:
            self.xbox.set_text(f"XBOX menu: {state}")
        self._explain()

    def set_screen(self, name: str) -> None:
        """The Screen row: "" with one screen (hidden), else the name of the screen the portal is on."""
        self.screen_row.setVisible(bool(name))
        if name:
            self.screen_row.set_text(f"Screen: {name}")
        self._explain()

    def set_clock(self, twelve_hour: bool, seconds: bool, zone: str) -> None:
        self.hours.set_text(f"Clock: {'12 hours' if twelve_hour else '24 hours'}")
        self.seconds.set_text(f"Seconds: {'On' if seconds else 'Off'}")
        self.zone.set_text(f"Time zone: {zone}")

    def set_place(self, name: str) -> None:
        """The Location row: the place's name, "" for Off."""
        self.place.set_text(f"Location: {name or 'Off'}")

    def set_mode(self, name: str) -> None:
        """The Operating mode row: "" off the ROG XBOX Ally X (hidden), else the active mode's name."""
        self.mode.setVisible(bool(name))
        if name:
            self.mode.set_text(f"Performance mode: {name}")
        self._explain()


class PlacePane(Pane):
    """The Location page (owner, 06-11-2026): a field for part of a place's name, A searches Open-Meteo's places, and
    the matches as rows under it, A takes the one with the focus; Off takes none (no weather). R3 opens Windows'
    touch keyboard for the field, Y goes back to it from the rows, B back to Settings."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.column.addWidget(text_label("Location", NAME, QFont.Weight.ExtraBold))
        self.column.addSpacing(px(6))
        self.column.addWidget(text_label("Part of the place's name, then A to search; Y goes to the list, with Off "
                                         "for no weather. Weather data by Open-Meteo.com.", BODY + 1, color=DIM,
                                         wrap=True))
        self.column.addSpacing(px(12))
        self.field = QLineEdit()
        self.field.setFont(font(BODY + 2))
        self.field.setMinimumHeight(px(44))
        self.field.setPlaceholderText("Amsterdam")
        self.field.setStyleSheet(f"QLineEdit {{ color: {TEXT}; background: {RAISED}; border: none; "
                                 f"border-radius: {px(10)}px; padding: 0 {px(12)}px; }}")
        self.column.addWidget(self.field)
        self.column.addSpacing(px(10))
        self.rows: list[Row] = []
        listed = QVBoxLayout()
        listed.setSpacing(px(8))                        # apart, so the focused row's edge shows whole
        for _ in range(MATCHES):
            row = Row("")
            row.hide()
            self.rows.append(row)
            listed.addWidget(row)
        self.off = Row("Off: no weather")
        listed.addWidget(self.off)
        self.column.addLayout(listed)
        self.column.addStretch()
        self.status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
        self.column.addWidget(self.status)
        self.places: list[Place] = []

    def show_places(self, places: Sequence[Place]) -> None:
        """The matches as rows, the first *MATCHES*; none: the rows hidden."""
        self.places = list(places)[:len(self.rows)]
        for row, found in zip(self.rows, [*self.places, *[None] * len(self.rows)]):
            row.setVisible(found is not None)
            if found is not None:
                row.set_text(found.label)


class ModePane(Pane):
    """The ROG XBOX Ally X's Operating Mode page (owner, 31-10-2026): Silent, Performance, Turbo and Windows, a row each
    with its watts for the power source the device is on now; A sets the mode with the focus. Under them the Watt
    limits row installs or removes the helper that writes the watts. Shown only on the Ally X, from the Settings
    page's Operating mode row."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        heading = QHBoxLayout()
        heading.addWidget(text_label("Performance Mode", NAME, QFont.Weight.ExtraBold))
        heading.addStretch()
        self.info = InfoPill("Performance Mode", "")
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
            "The ROG XBOX Ally X's performance modes, as Armoury Crate's Command Center offers them. Each row shows the "
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


__all__ = ["AppPane", "DetailsPane", "ModePane", "SuitePane", "Tabs", "TEXT", "UpdateBanner"]
