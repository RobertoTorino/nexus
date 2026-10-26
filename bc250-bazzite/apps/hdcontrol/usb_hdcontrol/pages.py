# SPDX-License-Identifier: GPL-3.0-or-later
"""The window's pages besides the main one: the page that asks to connect a controller (the drawing with a cable
going in), the introduction of three pages shown after the first controller connects, and the card of one profile
on the main page."""

from __future__ import annotations

import html
from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.theme import header_font, muted, surface_style
from bc250_core.widgets import MetricBox, Pill, accent_button

from . import profiles, specs, style
from .drawing import ControllerView

SYMBOLS = {"Triangle": "△", "Square": "□", "Cross": "✕", "Circle": "○"}


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(header_font() + "font-size:22px; font-weight:800;")
    label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    return label


class WrappedText(QLabel):
    """A paragraph under the drawing, 620 px wide, that keeps the height of all its lines: in a column with the
    drawing, which takes whatever room it gets, a wrapped QLabel would be cut to two lines."""

    WIDTH = 620

    def __init__(self, text: str = ""):
        super().__init__()
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet("font-size:14px;")
        self.setFixedWidth(self.WIDTH)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt override)
        super().setText(text)
        self.ensurePolished()               # the style sheet's font, before the height is measured
        self.setFixedHeight(max(0, self.heightForWidth(self.WIDTH)))       # -1 for no text


def _text(text: str = "") -> WrappedText:
    return WrappedText(text)


class ConnectPage(QWidget):
    """Shown while no controller is connected: the drawing, a cable going into its port, and what to do."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.view = ControllerView(edge=True)
        self.view.lit({"usb"})
        layout.addWidget(self.view, 1)
        layout.addWidget(_title("Connect your controller"))
        self.text = _text("Plug your DualSense or DualSense Edge into a USB port of the board, with a USB-C cable. "
                          "The app finds it by itself. A controller paired over Bluetooth shows up too; only the "
                          "firmware update needs the cable.")
        layout.addWidget(self.text, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(12)
        self.held = False

    def set_held(self, held: bool) -> None:
        """A controller on the cable that Linux did not take, while it was still on Bluetooth: say what to do."""
        if held == self.held:
            return
        self.held = held
        self.text.setText(
            "Your controller is on the cable, but Linux did not take it while it was still connected over "
            "Bluetooth. Unplug the cable and plug it in again." if held else
            "Plug your DualSense or DualSense Edge into a USB port of the board, with a USB-C cable. The app finds "
            "it by itself. A controller paired over Bluetooth shows up too; only the firmware update needs the "
            "cable.")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.view.animate_cable(True)
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.view.animate_cable(False)
        super().hideEvent(event)


@dataclass(frozen=True)
class IntroStep:
    title: str
    text: str
    parts: tuple[str, ...]


def intro_steps(edge: bool) -> list[IntroStep]:
    """Three pages, for someone who has never looked after a controller: what the app is, the firmware, and the
    Edge's profiles (or, on a DualSense, its battery)."""
    steps = [
        IntroStep("Your controller on the board",
                  "Linux already lets you play with your controller. This app looks after the controller itself: it "
                  "shows its battery and its firmware, keeps the firmware up to date and, on a DualSense Edge, shows "
                  "its profiles.", ("ps", "touchpad", "lightbar")),
        IntroStep("Up-to-date firmware",
                  "Controllers get better with firmware updates, offered officially only on a PS5 and in an app for "
                  "Windows. This app gets the same firmware from the official update server and puts it on the "
                  "controller over the USB cable, in about half a minute. Leave the cable in until it is done.", ("usb",)),
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
            "The header shows how full the battery is, in steps of 10 %. The controller charges while the USB cable "
            "is in, also from the board.", ("lightbar",)))
    return steps


class IntroPage(QWidget):
    """The three pages, with Back, Next (Start on the last) and Skip; finished when the user is through."""

    finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.steps = intro_steps(True)
        self.index = 0
        layout = QVBoxLayout(self)
        self.view = ControllerView(edge=True)
        layout.addWidget(self.view, 1)
        self.title = _title("")
        layout.addWidget(self.title)
        self.text = _text()
        layout.addWidget(self.text, 0, Qt.AlignmentFlag.AlignHCenter)
        self.counter = QLabel()
        self.counter.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.counter.setStyleSheet(f"color:{muted()};")
        layout.addWidget(self.counter)
        buttons = QHBoxLayout()
        self.skip_button = QPushButton("Skip")
        self.skip_button.setToolTip("Goes straight to your controller. Show the introduction brings it back.")
        self.skip_button.clicked.connect(self.finished.emit)
        self.back_button = QPushButton("Back")
        self.back_button.setToolTip("The page before.")
        self.back_button.clicked.connect(lambda: self.go(self.index - 1))
        self.next_button = accent_button("Next", "The next page; on the last one, Start opens your controller.")
        self.next_button.clicked.connect(self.next)
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)

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
        self.back_button.setEnabled(self.index > 0)
        last = self.index == len(self.steps) - 1
        self.next_button.setText("Start" if last else "Next")
        self.skip_button.setVisible(not last)

    def next(self) -> None:
        if self.index == len(self.steps) - 1:
            self.finished.emit()
        else:
            self.go(self.index + 1)


WIDER = 1.05                        # the header's boxes 5 % wider than core makes them (owner, 23-10-2026)


class Box(MetricBox):
    """Core's header box, 5 % wider; its edges as core draws them (owner, 26-10-2026: the same as every app's)."""

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        hint = super().sizeHint()
        return QSize(round(hint.width() * WIDER), hint.height())


class SoftPill(Pill):
    """Core's header pill, 5 % wider; its edges as core draws them (owner, 26-10-2026)."""

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        hint = super().sizeHint()
        return QSize(round(hint.width() * WIDER), hint.height())


class Section(QFrame):
    """A box of the main page with its title in a blue bar along its top, touching its sides (owner, 23-10-2026),
    instead of a group box's title above its frame. Its content goes in *body*."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("section")
        self.setStyleSheet(f"#section {{ border:1px solid {style.EDGE}; border-radius:8px; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        self.bar = QLabel(title)
        self.bar.setObjectName("sectionBar")
        self.bar.setStyleSheet(f"#sectionBar {{ background:{style.BLUE}; color:white; font-weight:700; "
                               "padding:5px 10px; border-top-left-radius:7px; border-top-right-radius:7px; }")
        outer.addWidget(self.bar)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(10, 8, 10, 10)
        outer.addLayout(self.body, 1)


class InfoDialog(QDialog):
    """The spec sheet (owner, 23-10-2026): this controller, read from it now; the model's facts, each with its
    source; and the parts the drawing leaves out, as the controller does not report them."""

    def __init__(self, title: str, live: list[tuple[str, str]], product: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title(title))
        layout = QVBoxLayout(self)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextFormat(Qt.TextFormat.RichText)
        self.text.setOpenExternalLinks(True)
        self.text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text.setText(info_html(live, product))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.text)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(640, 620)


def info_html(live: list[tuple[str, str]], product: int) -> str:
    def table(rows: list[tuple[str, str]]) -> str:
        return "<table cellspacing='0' cellpadding='3'>" + "".join(
            f"<tr><td style='color:{muted()}; padding-right:14px' valign='top'>{name}</td><td>{value}</td></tr>"
            for name, value in rows) + "</table>"
    head = lambda text: f"<h3 style='color:{style.BLUE_LIGHT}'>{text}</h3>"  # noqa: E731
    sources: list[tuple[str, str]] = []
    rows = []
    for fact in specs.facts(product):
        if fact.source not in sources:
            sources.append(fact.source)
        rows.append((html.escape(fact.name), f"{html.escape(fact.value)} <sup>{sources.index(fact.source) + 1}</sup>"))
    parts = [(html.escape(part.name), f"{html.escape(part.what)} <span style='color:{muted()}'>"
                                       f"({html.escape(part.where)})</span>") for part in specs.parts(product)]
    text = head("This controller") + table([(html.escape(n), html.escape(v)) for n, v in live])
    text += head("Specifications")
    text += table(rows) if rows else (f"<p style='color:{muted()}'>The app has no specifications of this model yet: "
                                      "only facts from an official source go in.</p>")
    text += head("Not in the drawing") + f"<p style='color:{muted()}'>The controller does not report these.</p>"
    text += table(parts)
    if sources:
        text += head("Sources") + "".join(f"<p>{index}. <a href='{url}' style='color:{style.BLUE_LIGHT}'>"
                                          f"{html.escape(name)}</a></p>"
                                          for index, (name, url) in enumerate(sources, 1))
    return text


class ProfileCard(QFrame):
    """One profile slot, a column of the main page: Fn and its button, the name, and what the profile sets. A click
    chooses it, and the drawing then lights what it changes. Under it Create… on an empty slot, Edit… and Clear on a
    profile; the default profile (Fn + Triangle) has none: the app does not change it."""

    clicked = pyqtSignal(object)        # the Profile
    create = pyqtSignal(object)
    edit = pyqtSignal(object)
    clear = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.profile: profiles.Profile | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.slot = QLabel()
        self.slot.setStyleSheet("font-size:12px; font-weight:600;")
        self.active = QLabel("Active")
        self.active.setStyleSheet(f"font-size:12px; font-weight:700; color:{style.BLUE_LIGHT};")
        self.active.setToolTip("The profile the controller uses now.")
        self.active.setVisible(False)
        self.name = QLabel()
        self.name.setWordWrap(True)
        self.name.setTextFormat(Qt.TextFormat.PlainText)       # a profile's name is the user's text
        self.name.setStyleSheet(header_font() + "font-size:17px; font-weight:800;")
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        top = QHBoxLayout()
        top.addWidget(self.slot)
        top.addStretch(1)
        top.addWidget(self.active)
        layout.addLayout(top)
        for label in (self.name, self.details):
            layout.addWidget(label)
        layout.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.create_button = QPushButton("Create…")
        self.edit_button = QPushButton("Edit…")
        self.clear_button = QPushButton("Clear")
        for button, signal in ((self.create_button, self.create), (self.edit_button, self.edit),
                               (self.clear_button, self.clear)):
            button.clicked.connect(lambda _checked=False, signal=signal: signal.emit(self.profile))
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.set_actions(True, "")
        self.set_chosen(False)

    def set_chosen(self, chosen: bool) -> None:
        if chosen == getattr(self, "chosen", None):
            return
        self.chosen = chosen
        self.setStyleSheet(style.soften(surface_style(style.BLUE_LIGHT if chosen else None))
                           + "QLabel { background:transparent; border:none; }")

    def set_active(self, active: bool) -> None:
        self.active.setVisible(active)

    def set_actions(self, allowed: bool, reason: str) -> None:
        """Whether the profile may be changed now; *reason* says why not (the cable, an update running)."""
        profile = self.profile
        writable = profile is not None and profile.slot in profiles.WRITE_REPORTS
        self.create_button.setVisible(writable and profile.empty)
        self.edit_button.setVisible(writable and not profile.empty)
        self.clear_button.setVisible(writable and not profile.empty)
        for button, tip in ((self.create_button, "Makes a profile in this slot, starting from the default profile."),
                            (self.edit_button, "Changes this profile's name, sticks, triggers and buttons."),
                            (self.clear_button, "Removes this profile from the controller.")):
            button.setEnabled(allowed)
            button.setToolTip(tip if allowed else reason)

    def set_profile(self, profile: profiles.Profile) -> None:
        self.profile = profile
        self.slot.setText(f"Fn + {SYMBOLS[profile.slot]}  {profile.slot}")
        default = profile.slot not in profiles.WRITE_REPORTS
        self.setToolTip(f"Fn + {profile.slot}: no profile yet. Create… makes one." if profile.empty else
                        f"Fn + {profile.slot}: {profile.name}. Click to see on the drawing what it sets; click again "
                        "to let go." + (" The default profile: the app does not change it." if default else ""))
        if profile.empty:
            self.name.setText("Empty")
            self.name.setStyleSheet(header_font() + f"font-size:17px; font-weight:800; color:{muted()};")
            self.details.setText(f"<span style='color:{muted()}'>No profile in this slot.</span>")
            return
        self.name.setStyleSheet(header_font() + "font-size:17px; font-weight:800;")
        self.name.setText(profile.name + ("" if profile.crc_ok else " (checksum does not match)"))
        l_start, l_end, r_start, r_end = profile.triggers
        remapped = "<br>".join(f"{source} → {target}" for source, target in profile.remapped) or "Each its own"
        rows = (("Left stick", profile.left_curve), ("Right stick", profile.right_curve),
                ("L2", profiles.trigger_text(l_start, l_end)), ("R2", profiles.trigger_text(r_start, r_end)),
                ("Buttons", remapped))
        self.details.setText("<table cellspacing='0' cellpadding='2'>" + "".join(
            f"<tr><td style='color:{muted()}; padding-right:8px'>{name}</td><td>{value}</td></tr>"
            for name, value in rows) + "</table>")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self.profile is not None:
            self.clicked.emit(self.profile)
        super().mouseReleaseEvent(event)

