#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""A video tour of one app, for the wiki and YouTube: the app's real window from this checkout, rendered frame by
frame into an MP4 (H.264, 1920 x 1080, 30 fps) of about 40 seconds, one short video per app, with music under it
that fades out over the last two seconds (the suite's tools/sounds/the_quiet_engine.mp3, made with generative AI tools). The
same script for every app: only the name changes.

    python3 tools/app_tour.py APP [OUT.mp4] [--package PACKAGE] [--seconds 40] [--music FILE | --no-music] [--fps 30]

Default output: ~/Videos/bc250-<app>-tour-v<its VERSION>.mp4 (with the package for compute and cores).

APP is the app's key in the suite's portal/apps.toml (fan, cec, ...) or its folder under its apps/ (--suite names the
suite; with one suite in the checkout it is the default). An app with two programs
(compute, cores) needs --package to say which one (cu_bisect, cu_unlock, ...).

The app starts as it does on a board, through its own __main__, in a temporary home folder (no settings of yours)
and offscreen; the tour takes over where the app would wait for the user. pkexec, sudo and run0 refuse (and are
named on stderr): nothing runs as root and no password is asked. The tour shows the app's title card, its summary
from the manifest, the icon, the controls of the header with their own tooltips as the captions, the tabs (or the
pages of a list at the left), and the app's chapter of the wiki. What does not fit in the time is left out: the
header takes about 40 % of it, an even spread of the pages the rest. It only points and switches pages: it presses
no buttons, so it changes nothing. A dialog the app opens is closed, and named on stderr.

What the app reads at start is real: watch the video before publishing it, for names, addresses and serial numbers.
Needs PyQt6 (the dev venv) and ffmpeg with libx264. The frames are drawn by tools/tour_frames.py."""

from __future__ import annotations

import argparse
import os
import re
import runpy
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

import tour_frames
from tour_frames import SCALE, SUITE, Recorder

MANIFEST = SUITE / "portal" / "apps.toml"
SECONDS = 40                                        # the whole video, title and end cards included
HEADER_SHARE = 0.4                                  # of the time after the summary and the icon, with pages to show
END = 0.5 + 0.8 + 3.5                               # the end card: a pause, the fade, the card
MUSIC = SUITE / "tools" / "sounds" / "the_quiet_engine.mp3"
FADE = 2.0                                          # the music fades out over the video's last seconds


class Done(BaseException):
    """Raised from the app's exec() once the tour is recorded: through the app's main(), whatever it catches."""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


def find_app(name: str) -> tuple[Path, str, dict]:
    """The app's folder, its key and its table in the manifest (empty for an app the portal does not list)."""
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    for table in ("apps", "checkout"):
        entry = manifest.get(table, {}).get(name)
        if entry is not None:
            return SUITE / entry.get("folder", f"apps/{name}"), name, entry
    folder = SUITE / "apps" / name
    if not folder.is_dir():
        raise SystemExit(f"No app {name!r}: give its key in portal/apps.toml or its folder under apps/.")
    return folder, name, {}


def find_package(folder: Path, package: str | None) -> str:
    packages = sorted(p.parent.name for p in folder.glob("*/__main__.py"))
    if package is not None:
        if package not in packages:
            raise SystemExit(f"No package {package!r} in {folder.name}: {', '.join(packages) or 'none'}.")
        return package
    if len(packages) != 1:
        raise SystemExit(f"{folder.name} has {len(packages) or 'no'} programs"
                         + (f" ({', '.join(packages)}): say which with --package." if packages else "."))
    return packages[0]


def plain(text: str) -> str:
    """A tooltip as one short caption: no markup, its first sentence (two when they are short), at most about 110
    characters."""
    from PyQt6.QtGui import QTextDocument
    from PyQt6.QtCore import Qt
    document = QTextDocument()
    if Qt.mightBeRichText(text):
        document.setHtml(text)
    else:
        document.setPlainText(text)
    text = ""
    for line in (" ".join(line.split()) for line in document.toPlainText().splitlines() if line.strip()):
        # a line of its own ends a sentence; a line wrapped by hand goes on in lower case
        ends = text and text[-1] not in ".!?:;," and line[0].isupper()
        text = f"{text}{'.' if ends else ''} {line}".strip()
    caption = ""
    for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text):
        if caption and (len(caption) >= 40 or len(caption) + len(sentence) > 110):
            break
        caption = f"{caption} {sentence}".strip()
    if len(caption) > 120:
        caption = caption[:110].rsplit(" ", 1)[0] + " …"
    return caption


class AppTour(Recorder):
    def __init__(self, out: Path, fps: int, window, home: Path, folder: Path, key: str, entry: dict,
                 seconds: float = SECONDS):
        from PyQt6.QtWidgets import QApplication

        from bc250_core import appinfo
        app = QApplication.instance()
        info = appinfo.current()
        version = folder / "VERSION"
        self.version = info.version if info is not None else (
            app.applicationVersion() or (version.read_text(encoding="utf-8").strip() if version.is_file() else ""))
        self.name = info.name if info is not None else (
            (app.applicationDisplayName() or app.applicationName()).removesuffix(f" {self.version}"))
        self.key = key
        self.entry = entry
        self.told: set[str] = set()                 # the captions shown: each control once
        self.seconds = seconds
        logo = info.logo if info is not None and info.logo is not None and info.logo.is_file() else None
        if logo is None and not app.windowIcon().isNull():
            logo = home / "logo.png"
            app.windowIcon().pixmap(512, 512).save(str(logo))
        if logo is None:                            # the largest picture in images/
            logo = max(folder.glob("images/*.webp"), key=lambda path: path.stat().st_size, default=None)
        tour_frames.place(window)
        window.raise_()
        for _ in range(3):
            app.processEvents()
        super().__init__(out, fps, window, logo)

    # --- finding things in the window -----------------------------------------------------------------------
    def shown(self, widget) -> bool:
        return widget.isVisibleTo(self.window) and widget.width() > 4 and widget.height() > 4

    def top(self, widget) -> int:
        from PyQt6.QtCore import QPoint
        return widget.mapTo(self.window, QPoint(0, 0)).y()

    def logo_label(self):
        """The icon at the top left: the largest picture in the top quarter of the window."""
        from PyQt6.QtWidgets import QLabel
        pictures = [label for label in self.window.findChildren(QLabel)
                    if self.shown(label) and label.pixmap() is not None and not label.pixmap().isNull()
                    and self.top(label) < self.window.height() / 4]
        return max(pictures, key=lambda label: label.width() * label.height(), default=None)

    def pages(self) -> list[tuple]:
        """The window's pages: the tabs of its largest QTabWidget, else the rows of a list at the left that turns
        the pages of the largest QStackedWidget. Each as (where it is, how to open it, its name, its tooltip, the
        page)."""
        from PyQt6.QtWidgets import QListWidget, QStackedWidget, QTabWidget
        tabs = [t for t in self.window.findChildren(QTabWidget) if self.shown(t) and t.count() > 1]
        if tabs:
            tabs = max(tabs, key=lambda t: t.width() * t.height())
            return [(lambda i=i: self.tab_at(tabs.tabBar(), i), lambda i=i: tabs.setCurrentIndex(i),
                     tabs.tabText(i).replace("&", ""), tabs.tabToolTip(i), lambda i=i: tabs.widget(i))
                    for i in range(tabs.count()) if tabs.isTabVisible(i) and tabs.isTabEnabled(i)]
        stacks = [s for s in self.window.findChildren(QStackedWidget) if self.shown(s) and s.count() > 1]
        stack = max(stacks, key=lambda s: s.width() * s.height(), default=None)
        for nav in self.window.findChildren(QListWidget):
            if stack is None or not self.shown(nav) or not 1 < nav.count() <= 30 \
                    or self.at(nav)[0] > self.window.width() * 0.3:
                continue
            return [(lambda i=i: self.row_at(nav, i), lambda i=i: nav.setCurrentRow(i), nav.item(i).text(),
                     nav.item(i).toolTip(), lambda: stack.currentWidget())
                    for i in range(nav.count()) if not nav.item(i).isHidden()]
        return []

    def row_at(self, nav, row: int) -> tuple[float, float]:
        from PyQt6.QtCore import QPoint
        rect = nav.visualItemRect(nav.item(row))
        point = nav.viewport().mapTo(self.window, rect.center() + QPoint(-rect.width() // 4, 0))
        return point.x() * SCALE, point.y() * SCALE

    def top_of_pages(self) -> int:
        """Where the pages start: the header is above it."""
        from PyQt6.QtWidgets import QListWidget, QStackedWidget, QTabWidget
        tops = [self.top(w) for kind in (QTabWidget, QStackedWidget, QListWidget)
                for w in self.window.findChildren(kind) if self.shown(w) and w.height() > self.window.height() / 3]
        return min(tops, default=self.window.height() // 3)

    def controls(self, inside, above: int | None = None) -> list:
        """The widgets with a tooltip in *inside*, top to bottom and left to right (none inside another one), those
        above *above* only when it is given; none the tour showed already."""
        from PyQt6.QtWidgets import QTabBar, QWidget
        found, seen = [], set(self.told)
        for widget in inside.findChildren(QWidget):
            if not widget.toolTip().strip() or not self.shown(widget) or isinstance(widget, QTabBar):
                continue
            if widget.width() > self.window.width() * 0.6:      # a whole panel, not a control
                continue
            if above is not None and self.top(widget) + widget.height() > above:
                continue
            found.append(widget)
        found = [w for w in found if not any(o is not w and o.isAncestorOf(w) for o in found)]
        found.sort(key=lambda w: (self.top(w) // 24, w.mapTo(self.window, w.rect().topLeft()).x()))
        picked = []
        for widget in found:
            caption = plain(widget.toolTip())
            if caption and caption not in seen:
                seen.add(caption)
                picked.append((widget, caption))
        return picked

    def read(self, caption: str) -> float:
        """Long enough to read *caption*."""
        return max(2.0, 0.8 + len(caption) / 20)

    # --- the time -------------------------------------------------------------------------------------------
    def left(self) -> float:
        """The seconds still free before the end card."""
        return self.seconds - END - self.frames / self.fps

    def point_out(self, widgets: list, keep: float = 0) -> None:
        """Each control with its caption while more than *keep* seconds are left; one that does not fit is left
        out."""
        for widget, caption in widgets:
            if 0.6 + self.read(caption) > self.left() - keep:
                continue
            self.told.add(caption)
            self.say(caption)
            self.move(self.at(widget), 0.6)
            self.hold(self.read(caption))

    def page_caption(self, name: str, tooltip: str) -> str:
        tip = plain(tooltip)
        return f"{name}: {tip}" if tip else name

    def spread(self, pages: list) -> list:
        """As many pages as fit in the time left, evenly spread from the first to the last."""
        costs = [0.8 + self.read(self.page_caption(name, tip)) for _, _, name, tip, _ in pages]
        fits = max(1, min(len(pages), int(self.left() / (sum(costs) / len(costs)))))
        if fits >= len(pages):
            return pages
        return [pages[round(i * (len(pages) - 1) / max(1, fits - 1))] for i in range(fits)]

    # --- the tour -------------------------------------------------------------------------------------------
    def run(self) -> None:
        from bc250_core.appinfo import SUITE_MANUAL_URL

        title = self.card(self.name, ["A tour of the app", f"Version {self.version}"])
        self.overlay = title
        self.emit(title, round(2.5 * self.fps))
        self.overlay = None
        self.fade(title, self.frame(), 0.6)

        if self.entry.get("summary"):
            self.say(self.entry["summary"])
            self.hold(self.read(self.caption))
        logo = self.logo_label()
        if logo is not None:
            self.say(f"{self.name} {self.version}".strip() + ".")
            self.move(self.at(logo), 0.6)
            self.hold(1.8)
        pages = self.pages()
        self.point_out(self.controls(self.window, self.top_of_pages()),
                       self.left() * (1 - HEADER_SHARE) if pages else 0)

        shown = None
        for where, open_page, name, tooltip, page in self.spread(pages) if pages else []:
            caption = self.page_caption(name, tooltip)
            if 0.8 + self.read(caption) > self.left():
                continue
            self.say("")
            self.move(where(), 0.6)
            self.click(open_page)
            self.say(caption)
            self.hold(self.read(caption))
            shown = page
        self.point_out(self.controls(shown() if shown is not None else self.window))     # time to spare

        self.say("")
        self.hold(0.5)
        url = (SUITE_MANUAL_URL + chapter_of(self.key, self.name)).removeprefix("https://").rstrip("/")
        last = self.frame()
        end = self.card(self.name, ["Everything about the app is in the wiki:", url])
        self.fade(last, end, 0.8)
        self.emit(end, round(3.5 * self.fps))


def chapter_of(key: str, name: str) -> str:
    """The app's page in the wiki, relative to its home: docs/apps/<key>.md, else the page headed with its name."""
    docs = SUITE / "docs"
    if (docs / "apps" / f"{key}.md").is_file():
        return f"apps/{key}/"
    for page in sorted(docs.rglob("*.md")):
        if f"\n# {name}\n" in page.read_text(encoding="utf-8"):
            return page.relative_to(docs).with_suffix("").as_posix() + "/"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("app", help="its key in portal/apps.toml, or its folder under apps/")
    parser.add_argument("out", nargs="?", help="default: ~/Videos/bc250-<app>-tour-v<version>.mp4")
    parser.add_argument("--package", help="which program, for an app with two (compute, cores)")
    parser.add_argument("--seconds", type=float, default=SECONDS, help="the length of the video (default 40)")
    parser.add_argument("--music", type=Path, default=MUSIC, help="the track under the video (default: the suite's)")
    parser.add_argument("--no-music", action="store_true", help="a video without sound")
    parser.add_argument("--fps", type=int, default=30)
    tour_frames.suites.add_argument(parser)
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        print("ffmpeg is needed", file=sys.stderr)
        return 1
    music = None if args.no_music else args.music.resolve()
    if music is not None and not music.is_file():
        print(f"No music at {music} (--no-music for a video without sound)", file=sys.stderr)
        return 1
    folder, key, entry = find_app(args.app)
    package = find_package(folder, args.package)
    if args.out:
        out = Path(args.out).resolve()
    else:
        version = (folder / "VERSION").read_text(encoding="utf-8").strip() if (folder / "VERSION").is_file() else ""
        name = key if args.package is None else f"{key}-{package}"
        out = Path.home() / "Videos" / f"bc250-{name}-tour{f'-v{version}' if version else ''}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="app-tour-") as temp:
        home = Path(temp)
        tour_frames.prepare_home(home)
        (home / "tmp").mkdir()
        os.environ["TMPDIR"] = str(home / "tmp")     # the app's one-instance socket: not that of an app you have open
        refuse = home / "refuse"
        refuse.mkdir()
        for name in ("pkexec", "sudo", "run0"):
            stub = refuse / name
            stub.write_text(f'#!/bin/sh\necho "Refused in the tour: {name} $*" >&2\nexit 126\n', encoding="utf-8")
            stub.chmod(0o755)
        os.environ["PATH"] = f"{refuse}{os.pathsep}{os.environ.get('PATH', '')}"
        sys.path[:0] = [str(folder)]

        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication, QMainWindow

        def close_dialogs() -> None:
            dialog = QApplication.activeModalWidget()
            if dialog is not None:
                print(f"Closed a dialog: {dialog.windowTitle() or type(dialog).__name__}", file=sys.stderr)
                dialog.close()

        def record(app) -> int:
            """The app's exec(): record the tour instead of waiting for the user."""
            closer = QTimer()
            closer.timeout.connect(close_dialogs)
            closer.start(100)
            for _ in range(10):
                app.processEvents()
            windows = [w for w in app.topLevelWidgets() if w.isVisible()]
            if not windows:
                raise SystemExit("The app shows no window.")
            window = max(windows, key=lambda w: (isinstance(w, QMainWindow), w.width() * w.height()))
            silent = out if music is None else home / "silent.mp4"
            tour = AppTour(silent, args.fps, window, home, folder, key, entry, args.seconds)
            try:
                tour.run()
            finally:
                code = tour.finish()
            if code == 0 and music is not None:
                code = tour_frames.add_music(silent, music, out, tour.frames / tour.fps, FADE)
            raise Done(code)

        QApplication.exec = record
        sys.argv = [package]
        try:
            runpy.run_module(package, run_name="__main__", alter_sys=True)
        except Done as done:
            print(out if done.code == 0 else f"ffmpeg failed ({done.code})")
            return done.code
        except SystemExit as exc:
            if exc.code not in (None, 0):
                print(exc.code if isinstance(exc.code, str) else f"The app ended ({exc.code}).", file=sys.stderr)
                return 1
        print("The app ended before it showed its window.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # As portal_tour.py: os._exit skips the interpreter's shutdown, where Python destroys the Qt objects in no fixed
    # order, once the video is written and the temporary home removed.
    try:
        status = main()
    except SystemExit as exc:                       # argparse: --help, or a wrong argument; a wrong app
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
        status = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        import traceback
        traceback.print_exc()
        status = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
