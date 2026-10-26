#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""A video tour of the portal, for the wiki and YouTube: the real portal window from this checkout, driven by a
script and rendered frame by frame into an MP4 (H.264, 1920 x 1080, 30 fps), with music under it that fades out over
the last two seconds (tools/sounds/the_quiet_engine_remix_3min.mp3, made with generative AI tools).

    python3 tools/portal_tour.py [OUT.mp4] [--music FILE | --no-music] [--wiki] [--fps 30]

--wiki also writes the copy on the wiki's Portal Tour page: docs/videos/portal-tour.mp4 (1280 x 720, smaller) and its
poster, docs/images/portal/portal-tour-poster.webp (the title card).

It runs offscreen in a temporary home folder: a few apps "installed" (their detect paths and records), one of them
behind its pinned release so the update notice shows, no network, and nothing from the machine it runs on (no user
or host names, no checkout path), no sound from the portal and no controller. The pointer, the clicks and the
captions are drawn into the frames. Needs PyQt6 (the dev venv) and ffmpeg with libx264.
The frames are drawn by tools/tour_frames.py, which tools/app_tour.py uses too."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tour_frames
from tour_frames import SCALE, SUITE, Recorder

INSTALLED = ("check", "gpu", "upscaler", "shadps4", "rpcs3", "cec", "package")
BEHIND = "shadps4"                                  # installed from an older release: the red dot and the notice
MUSIC = SUITE / "tools" / "sounds" / "the_quiet_engine_remix_3min.mp3"
FADE = 2.0                                          # the music fades out over the video's last seconds
WIKI_VIDEO = SUITE / "docs" / "videos" / "portal-tour.mp4"
WIKI_POSTER = SUITE / "docs" / "images" / "portal" / "portal-tour-poster.webp"


def prepare_home(home: Path) -> None:
    tour_frames.prepare_home(home)
    sys.path[:0] = [str(SUITE / "portal")]


class Tour(Recorder):
    def __init__(self, out: Path, fps: int, home: Path):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtWidgets import QApplication

        from bc250_core.app import create_app
        from bc250_portal import INFO, LOGO_PATH, MANIFEST, audio, state_dir
        from bc250_portal.gamepad import Gamepad
        from bc250_portal.manifest import load, load_checkout
        from bc250_portal.sources import Records, Sources

        self.home = home
        app = QApplication.instance() or create_app(INFO, [])
        for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            QSettings.setPath(fmt, QSettings.Scope.UserScope, str(home / ".config"))
        entries = load(MANIFEST)
        shown = entries + load_checkout(MANIFEST)
        records = {}
        for entry in entries:
            if entry.key in INSTALLED:
                for path in entry.detect:
                    target = Path(os.path.expanduser(os.path.expandvars(path)))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.touch()
                records[entry.key] = entry.tag
                if entry.key == BEHIND:
                    major, minor, _ = entry.version.split(".")
                    records[entry.key] = f"{entry.key}-v{major}.{max(int(minor) - 1, 0)}.0"
        state_dir().mkdir(parents=True, exist_ok=True)
        (state_dir() / "installed.json").write_text(json.dumps(records), encoding="utf-8")
        from bc250_portal.main_window import MainWindow

        class Silent(audio.Sounds):                 # the Sound pill as on a board with an output, but nothing plays
            def available(self) -> bool:
                return True

            def play(self, name: str) -> bool:
                return False

        def no_controller():
            raise OSError("no controller in the tour")

        window = MainWindow(shown, Sources(state_dir() / "releases", checkout=None, download=None),
                            Records(state_dir() / "installed.json"), desktop=home / "Desktop",
                            menu=home / ".local/share/applications", sounds=Silent(),
                            gamepad=Gamepad(source_factory=no_controller))
        window.setWindowTitle(INFO.display_name)
        tour_frames.place(window)
        window.show()
        for _ in range(3):
            app.processEvents()
        super().__init__(out, fps, window, LOGO_PATH)

    # --- the tour -------------------------------------------------------------------------------------------
    def run(self) -> None:
        from bc250_core.appinfo import SUITE_MANUAL_URL
        from bc250_portal import __version__
        from bc250_portal.main_window import CATEGORY_HINTS
        from bc250_portal.manifest import CATEGORIES

        w = self.window
        title = self.card("BC250 Bazzite Suite", ["A tour of the portal", f"Portal {__version__}"])
        self.overlay = title
        self.emit(title, round(3.5 * self.fps))
        self.overlay = None
        self.fade(title, self.frame(), 0.8)

        self.say("The portal installs, updates and starts every app of the suite for the AMD BC-250 on Bazzite.")
        self.hold(3.5)
        self.say("Its header: the portal's icon and name, and where the apps install from.")
        self.move(self.at(w.logo))
        self.hold(3)
        self.say("A click on the icon opens the wiki in the browser: everything about each app.")
        self.hold(1.2)
        self.click()                                # only the ring: the tour opens no browser
        self.hold(0.8)
        shown = self.frame()
        wiki = self.card("Wiki", [SUITE_MANUAL_URL.removeprefix("https://").rstrip("/")])
        self.fade(shown, wiki, 0.6)
        self.emit(wiki, round(2.8 * self.fps))
        self.fade(wiki, shown, 0.6)
        for pill, text in ((w.refresh_pill, "Refresh looks again at which apps are installed."),
                           (w.icons_box, "Icons on Desktop: one icon per app on the Desktop, or only the portal's."),
                           (w.theme_pill, "The theme switcher: one look for every app in the suite."),
                           (w.wallpaper_pill, "And a wallpaper of your own behind the portal.")):
            self.say(text)
            self.move(self.at(pill), 0.6)
            self.hold(2.6)

        self.say("An app with a newer release gets a red dot, and the notice above the tabs names it.")
        self.move(self.at(w.notice, 0.2, 0.5))
        self.hold(3.5)
        first = w.cards["check"]
        self.say("Bazzite Test checks the board. It is always installed, as the first tile on Sustainable.")
        self.move(self.at(first, 0.5, 0.3))
        self.hold(3.5)
        self.say("Every tile installs, opens, updates and uninstalls its app; the installer runs in a terminal.")
        self.move(self.at(first, 0.5, 0.92))
        self.hold(3.5)
        board = next((c for k, c in w.cards.items() if c.entry.changes_board and c.isVisible()), None)
        if board is not None:
            self.say("Apps that change how the board runs carry a mark, and the portal asks first. "
                     "All of them are software-only and can be undone.")
            self.move(self.at(board, 0.5, 0.4))
            self.hold(4)

        self.say("")
        for category, page in list(w.pages.items())[1:]:   # the last tab, Install all apps, is a button
            index = w.tabs.indexOf(page)
            self.move(self.tab_at(w.tabs.tabBar(), index), 0.7)
            self.click(lambda i=index: w.tabs.setCurrentIndex(i))
            self.say(f"{CATEGORIES[category]}: {CATEGORY_HINTS[category]}")
            self.hold(3.8)
        self.say("")
        self.move(self.tab_at(w.tabs.tabBar(), 0), 0.7)
        self.click(lambda: w.tabs.setCurrentIndex(0))
        self.hold(0.6)

        self.say("The Wallpaper pill: your own picture, the example, one used before, or none.")
        self.move(self.at(w.wallpaper_pill))
        self.click(lambda: self.open_menu())
        self.hold(2.5)
        example = next(a for a in self.popup.actions() if a.text() == "Example wallpaper")
        self.move(self.at_action(example), 0.6)
        self.click(lambda: (self.popup.close(), w.example_wallpaper()))
        self.popup = None
        self.say("It fills the window, under a veil of the theme's color so the text stays readable.")
        self.hold(3.5)
        self.say("")
        self.move(self.at(w.wallpaper_pill), 0.6)
        self.click(lambda: self.open_menu())
        slider = w.transparency_slider
        self.move(self.at_slider(slider, slider.value()), 0.7)
        self.say("Transparency sets that veil: more for a dark or busy picture, so the icons stand out.")
        self.hold(1)
        for target in (90, 25, 60):
            self.drag(slider, target, 1.6)
            self.hold(0.8)
        self.say("The window changes while you move it, and the portal remembers it.")
        self.hold(2)
        self.popup.close()
        self.popup = None
        self.pump()

        self.big_picture()

        self.say("Gunmetal, Silver or Warm: each app takes the theme the next time it starts.")
        self.move(self.at(w.theme_pill))
        self.click(w._next_theme)
        self.hold(1.5)
        last = self.frame()
        for name in ("silver", "warm"):
            still = self.still(name)
            self.fade(last, still, 0.5)
            self.emit(still, round(2.2 * self.fps))
            last = still
        self.caption = ""
        end = self.card("BC250 Bazzite Suite", ["Everything about each app is in the wiki:",
                                               SUITE_MANUAL_URL.removeprefix("https://").rstrip("/")])
        self.fade(last, end, 0.8)
        self.emit(end, round(5 * self.fps))

    def big_picture(self) -> None:
        """Suite Big Picture Mode: in by the Suite mode pill, its intro, the focus moved as a controller moves it,
        and back to the desktop."""
        from bc250_portal.bigpicture import INTRO_MS

        w = self.window
        self.say("Suite mode switches to Big Picture Mode: fullscreen with large icons, for a TV and a controller.")
        self.move(self.at(w.mode_pill))
        self.hold(3.5)
        self.click(w.enter_big_picture)
        intro = w.intro
        intro.animation.stop()                      # the intro follows the video's frames, not the clock
        pointer, self.pointer = self.pointer, (-100, -100)
        self.say("")
        frames = round(INTRO_MS / 1000 * self.fps)
        for i in range(1, frames + 1):
            intro._step(i / frames)
            self.pump()
            self.emit(self.frame())
        intro._done()
        self.pump()
        self.say("The d-pad, the stick or the arrow keys move the focus; A or Enter opens the app.")
        self.hold(1.2)
        for direction in ("right", "right", "right", "right", "left", "left"):     # the top row: above the captions
            w.big.move_focus(direction)
            self.hold(0.7)
        self.hold(1)
        self.say("LB and RB, or Page Up and Page Down, change the category.")
        for _ in range(2):
            w.big.change_category(1)
            self.hold(1.8)
        w.big.change_category(-2)
        self.hold(0.6)
        self.say("Y or F11 goes back to Suite Desktop Mode, and the portal opens in the mode it was last in.")
        self.hold(3.5)
        last = self.frame()
        w.leave_big_picture()
        self.pointer = pointer
        self.pump()
        self.fade(last, self.frame(), 0.5)
        self.hold(0.5)

    def open_menu(self) -> None:
        self.popup = self.window.wallpaper_menu()
        pill = self.window.wallpaper_pill
        self.popup.popup(pill.mapToGlobal(pill.rect().bottomLeft()))
        self.pump()

    def at_action(self, action) -> tuple[float, float]:
        rect = self.popup.actionGeometry(action)
        top_left = self.popup.pos() - self.window.pos()
        return (top_left.x() + rect.center().x()) * SCALE, (top_left.y() + rect.center().y()) * SCALE

    def at_slider(self, slider, value: int) -> tuple[float, float]:
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QStyle, QStyleOptionSlider
        option = QStyleOptionSlider()
        slider.initStyleOption(option)
        option.sliderPosition = value
        handle = slider.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                               QStyle.SubControl.SC_SliderHandle, slider)
        point = slider.mapToGlobal(handle.center()) - self.window.pos() + QPoint(0, 0)
        return point.x() * SCALE, point.y() * SCALE

    def drag(self, slider, target: int, seconds: float) -> None:
        start, frames = slider.value(), max(1, round(seconds * self.fps))
        for i in range(1, frames + 1):
            t = i / frames
            value = round(start + (target - start) * t * t * (3 - 2 * t))
            slider.setValue(value)
            self.pointer = self.at_slider(slider, value)
            self.pump()
            self.emit(self.frame())

    def still(self, theme: str):
        """The portal in another theme: a fresh process (the theme is read at start) renders one frame."""
        from PyQt6.QtGui import QImage
        out = self.home / f"still-{theme}.png"
        subprocess.run([sys.executable, __file__, "--still", theme, str(out)], check=True)
        return QImage(str(out)).convertToFormat(QImage.Format.Format_RGB888)


def render_still(theme: str, out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="portal-tour-") as folder:
        home = Path(folder)
        prepare_home(home)
        import importlib

        import bc250_core.theme
        bc250_core.theme.save_theme_name(theme)
        importlib.reload(bc250_core.theme)              # the theme is read when the module is imported
        tour = Tour(Path(os.devnull), 1, home)
        tour.ffmpeg.kill()
        tour.window.example_wallpaper()
        tour.say({"silver": "Silver", "warm": "Warm"}.get(theme, theme))
        tour.overlay = None
        tour.pointer = (-100, -100)
        tour.pump()
        tour.frame().save(str(out))


def wiki_copy(video: Path) -> int:
    """The wiki's copy of *video*: 1280 x 720 and about a third of the size, so the repository stays small, and the
    title card as its poster. ffmpeg's exit code."""
    WIKI_POSTER.parent.mkdir(parents=True, exist_ok=True)
    code = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vf", "scale=1280:720:flags=lanczos",
         "-c:v", "libx264", "-preset", "slow", "-crf", "26", "-tune", "stillimage", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(WIKI_VIDEO)]).returncode
    return code or subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-ss", "1", "-i", str(video), "-frames:v", "1",
         "-vf", "scale=1280:720:flags=lanczos", "-c:v", "libwebp", "-quality", "85", str(WIKI_POSTER)]).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", nargs="?", default="portal-tour.mp4")
    parser.add_argument("--music", type=Path, default=MUSIC, help="the track under the video (default: the suite's)")
    parser.add_argument("--no-music", action="store_true", help="a video without sound")
    parser.add_argument("--wiki", action="store_true", help="also write the copy on the wiki's Portal Tour page")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--still", nargs=2, metavar=("THEME", "PNG"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.still:
        render_still(args.still[0], Path(args.still[1]))
        return 0
    if not shutil.which("ffmpeg"):
        print("ffmpeg is needed", file=sys.stderr)
        return 1
    music = None if args.no_music else args.music.resolve()
    if music is not None and not music.is_file():
        print(f"No music at {music} (--no-music for a video without sound)", file=sys.stderr)
        return 1
    out = Path(args.out).resolve()
    with tempfile.TemporaryDirectory(prefix="portal-tour-") as folder:
        home = Path(folder)
        prepare_home(home)
        silent = out if music is None else home / "silent.mp4"
        tour = Tour(silent, args.fps, home)
        try:
            tour.run()
        finally:
            code = tour.finish()
        if code == 0 and music is not None:
            code = tour_frames.add_music(silent, music, out, tour.frames / tour.fps, FADE)
    if code == 0 and args.wiki:
        code = wiki_copy(out)
        if code == 0:
            print(WIKI_VIDEO.relative_to(SUITE).as_posix(), WIKI_POSTER.relative_to(SUITE).as_posix())
    print(out if code == 0 else f"ffmpeg failed ({code})")
    return code


if __name__ == "__main__":
    # The video is written and the temporary home removed when main() returns. os._exit skips the interpreter's
    # shutdown, where Python destroys the Qt objects in no fixed order: that crashed now and then (exit code 139)
    # after a complete recording.
    try:
        status = main()
    except SystemExit as exc:                       # argparse: --help, or a wrong argument
        status = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        import traceback
        traceback.print_exc()
        status = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(status)
