# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal's intro, about three seconds when it opens (owner, 28-10-2026: the BC250 portal's intro of Suite Big
Picture Mode with its sound, here with this suite's name, icon and amber; a handheld has no mode to switch to, so
it plays at the start). Painted over the window: a light sweeps across a dark screen, rings open from the suite's
icon, the name draws itself in wide letters and settles, and the screen clears to the tiles. Any key, tap or button
skips it, and its sound with it (skip(), also called for the controller's buttons).

It covers the window from its first frame (cover(), before the window shows) and is dark from the start: the tiles
show only as it clears at the end (owner, 28-10-2026: the page showed first, then the intro faded in over it)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPointF, QRect, QRectF, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QWidget

from bc250_core.portable import AMBER, BACKGROUND, font

from . import APP_NAME, INTRO_SOUND, LOGO_PATH

INTRO_MS = 3000                 # about three seconds, as the BC250 portal's
LOGO_SHARE = 0.26               # the icon: this part of the screen's shorter side


def play(sound: Path | None) -> None:
    """Play a .wav in the background with Windows' own player (winsound: no Qt Multimedia in the program), or stop
    the one playing (None). Without winsound (Linux) or without an audio output the intro stays silent."""
    try:
        import winsound
        if sound is None:
            winsound.PlaySound(None, 0)
        elif sound.is_file():
            winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except (ImportError, RuntimeError):     # not Windows, or no sound device: no sound, no message
        pass


class Intro(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent: QWidget, duration: int = INTRO_MS, name: str = APP_NAME,
                 sound: Path | None = INTRO_SOUND, player: Callable[[Path | None], None] | None = None):
        super().__init__(parent)
        self.progress = 0.0
        self.name, self.sound, self.player = name, sound, player or (lambda wav: play(wav))
        self.logo = QPixmap(str(LOGO_PATH))
        self._logo_at: tuple[int, float] | None = None
        self._logo_scaled = QPixmap()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(duration)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.valueChanged.connect(self._step)
        self.animation.finished.connect(self._done)
        self.done = False

    def cover(self) -> None:
        """Over the whole window, dark: called before the window shows, so its first frame is the intro's."""
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def begin(self) -> None:
        self.cover()
        self.setFocus()
        self.animation.start()
        if self.sound is not None:              # None: the suite's sound is off (the portal's Suite page)
            self.player(self.sound)

    def skip(self) -> None:
        if not self.done:
            self.player(None)                   # cut short: its sound stops too
        self.animation.stop()
        self._done()

    def _step(self, value) -> None:
        self.progress = float(value)
        self.update()

    def _done(self) -> None:
        if self.done:
            return
        self.done = True
        self.hide()
        self.finished.emit()
        self.deleteLater()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.skip()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.skip()

    def _logo_for(self, full: int) -> QPixmap:
        """The icon scaled once to its largest size on this screen's own pixels: drawing the picture straight to a
        few hundred pixels, 60 times a second, would alias."""
        ratio = self.devicePixelRatioF()
        if self._logo_at != (full, ratio):
            self._logo_scaled = self.logo.scaled(round(full * ratio), round(full * ratio),
                                                 Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
            self._logo_scaled.setDevicePixelRatio(ratio)
            self._logo_at = (full, ratio)
        return self._logo_scaled

    @staticmethod
    def _phase(p: float, start: float, end: float) -> float:
        return min(1.0, max(0.0, (p - start) / (end - start)))

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = self.progress
        w, h = self.width(), self.height()
        ease = QEasingCurve(QEasingCurve.Type.OutCubic)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        backdrop = QColor(BACKGROUND)
        backdrop.setAlphaF(1 - self._phase(p, 0.86, 1.0))     # dark from the start, clearing at the end
        painter.fillRect(self.rect(), backdrop)
        center = QPointF(w / 2, h / 2 - h * 0.06)
        accent = QColor(AMBER)

        # The grid of the floor, rushing toward the viewer.
        floor = self._phase(p, 0.05, 0.4) * (1 - self._phase(p, 0.8, 0.97))
        if floor > 0:
            horizon = center.y() + h * 0.12
            line = QColor(accent)
            line.setAlphaF(0.35 * floor)
            painter.setPen(QPen(line, 1.5))
            for i in range(-12, 13):
                painter.drawLine(QPointF(w / 2 + i * w * 0.02, horizon), QPointF(w / 2 + i * w * 0.14, h))
            slide = (p * 3.0) % 1.0
            for i in range(9):
                t = ((i + slide) / 9) ** 2
                y = horizon + (h - horizon) * t
                painter.drawLine(QPointF(0, y), QPointF(w, y))

        # The sweep of light.
        sweep = self._phase(p, 0.08, 0.5)
        if 0 < sweep < 1:
            x = -w * 0.2 + ease.valueForProgress(sweep) * w * 1.4
            beam = QLinearGradient(x - w * 0.18, 0, x + w * 0.18, 0)
            clear, bright = QColor(accent), QColor("#ffffff")
            clear.setAlpha(0)
            bright.setAlpha(230)
            beam.setColorAt(0.0, clear)
            beam.setColorAt(0.5, bright)
            beam.setColorAt(1.0, clear)
            painter.fillRect(QRectF(x - w * 0.18, center.y() - 3, w * 0.36, 6), beam)
            halo = QRadialGradient(QPointF(0, 0), w * 0.18)
            glow = QColor(accent)
            glow.setAlpha(120)
            halo.setColorAt(0, glow)
            glow.setAlpha(0)
            halo.setColorAt(1, glow)
            painter.save()
            painter.translate(x, center.y())
            painter.scale(1, 0.18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QPointF(0, 0), w * 0.18, w * 0.18)
            painter.restore()

        # The rings.
        for i in range(3):
            ring = self._phase(p, 0.22 + i * 0.07, 0.72 + i * 0.05)
            if 0 < ring < 1:
                radius = ease.valueForProgress(ring) * min(w, h) * (0.32 + 0.12 * i)
                color = QColor(accent)
                color.setAlphaF((1 - ring) * 0.8)
                painter.setPen(QPen(color, 3 - i * 0.7))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(center, radius, radius)

        # The icon.
        appear = ease.valueForProgress(self._phase(p, 0.2, 0.5))
        fade = 1 - self._phase(p, 0.86, 1.0)
        if not self.logo.isNull() and appear > 0:
            size = int(min(w, h) * LOGO_SHARE * (0.7 + 0.3 * appear))
            glow = QRadialGradient(center, size)
            tint = QColor(accent)
            tint.setAlphaF(0.5 * appear * fade)
            glow.setColorAt(0, tint)
            tint.setAlpha(0)
            glow.setColorAt(1, tint)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(center, size, size)
            painter.setOpacity(appear * fade)
            painter.drawPixmap(QRect(int(center.x() - size / 2), int(center.y() - size / 2), size, size),
                               self._logo_for(int(min(w, h) * LOGO_SHARE)))
            painter.setOpacity(1.0)

        # The name, in wide letters that close up as it lands.
        text = self._phase(p, 0.38, 0.75)
        if text > 0:
            face = font(10, QFont.Weight.ExtraBold)
            face.setPixelSize(max(18, int(h * 0.055)))
            spacing = 0.9 - 0.7 * ease.valueForProgress(text)
            face.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, face.pixelSize() * spacing)
            painter.setFont(face)
            color = QColor("#ffffff")
            color.setAlphaF(ease.valueForProgress(text) * fade)
            painter.setPen(color)
            box = QRect(0, int(center.y() + min(w, h) * 0.17), w, face.pixelSize() * 2)
            painter.drawText(box, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                             self.name.upper())
        painter.end()
