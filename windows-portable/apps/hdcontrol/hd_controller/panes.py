# SPDX-License-Identifier: GPL-3.0-or-later
"""The panes beside the cards (Controller, Test, Firmware, Profiles, Settings) and the pages that take a pane's place
(the introduction, the profile editor and its name, the firmware file's browser), with their texts. The BC250 app's
pages.py and its window's boxes, for the handheld: what its dialogs and tooltips said is in a pane's information
(InfoPill, Menu), and every action is a controller button in the window's legend, A too, never a pill (owner,
29-10-2026: one way everywhere). A long list is a ListArea, as Xenia Manager's: rows in a column that scrolls, the one
with the focus kept in view, so the d-pad goes down a list of any length and a finger can drag it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLineEdit, QScrollArea, QScroller, QVBoxLayout,
                             QWidget)

from bc250_core.portable import (AMBER, BODY, DIM, RAISED, ROW_HEIGHT, TEXT, InfoPill, Pane, Row, font, px,
                                 text_label)

from . import firmware, profiles, specs
from .battery import BatteryIcon
from .drawing import ControllerView

SYMBOLS = {"Triangle": "△", "Square": "□", "Cross": "✕", "Circle": "○"}

CONTROLLER_INFO = (
    "Your DualSense or DualSense Edge, as Windows has it: plugged in with a USB cable or paired over Bluetooth. "
    "Windows lets you play with it as it is; this app looks after the controller itself: its battery, its firmware "
    "and, on a DualSense Edge, its profiles.\n\n"
    "Nothing is read from the controller before you press the A button (Read): then the app reads its firmware and "
    "its profiles, and follows it (its battery, the reports a second). From then on it reads each controller as it "
    "connects, until the app closes. With more than one controller connected, LB and RB choose the one the app "
    "shows. The app needs no administrator and no driver: Windows gives every user the controller.\n\n"
    "Reports is how many input reports a second the controller sends now: steady and high is a good connection; a "
    "low or jumpy number over Bluetooth points to interference or distance. The battery is what the controller "
    "reports, in tens of percent.")
TEST_INFO = (
    "The drawing follows your controller live: a button lights while you press it (the Edge's Fn and back buttons "
    "too), the sticks move and the triggers fill as far as you pull them. A tap on a part names it. The drawing is the "
    "app's own, with the face buttons in the colors of the first PlayStation pads.\n\n"
    "The A button starts the test: from then on every button of every controller only lights the drawing, so the "
    "controller you test does not move the app (its Circle is B, its Cross A). Hold B for two seconds to end the "
    "test, or tap B Back in the row at the bottom.\n\n"
    "The X button (Test vibration) runs the left motor, then the right one, almost a second each, and the drawing "
    "shakes on that side: you should feel each on its own side. A motor that stays still while the drawing shakes is "
    "worth a closer look.\n\n"
    "The Y button (Light bar) gives the light bar the next color: Blue, Red, Green, Purple, White, Off, or as the "
    "system sets it. The app sets it at once and again each time the controller connects while the app is open; the "
    "controller forgets it when it disconnects, and Steam or a game may set another. Off saves some battery.")
FIRMWARE_INFO = (
    "Controller updates are offered officially on a PS5 and in an app for Windows. This app sends the same firmware "
    f"from {firmware.SOURCE}, over a USB cable. The controller checks the firmware's signature before it takes it.\n\n"
    "The Y button (Check for an update) asks the update server for the latest version of each controller; with "
    "Check when the app opens on (the Settings card), the app asks by itself, at most once a day. When a newer "
    "version is out, the A button (Update) downloads it (about 1 MB) and keeps it, checks that it fits (the firmware "
    "names the controller it is for, and it must be newer than the one the controller runs), saves a backup of the "
    "Edge's profiles, and sends it. It asks for a second press first. It takes about half a minute; the controller "
    "then restarts by itself and comes back with its new version.\n\n"
    "Before it starts: connect the controller with a USB cable (the update does not go over Bluetooth), quit Steam "
    "(Steam, Exit) and any other program that talks to the controller (the app names it and does not start while it "
    "runs), and leave the cable in until the pane says the update is done. The update cannot be stopped: the View "
    "button waits for it. The Bluetooth pairing does not survive it: remove the controller from Windows' Bluetooth "
    "settings and pair it anew.\n\n"
    "The X button (Use a file) sends a firmware file you have (FWUPDATE<target>.bin), for example one kept from the "
    "update server before: the app checks it the same way and refuses one for another controller or one that is not "
    "newer.\n\n"
    "The app knows the files that were on the update server on 23-10-2026 by their SHA-256 (target, version):\n"
    + "\n".join(f"{known.target:04X} {firmware.TARGET_NAMES.get(known.target, '')} "
                f"{firmware.version_text(known.version)}: {digest}" for digest, known in firmware.KNOWN.items())
    + "\nA newer file from the update server works too; the pane then says the app does not know it yet. The "
    "controller checks its signature either way.")
PROFILES_INFO = (
    "The DualSense Edge keeps four profiles; Fn and Triangle, Square, Cross or Circle chooses one (Triangle is the "
    "default profile). The rows show them as the controller reports them; the one the controller uses now says "
    "Active, and follows when you switch with Fn. Under the rows, what the focused one sets: each stick's curve, each "
    "trigger's range, and the buttons that send something other than themselves. A profile whose checksum does not "
    "match is marked.\n\n"
    "With the controller on the USB cable, the A button creates a profile in an empty slot (starting from the "
    "default profile's settings) or edits one, and the X button clears one, on a second press. The default profile "
    "(Fn + Triangle) is never changed. The app saves a backup of all four before every change and before a firmware "
    "update; the Y button (Back up) saves one now, and LT (Read again) reads them anew, for example after you changed "
    "them on a PS5. The backups are JSON files, exactly as the controller holds the profiles.\n\n"
    "The controller applies a profile itself: after Fn + Square, a button you set to send another sends that one, "
    "and the sticks follow their curves. A profile's trigger range is kept in it; whether Windows' games use it is "
    "the controller's and the game's. The plain DualSense has no profiles.")
EDITOR_INFO = (
    "The A button gives the row with the focus its next value, the X button the one before. Name: the A button opens "
    "a page to type it (up to 39 characters; R3 opens the touch keyboard). Sticks: each stick's curve (Default, "
    "Quick, Precise, Steady, Digital or Dynamic) and its sensitivity, 0 to 10. A profile made on a PS5 says \"as it "
    "is\": its curve stays exactly as it was until you change the curve or the sensitivity. Triggers: where on its "
    "travel L2 and R2 start and stop counting, in steps of 5 %. Buttons: what each one sends, the back buttons "
    "included: its own, another button, Options or the touchpad's click.\n\n"
    "The Y button (Save to the controller) saves a backup of all four profiles, writes this one and reads it back to "
    "check that the controller kept it. The B button goes back and saves nothing. The parts of a profile the app does "
    "not show stay as the controller holds them.")
NAME_TEXT = ("The profile's name: up to 39 characters. R3 (the right stick pressed) opens Windows' touch keyboard, or "
             "closes it; the A button takes the name, the B button goes back without it.")
SETTINGS_INFO = (
    "Check when the app opens: the app asks the official update server for the latest firmware when it opens, at "
    "most once a day, so the Firmware card knows it without a press. The A button switches it.\n\n"
    "Show the introduction: the three short pages shown after the first controller was read.")
BROWSE_INFO = (
    "Pick the firmware file (a .bin, FWUPDATE<target>.bin from the update server): the A button opens a place or a "
    "folder, and picks a file; the B button goes a level up, and from the places back to the Firmware card. The app "
    "checks the file before it asks for the second press that sends it.")


def fill_grid(grid: QGridLayout, rows: Sequence[tuple[str, str]]) -> None:
    """*rows* (label, value) in *grid*: the label dimmed on the left, the value on the right, as every pane has them."""
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
    for r, (label, value) in enumerate(rows):
        grid.addWidget(text_label(label, BODY + 1, color=DIM), r, 0, Qt.AlignmentFlag.AlignTop)
        shown = text_label(value, BODY + 1, QFont.Weight.DemiBold, wrap=True)
        shown.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        grid.addWidget(shown, r, 1)
    grid.setColumnStretch(1, 1)


def wrappable(text: str, every: int = 16) -> str:
    """A long word (a SHA-256) that may wrap every *every* characters, as a line too long would widen the pane."""
    return "​".join(text[i:i + every] for i in range(0, len(text), every))


class ListArea(QScrollArea):
    """Rows in a column that scrolls; picked(key) when A or a tap acts on one, current(key) when one gets the
    focus."""

    picked = pyqtSignal(str)
    current = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget "
                           "{ background: transparent; }")
        self.setMinimumHeight(px(ROW_HEIGHT * 2 + 8))
        self.inner = QWidget()
        self.column = QVBoxLayout(self.inner)
        self.column.setContentsMargins(0, 0, px(4), 0)
        self.column.setSpacing(px(6))
        self.column.addStretch()
        self.setWidget(self.inner)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture)  # a finger drags
        self.pills: dict[str, Row] = {}
        self._keys: dict[QObject, str] = {}

    def set_items(self, items: Sequence[tuple[str, str]]) -> None:
        """The list's (key, text) rows, in order. A row whose key is there already keeps its widget and its focus
        (the editor changes a row's text with every press); the others go. The focus, when a row that went had it,
        moves to the first row: a row taken away with the focus would hand it to a card."""
        keys = [key for key, _text in items]
        if keys == list(self.pills):
            for key, text in items:
                self.pills[key].set_text(text)
            return
        old = self.pills
        had = next((key for key, pill in old.items() if pill.hasFocus()), None)
        self.pills, self._keys = {}, {}
        for n, (key, text) in enumerate(items):
            pill = Row(text)
            pill.activated.connect(lambda key=key: self.picked.emit(key))
            pill.installEventFilter(self)
            self.column.insertWidget(n, pill)
            if self.isVisible():
                pill.show()                             # shown now, so it can take the focus at once
            self.pills[key] = pill
            self._keys[pill] = key
        if had is not None:
            keep = self.pills.get(had) or self.first()
            if keep is not None:
                keep.setFocus()
        for pill in old.values():
            pill.removeEventFilter(self)
            pill.hide()
            pill.deleteLater()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FocusIn and obj in self._keys:
            self.ensureWidgetVisible(obj, 0, px(8))
            self.current.emit(self._keys[obj])
        return super().eventFilter(obj, event)

    def first(self) -> Row | None:
        return next(iter(self.pills.values()), None)

    def focused(self) -> str:
        """The key of the row with the focus, "" when none has it."""
        return next((key for key, pill in self.pills.items() if pill.hasFocus()), "")


def _heading(pane: Pane, title: str, info_title: str, info: str) -> tuple[object, InfoPill]:
    row = QHBoxLayout()
    label = text_label(title, 24, QFont.Weight.ExtraBold)
    row.addWidget(label)
    row.addStretch()
    pill = InfoPill(info_title, info)
    row.addWidget(pill, 0, Qt.AlignmentFlag.AlignTop)
    pane.column.addLayout(row)
    return label, pill


def _status(pane: Pane):
    status = text_label("", BODY + 1, QFont.Weight.DemiBold, AMBER, wrap=True)
    pane.column.addWidget(status)
    return status


class ListPane(Pane):
    """A heading with the information icon, a line under it, a ListArea and the status line."""

    def __init__(self, title: str, info_title: str, info: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading, self.info = _heading(self, title, info_title, info)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.column.addWidget(self.list, 1)
        self.status = _status(self)


class ControllerPane(Pane):
    """The controller: its rows and its battery; while none is connected, the drawing with a cable going into its
    port, and what to do (the BC250 app's Connect page)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading, self.info = _heading(self, "Controller", "The controller", CONTROLLER_INFO)
        self.column.addSpacing(px(8))
        self.found = QWidget()
        row = QHBoxLayout(self.found)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(px(24))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        row.addLayout(self.grid, 1)
        self.battery = BatteryIcon()
        row.addWidget(self.battery, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addWidget(self.found)
        self.connect_view = ControllerView(edge=True)
        self.connect_view.lit({"usb"})
        self.column.addWidget(self.connect_view, 1)
        self.stretch = QWidget()                        # the room under the rows, while there are rows
        self.column.addWidget(self.stretch, 1)
        self.status = _status(self)
        self.show_found(False)

    def show_found(self, found: bool) -> None:
        """The rows and the battery with a controller; the drawing with the cable going in without one."""
        self.found.setVisible(found)
        self.stretch.setVisible(found)
        self.connect_view.setVisible(not found)
        self.connect_view.animate_cable(not found and self.isVisible())

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.connect_view.animate_cable(self.connect_view.isVisibleTo(self))
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.connect_view.animate_cable(False)
        super().hideEvent(event)


class TestPane(Pane):
    """The drawing, live, and the status line under it (the BC250 app's Controller box)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading, self.info = _heading(self, "Test", "The test", TEST_INFO)
        self.view = ControllerView(edge=True)
        self.column.addWidget(self.view, 1)
        self.status = _status(self)


class FirmwarePane(Pane):
    """The firmware's rows, the drawing while an update sends it, and the status line."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading, self.info = _heading(self, "Firmware", "The firmware", FIRMWARE_INFO)
        self.column.addSpacing(px(8))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(4))
        self.column.addLayout(self.grid)
        self.view = ControllerView(edge=True)           # the cable plugged in and the data flowing, while it sends
        self.view.hide()
        self.column.addWidget(self.view, 1)
        self.stretch = QWidget()
        self.column.addWidget(self.stretch, 1)
        self.status = _status(self)

    def show_sending(self, progress: float | None) -> None:
        """The drawing with the data going in (*progress* 0 to 1), or the rows alone (None)."""
        self.view.setVisible(progress is not None)
        self.stretch.setVisible(progress is None)
        self.view.show_data(progress)


class ProfilesPane(Pane):
    """The four slots as rows, what the focused one sets under them, and the status line."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading, self.info = _heading(self, "Profiles", "The profiles", PROFILES_INFO)
        self.summary = text_label("", BODY + 1, color=DIM, wrap=True)
        self.column.addWidget(self.summary)
        self.column.addSpacing(px(8))
        self.list = ListArea()
        self.list.setFixedHeight(px(4 * ROW_HEIGHT + 3 * 6 + 4))
        self.column.addWidget(self.list)
        self.column.addSpacing(px(10))
        under = QHBoxLayout()
        under.setSpacing(px(20))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(px(16))
        self.grid.setVerticalSpacing(px(2))
        under.addLayout(self.grid, 1)
        self.view = ControllerView(edge=True)           # what the focused profile sets, lit (the BC250 app's
        self.view.setFixedWidth(px(230))                # chosen card on its drawing)
        under.addWidget(self.view, 0, Qt.AlignmentFlag.AlignTop)
        self.column.addLayout(under, 1)
        self.status = _status(self)


class NamePane(Pane):
    """A profile's name: the text and the field; A and R3 the keyboard are in the legend."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.heading = text_label("Name", 24, QFont.Weight.ExtraBold)
        self.column.addWidget(self.heading)
        self.column.addSpacing(px(6))
        self.column.addWidget(text_label(NAME_TEXT, BODY + 1, color=DIM, wrap=True))
        self.column.addSpacing(px(12))
        self.field = QLineEdit()
        self.field.setMaxLength(profiles.NAME_BYTES // 2)
        self.field.setPlaceholderText("The profile's name")
        self.field.setFont(font(BODY + 2))
        self.field.setMinimumHeight(px(44))
        self.field.setStyleSheet(f"QLineEdit {{ color: {TEXT}; background: {RAISED}; border: none; "
                                 f"border-radius: {px(10)}px; padding: 0 {px(12)}px; }}")
        self.column.addWidget(self.field)
        self.column.addStretch()
        self.status = _status(self)


@dataclass(frozen=True)
class IntroStep:
    title: str
    text: str
    parts: tuple[str, ...]


def intro_steps(edge: bool) -> list[IntroStep]:
    """Three pages, for someone who has never looked after a controller: what the app is, the firmware, and the
    Edge's profiles (or, on a DualSense, its battery)."""
    steps = [
        IntroStep("Your controller on the handheld",
                  "Windows already lets you play with your controller. This app looks after the controller itself: "
                  "it shows its battery and its firmware, keeps the firmware up to date and, on a DualSense Edge, "
                  "shows its profiles.", ("ps", "touchpad", "lightbar")),
        IntroStep("Up-to-date firmware",
                  "Controllers get better with firmware updates, offered officially only on a PS5 and in an app for "
                  "Windows. This app gets the same firmware from the official update server and puts it on the "
                  "controller over the USB cable, in about half a minute. Leave the cable in until it is done.",
                  ("usb",)),
    ]
    if edge:
        steps.append(IntroStep(
            "Four profiles",
            "The DualSense Edge keeps four profiles. Hold Fn, below a stick, and press Triangle, Square, Cross or "
            "Circle to switch. A profile sets how the sticks respond, how far the triggers travel and what each "
            "button does, the back buttons too. The app shows each profile, keeps a backup of them, and creates and "
            "edits the three besides the default.",
            ("fn", "back", "sticks", "triggers")))
    else:
        steps.append(IntroStep(
            "The battery",
            "The Controller card shows how full the battery is, in steps of 10 %. The controller charges while the "
            "USB cable is in, also from the handheld.", ("lightbar",)))
    return steps


class IntroPane(Pane):
    """The introduction's pages: the drawing with what the page is about lit, its title, its text and where it is
    (A Next, X Back, B Skip are in the legend)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.steps = intro_steps(True)
        self.index = 0
        self.view = ControllerView(edge=True)
        self.column.addWidget(self.view, 1)
        self.title = text_label("", 22, QFont.Weight.ExtraBold)
        self.title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.column.addWidget(self.title)
        self.text = text_label("", BODY + 1, wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.column.addWidget(self.text)
        self.counter = text_label("", BODY, color=DIM)
        self.counter.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.column.addWidget(self.counter)

    def start(self, edge: bool) -> None:
        self.steps = intro_steps(edge)
        self.view.set_edge(edge)
        self.go(0)

    def go(self, index: int) -> None:
        self.index = max(0, min(index, len(self.steps) - 1))
        step = self.steps[self.index]
        self.title.setText(step.title)
        self.text.setText(step.text)
        self.view.lit(step.parts)
        self.counter.setText(f"{self.index + 1} of {len(self.steps)}")

    @property
    def last(self) -> bool:
        return self.index == len(self.steps) - 1


def spec_text(live: Sequence[tuple[str, str]], product: int) -> str:
    """The spec sheet (the BC250 app's, owner 23-10-2026) as the information's text: this controller, read from it
    now; the model's facts, each with its source; and the parts the drawing leaves out, as the controller does not
    report them."""
    sources: list[tuple[str, str]] = []
    lines = ["This controller"] + [f"{name}: {value}" for name, value in live]
    lines += ["", "Specifications"]
    facts = specs.facts(product)
    for fact in facts:
        if fact.source not in sources:
            sources.append(fact.source)
        lines.append(f"{fact.name}: {fact.value} [{sources.index(fact.source) + 1}]")
    if not facts:
        lines.append("The app has no specifications of this model yet: only facts from an official source go in.")
    lines += ["", "Not in the drawing (the controller does not report these)"]
    lines += [f"{part.name} ({part.where}): {part.what}" for part in specs.parts(product)]
    if sources:
        lines += ["", "Sources"] + [f"{index}. {name}: {url}" for index, (name, url) in enumerate(sources, 1)]
    return "\n".join(lines)
