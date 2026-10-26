# SPDX-License-Identifier: GPL-3.0-or-later
"""What the video tours share (bc250-bazzite/tools/portal_tour.py, tools/app_tour.py): a temporary home for an offscreen Qt, and
Recorder, which renders a window frame by frame into an MP4 (H.264, 1920 x 1080, no sound) with a pointer, clicks,
captions and title cards drawn in, and add_music(), which lays a track under a finished video."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _suites():
    spec = importlib.util.spec_from_file_location("nexus_suites", ROOT / "tools" / "suites.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


suites = _suites()
SUITE = suites.suite()                              # the default suite (the tours take --suite)
WIDTH, HEIGHT = 1920, 1080
SCALE = 1.2                                         # the window is 1600 x 900 at 120 %: readable on a phone too


def prepare_home(home: Path) -> None:
    for var, sub in (("HOME", ""), ("XDG_DATA_HOME", ".local/share"), ("XDG_CONFIG_HOME", ".config"),
                     ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        (home / sub).mkdir(parents=True, exist_ok=True)
        os.environ[var] = str(home / sub)
    # One screen of the video's size, so Big Picture Mode's fullscreen is the window's 1600 x 900 at 120 %.
    screen = {"screens": [{"name": "tour", "x": 0, "y": 0, "width": WIDTH, "height": HEIGHT,
                           "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}
    (home / "screen.json").write_text(json.dumps(screen), encoding="utf-8")
    os.environ["QT_QPA_PLATFORM"] = f"offscreen:configfile={home / 'screen.json'}"
    os.environ["QT_SCALE_FACTOR"] = str(SCALE)
    os.environ.pop("QT_SCREEN_SCALE_FACTORS", None)
    sys.path[:0] = [str(ROOT / "core")]


def add_music(video: Path, music: Path, out: Path, seconds: float, fade: float = 2.0) -> int:
    """*video* (*seconds* long) with *music* under it, looped when shorter and faded out over the last *fade*
    seconds, into *out* (AAC); the picture is copied as it is. ffmpeg's exit code."""
    return subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(music),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", f"afade=t=out:st={max(0.0, seconds - fade):.3f}:d={fade}",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(out)]).returncode


def place(window) -> None:
    """The window at the top left, the size of the video."""
    window.move(0, 0)
    window.resize(round(WIDTH / SCALE), round(HEIGHT / SCALE))


class Recorder:
    """Renders *window* into *out*. *logo* is the picture on the title cards."""

    def __init__(self, out: Path, fps: int, window, logo: Path | None = None):
        from PyQt6.QtWidgets import QApplication

        self.fps = fps
        self.app = QApplication.instance()
        self.window = window
        self.logo = logo
        self.pointer = (WIDTH * 0.55, HEIGHT * 0.6)
        self.click_at: tuple[float, float, int] | None = None
        self.caption = ""
        self.popup = None
        self.overlay = None                         # a whole frame drawn instead of the window (title cards)
        self.frames = 0                             # written so far: the video's length is frames / fps
        self.ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}",
             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)

    # --- frames ---------------------------------------------------------------------------------------------
    def pump(self) -> None:
        for _ in range(3):
            self.app.processEvents()

    def frame(self):
        from PyQt6.QtCore import QPointF, QRectF, Qt
        from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

        image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB888)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.overlay is not None:
            painter.drawImage(0, 0, self.overlay)
        else:
            shot = self.window.grab()
            painter.drawPixmap(QRectF(0, 0, WIDTH, HEIGHT), shot, QRectF(shot.rect()))
            if self.popup is not None and self.popup.isVisible():
                menu = self.popup.grab()
                top_left = self.popup.pos() - self.window.pos()
                painter.drawPixmap(QRectF(top_left.x() * SCALE, top_left.y() * SCALE, menu.width(), menu.height()),
                                   menu, QRectF(menu.rect()))
            if self.click_at is not None:
                x, y, age = self.click_at
                radius = 12 + age * 3
                painter.setPen(QPen(QColor(255, 255, 255, max(0, 230 - age * 28)), 4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), radius, radius)
                self.click_at = (x, y, age + 1) if age < 8 else None
            x, y = self.pointer
            arrow = QPainterPath()
            for i, (dx, dy) in enumerate(((0, 0), (0, 34), (9, 26), (15, 40), (21, 37), (15, 24), (27, 24))):
                (arrow.moveTo if i == 0 else arrow.lineTo)(x + dx, y + dy)
            arrow.closeSubpath()
            painter.setPen(QPen(QColor("black"), 2))
            painter.setBrush(QColor("white"))
            painter.drawPath(arrow)
        if self.caption:
            font = QFont(self.app.font())
            font.setPixelSize(34)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            box = painter.boundingRect(QRectF(0, 0, WIDTH - 360, 400),
                                       int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), self.caption)
            box = box.adjusted(-28, -18, 28, 18)
            box.moveCenter(QPointF(WIDTH / 2, HEIGHT - 70 - box.height() / 2))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(10, 14, 22, 215))
            painter.drawRoundedRect(box, 14, 14)
            painter.setPen(QColor("white"))
            painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), self.caption)
        painter.end()
        return image

    def emit(self, image, count: int = 1) -> None:
        data = image.constBits().asstring(image.sizeInBytes())
        stride = image.bytesPerLine()
        if stride != WIDTH * 3:
            data = b"".join(data[row * stride: row * stride + WIDTH * 3] for row in range(HEIGHT))
        assert self.ffmpeg.stdin is not None
        for _ in range(count):
            self.ffmpeg.stdin.write(data)
        self.frames += count

    def hold(self, seconds: float) -> None:
        """The same picture for *seconds* (a click ring still fades out first)."""
        frames = round(seconds * self.fps)
        while self.click_at is not None and frames > 0:
            self.pump()
            self.emit(self.frame())
            frames -= 1
        self.pump()
        self.emit(self.frame(), max(frames, 0))

    def move(self, target: tuple[float, float], seconds: float = 0.8) -> None:
        start, frames = self.pointer, max(1, round(seconds * self.fps))
        for i in range(1, frames + 1):
            t = i / frames
            ease = t * t * (3 - 2 * t)
            self.pointer = (start[0] + (target[0] - start[0]) * ease, start[1] + (target[1] - start[1]) * ease)
            self.pump()
            self.emit(self.frame())

    def at(self, widget, fx: float = 0.5, fy: float = 0.5) -> tuple[float, float]:
        """Where a point of *widget* is in the video (fractions of its width and height)."""
        from PyQt6.QtCore import QPoint
        point = widget.mapTo(self.window, QPoint(round(widget.width() * fx), round(widget.height() * fy)))
        return point.x() * SCALE, point.y() * SCALE

    def tab_at(self, bar, index: int) -> tuple[float, float]:
        """Where tab *index* of the QTabBar *bar* is in the video."""
        from PyQt6.QtCore import QPoint
        point = bar.mapTo(self.window, bar.tabRect(index).center() + QPoint(0, 2))
        return point.x() * SCALE, point.y() * SCALE

    def click(self, action=None) -> None:
        self.click_at = (*self.pointer, 0)
        self.emit(self.frame(), 2)
        if action is not None:
            action()
        self.pump()

    def say(self, text: str) -> None:
        self.caption = text

    def fade(self, first, second, seconds: float = 0.6) -> None:
        from PyQt6.QtGui import QPainter
        frames = max(1, round(seconds * self.fps))
        for i in range(1, frames + 1):
            image = first.copy()
            painter = QPainter(image)
            painter.setOpacity(i / frames)
            painter.drawImage(0, 0, second)
            painter.end()
            self.emit(image)

    def card(self, title: str, lines: list[str]):
        """A title card in the theme's colors, with the logo."""
        from PyQt6.QtCore import QRectF, Qt
        from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPalette, QPixmap

        image = QImage(WIDTH, HEIGHT, QImage.Format.Format_RGB888)
        image.fill(self.window.palette().color(QPalette.ColorRole.Window))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        logo = QPixmap(str(self.logo)) if self.logo is not None else QPixmap()
        if not logo.isNull():
            painter.drawPixmap(QRectF(WIDTH / 2 - 128, 190, 256, 256), logo, QRectF(logo.rect()))
        font = QFont(self.app.font())
        font.setPixelSize(76)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        text = self.window.palette().color(QPalette.ColorRole.WindowText)
        painter.setPen(text)
        painter.drawText(QRectF(0, 490, WIDTH, 110), int(Qt.AlignmentFlag.AlignCenter), title)
        font.setPixelSize(40)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(text.red(), text.green(), text.blue(), 200))
        for i, line in enumerate(lines):
            painter.drawText(QRectF(0, 625 + i * 64, WIDTH, 60), int(Qt.AlignmentFlag.AlignCenter), line)
        painter.end()
        return image

    def finish(self) -> int:
        assert self.ffmpeg.stdin is not None
        self.ffmpeg.stdin.close()
        return self.ffmpeg.wait()
