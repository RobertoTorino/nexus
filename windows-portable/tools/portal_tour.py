#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""A video tour of the portal, for the wiki and YouTube: the real portal window from this checkout, driven by a
script and rendered frame by frame into an MP4 (H.264, 1920 x 1080, 30 fps), with music under it that fades out over
the last two seconds (the Nexus tools' sounds/the_quiet_engine_remix_3min.mp3, every suite's, made with generative AI
tools). The same tour as the BC250 Bazzite Suite's (bc250-bazzite/tools/portal_tour.py), on this suite's portal: the
window at the handheld's 1280 x 720, drawn at 150 % (owner, 02-11-2026: the Windows Portable Suite had no tour).

    python tools/portal_tour.py [OUT.mp4] [--music FILE | --no-music] [--wiki] [--fps 30] [--size 1080p|1440p|2160p]

--wiki also writes the copy on the wiki's Portal Tour page: docs/videos/portal-tour.mp4 (1280 x 720, smaller) and its
poster, docs/images/portal/portal-tour-poster.webp (the title card). --size 2160p renders the same tour at
3840 x 2160 for YouTube, which shows a 4K upload far sharper than a 1080p one (about four times the time).

It runs offscreen in a temporary home folder (the suite's folders under it, on Windows too: nothing of the handheld
it runs on is read, no user name, no Steam, no Xbox app, no operating mode): a few apps "installed" (their records),
one of them behind its pinned release so the update shows, no network, no sound and no controller. The pointer, the
clicks and the captions are drawn into the frames. Needs PyQt6 (the dev venv) and ffmpeg with libx264. The frames are
drawn by tools/tour_frames.py, which the BC250 suite's tour and tools/app_tour.py use too. Record it on the handheld
for the wiki and YouTube: elsewhere the window is the same, but what the suite reads (the battery, the chip) is
stood in for."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]         # the suite: windows-portable/
ROOT = SUITE.parent
sys.path.insert(0, str(ROOT / "tools"))             # tour_frames.py, the Nexus tools'

import tour_frames  # noqa: E402
from tour_frames import Recorder  # noqa: E402

INSTALLED = ("test", "pcsx2", "rpcs3", "shadps4", "bios")
BEHIND = "shadps4"                                  # installed from an older release: the dot and Update
MUSIC = tour_frames.MUSIC_DIR / "the_quiet_engine_remix_3min.mp3"
FADE = 2.0                                          # the music fades out over the video's last seconds
WIKI_VIDEO = SUITE / "docs" / "videos" / "portal-tour.mp4"
WIKI_POSTER = SUITE / "docs" / "images" / "portal" / "portal-tour-poster.webp"
WIKI_URL = "robertotorino.github.io/nexus/windows-portable-suite"
SCALE = 1.5                                         # the handheld's 1280 x 720 fills the 1920 x 1080 video
CATEGORY_HINTS = {
    "sustainable": "what the handheld is and how it runs: the test app, always installed.",
    "graphics": "the picture: the screen, the GPU, a TV on the dock.",
    "gaming": "the emulators, each with its manager: the games go into Steam.",
    "utilities": "the rest: the camera, the BIOS, files over the network.",
}


def prepare_home(home: Path) -> None:
    """The temporary home, and the suite's Windows folders in it: nothing of the user is read, on Windows too."""
    tour_frames.set_scale(SCALE)
    tour_frames.prepare_home(home)
    for var, sub in (("LOCALAPPDATA", "AppData/Local"), ("APPDATA", "AppData/Roaming"), ("USERPROFILE", "")):
        (home / sub).mkdir(parents=True, exist_ok=True)
        os.environ[var] = str(home / sub)
    sys.path[:0] = [str(SUITE / "portal")]


class Tour(Recorder):
    def __init__(self, out: Path, fps: int, home: Path):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtWidgets import QApplication

        from bc250_core import portable
        from bc250_core.app import create_app
        from bc250_core.gamepad import Gamepad
        from portable_portal import INFO, LOGO_PATH, MANIFEST, SUITE as SUITE_ID, state_dir
        from portable_portal import main_window as mw
        from portable_portal.intro import INTRO_MS
        from portable_portal.manifest import load
        from portable_portal.sources import Records, Sources

        self.home = home
        app = QApplication.instance() or create_app(INFO, [])
        for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
            QSettings.setPath(fmt, QSettings.Scope.UserScope, str(home / "AppData" / "Roaming"))
        portable.set_sound_on(SUITE_ID, True)      # the Sound row says On; nothing plays (the intro's player below)
        entries = load(MANIFEST)
        records = {}
        for entry in entries:
            if entry.key in INSTALLED:
                records[entry.key] = entry.tag
                if entry.key == BEHIND:
                    major, minor, _ = entry.version.split(".")
                    records[entry.key] = f"wp-{entry.key}-v{major}.{max(int(minor) - 1, 0)}.0"
        state_dir().mkdir(parents=True, exist_ok=True)
        (state_dir() / "installed.json").write_text(json.dumps(records), encoding="utf-8")
        # The detect paths are the handheld's (%LOCALAPPDATA%\...): here an app is installed when the tour says so.
        mw.is_installed = lambda entry: entry.key in INSTALLED

        def no_controller():
            raise OSError("no controller in the tour")

        window = mw.MainWindow(entries, Sources(state_dir() / "releases", download=None),
                               Records(state_dir() / "installed.json"), portal_check=None,
                               gamepad=Gamepad(source_factory=no_controller), battery=lambda: (82, False),
                               launch=lambda argv: None, terminal=lambda *args, **kwargs: None,
                               exit_dir=home / "exit", intro_ms=INTRO_MS, steam_here=lambda: True,
                               open_steam=lambda url: None, xbox_local=home / "no-xbox",
                               chip_parts=lambda: ["CPU 12% 48°", "GPU 7% 47°"], modes=lambda: None)
        window.setWindowTitle(INFO.display_name)
        window.intro.player = lambda wav: None     # the intro's sound: not here
        tour_frames.place(window)
        window.show()
        for _ in range(3):
            app.processEvents()
        super().__init__(out, fps, window, LOGO_PATH)

    # --- the tour -------------------------------------------------------------------------------------------
    def run(self) -> None:
        from portable_portal import __version__
        from portable_portal.manifest import CATEGORIES

        w = self.window
        title = self.card("Windows Portable Suite", ["A tour of the portal", f"Portal {__version__}"])
        self.overlay = title
        self.emit(title, round(3.5 * self.fps))
        self.overlay = None
        self.intro(title)

        self.say("The portal installs, updates, opens and removes every app of the suite on a Windows handheld.")
        self.hold(3.5)
        self.say("One page for the touch screen and the controller. The header: the suite, the date, the time and "
                 "the battery.")
        self.move(self.at(w.header, 0.5, 0.5))
        self.hold(3.5)
        self.say("The categories: LB and RB step through them, a tap picks one.")
        self.move(self.at(w.tabs.labels[w.tabs.current]), 0.6)
        self.hold(2.5)

        first = w.tiles["test"]
        self.say("Windows Portable Test checks the handheld. It is always installed, as the first tile on Sustainable.")
        self.move(self.at(first, 0.5, 0.4))
        self.click(lambda: first.setFocus())
        self.hold(3.5)
        self.say("The pane under the tiles: the app's name, its version and what it does. A opens it, or installs it.")
        self.move(self.at(w.app_pane, 0.3, 0.5), 0.6)
        self.hold(3.5)
        self.say("X opens the details: the release, where it is installed, and what the portal did last.")
        self.move(self.at(first, 0.5, 0.6), 0.6)
        self.click(lambda: (first.setFocus(), w.show_details()))
        self.hold(3.5)
        self.say("B goes back, everywhere.")
        self.click(w.on_back)
        self.hold(1.5)

        self.say("")
        for index, category in enumerate(w.tabs.keys[1:], 1):
            self.move(self.at(w.tabs.labels[category]), 0.7)
            self.click(lambda c=category: w.tabs.select(c))
            self.say(f"{CATEGORIES[category]}: {CATEGORY_HINTS.get(category, '')}")
            self.hold(3.8)
            behind = w.tiles.get(BEHIND)
            if category == "gaming" and behind is not None and behind.isVisible():
                self.say("An app with a newer release gets a dot, and its pane says Update: Y installs it.")
                self.move(self.at(behind, 0.5, 0.4), 0.6)
                self.click(lambda: behind.setFocus())
                self.hold(3.8)
        self.say("")
        self.move(self.at(w.tabs.labels[w.tabs.keys[0]]), 0.7)
        self.click(lambda: w.tabs.select(w.tabs.keys[0]))
        self.hold(0.6)

        self.say("The legend at the bottom is the row of actions: every action is a button, and a tap on an entry "
                 "does the same.")
        self.move(self.at(w.legend, 0.5, 0.5), 0.7)
        self.hold(4)
        self.say("RT opens Steam's library: the games the managers put there are played from Steam.")
        self.hold(3)

        self.say("Menu opens the Settings page: the wallpaper, its transparency, the sound; on the handheld also the "
                 "Xbox menu, the operating mode and the screen.")
        self.click(lambda: w.show_suite())
        self.hold(3.5)
        self.move(self.at(w.suite_pane.wallpaper, 0.3, 0.5), 0.6)
        self.say("Wallpaper: the suite's own picture, one of yours from its wallpaper folder, or none, for every app.")
        self.click(lambda: (w.suite_pane.wallpaper.setFocus(), w.next_wallpaper()))
        self.hold(2.5)
        self.click(w.next_wallpaper)
        self.hold(2.5)
        self.move(self.at(w.suite_pane.transparency, 0.3, 0.5), 0.6)
        self.say("Transparency: more of the background over the picture, so the cards stay readable.")
        for _ in range(3):
            self.click(lambda: (w.suite_pane.transparency.setFocus(), w.next_transparency()))
            self.hold(1.2)
        self.say("The look changes while you press, and every app of the suite takes it.")
        self.hold(2)
        self.move(self.at(w.suite_pane.sound, 0.3, 0.5), 0.6)
        self.say("Sound: the portal's intro, on or off.")
        self.hold(2.5)
        self.say("")
        self.click(w.on_back)
        self.hold(1)

        self.controller()

        self.caption = ""
        last = self.frame()
        end = self.card("Windows Portable Suite", ["Everything about each app is in the wiki:", WIKI_URL])
        self.fade(last, end, 0.8)
        self.emit(end, round(5 * self.fps))

    def intro(self, before) -> None:
        """The intro the portal opens with, frame by frame from the title card (the intro follows the video's
        frames, not the clock), ending with the focus on the first tile."""
        from portable_portal.intro import INTRO_MS

        w = self.window
        w.start()                                   # starts the intro's animation: stopped, stepped by hand
        intro = w.intro
        intro.animation.stop()
        pointer, self.pointer = self.pointer, (-100, -100)
        self.say("")
        intro._step(0.0)
        self.pump()
        self.fade(before, self.frame(), 0.8)
        frames = round(INTRO_MS / 1000 * self.fps)
        for i in range(1, frames + 1):
            intro._step(i / frames)
            self.pump()
            self.emit(self.frame())
        intro._done()
        self.pump()
        self.hold(0.8)
        self.pointer = pointer

    def controller(self) -> None:
        """The focus moved as the d-pad moves it, with the pointer away."""
        w = self.window
        pointer, self.pointer = self.pointer, (-100, -100)
        w.tiles["test"].setFocus()
        self.pump()
        self.say("The d-pad or the stick moves the amber focus between the tiles; A acts on the one it is on.")
        self.hold(1.2)
        for direction in ("right", "right", "left", "down", "up"):
            w.act(direction)
            self.hold(0.8)
        self.say("LB and RB change the category; View exits the portal.")
        for _ in range(2):
            w.act("next")
            self.hold(1.6)
        w.act("previous")
        w.act("previous")
        self.hold(0.8)
        self.say("Everything works the same by touch.")
        self.hold(2.5)
        self.pointer = pointer


def wiki_copy(video: Path) -> int:
    """The wiki's copy of *video*: 1280 x 720 (the handheld's own size) and about a third of the size, so the
    repository stays small, and the title card as its poster. ffmpeg's exit code."""
    WIKI_VIDEO.parent.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--music", type=Path, default=MUSIC, help="the track under the video (default: the Nexus tools')")
    parser.add_argument("--no-music", action="store_true", help="a video without sound")
    parser.add_argument("--wiki", action="store_true", help="also write the copy on the wiki's Portal Tour page")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--size", choices=tuple(tour_frames.SIZES), default="1080p",
                        help="the video's size: 1080p (the default), 1440p or 2160p (4K, for YouTube)")
    args = parser.parse_args()
    tour_frames.set_size(args.size)
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
    # after a video was complete.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(main())
