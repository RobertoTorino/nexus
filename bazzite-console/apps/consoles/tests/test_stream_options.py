# SPDX-License-Identifier: AGPL-3.0-or-later
"""stream_options.py and options_dialog.py: the stream settings, what they ask the console for, how they are kept
with the console, and the dialog."""

from __future__ import annotations

from dataclasses import replace

from consoles_link import jobs
from consoles_link.consoles import ConsoleStore, RegisteredConsole
from consoles_link.options_dialog import StreamOptionsDialog
from consoles_link.stream_options import AUTO, StreamOptions, width
from consoles_link.target import Target

PS4 = RegisteredConsole("H1", "PS4-728", "192.168.1.20", Target.PS4_10, b"r" * 16, b"k" * 16, b"\x01" * 6)
PS5 = replace(PS4, host_id="H2", nickname="PS5-1", target=Target.PS5_1)


def test_defaults_are_the_presets():
    options = StreamOptions()
    assert (options.resolution, options.fps, options.bitrate, options.screen) == (AUTO, 60, AUTO, "fit")
    assert [options.height(ps5, kind) for ps5, kind in ((True, ""), (False, "PS4 Pro"), (False, "PS4"))] == \
        [1080, 1080, 720]
    assert (options.kbps(1080), options.kbps(720), options.kbps(360)) == (15000, 10000, 2000)
    assert [width(h) for h in (360, 540, 720, 1080)] == [640, 960, 1280, 1920]


def test_chosen_values_and_the_ps4_limit():
    options = StreamOptions(resolution=1080, fps=30, bitrate=8000)
    assert options.height(True) == 1080 and options.height(False, "PS4 Pro") == 1080
    assert options.height(False, "PS4") == 720                         # a PS4 that is not a Pro: 720p at most
    assert StreamOptions(resolution=540).height(False, "PS4") == 540
    assert options.kbps(1080) == 8000
    assert options.describe(True) == "1080p, 30 fps, 8 Mbit/s, fit"
    assert StreamOptions(audio_delay=80, low_latency=True, screen="fill").describe(False, "PS4") == \
        "720p (automatic), 60 fps, 10 Mbit/s (automatic), fill, sound 80 ms later, low latency"


def test_json_keeps_what_is_valid():
    options = StreamOptions(resolution=540, fps=30, bitrate=4000, audio_delay=120, low_latency=True, screen="stretch")
    assert StreamOptions.from_json(options.to_json()) == options
    assert StreamOptions.from_json(None) == StreamOptions()
    broken = {"resolution": 480, "fps": 144, "bitrate": 10, "audio_delay": -5, "low_latency": "yes", "screen": "4:3"}
    assert StreamOptions.from_json(broken) == StreamOptions()


def test_kept_with_the_console(tmp_path):
    store = ConsoleStore(tmp_path)
    store.put(replace(PS4, options=StreamOptions(resolution=540, screen="fill")))
    [loaded] = store.load()
    assert loaded.options == StreamOptions(resolution=540, screen="fill")
    # A file from before the settings: the defaults.
    data = PS4.to_json()
    del data["options"]
    assert RegisteredConsole.from_json(data).options == StreamOptions()


def test_the_stream_asks_for_the_settings():
    assert (jobs.stream_profile(PS5).width, jobs.stream_profile(PS5).height) == (1920, 1080)
    chosen = replace(PS5, options=StreamOptions(resolution=720, fps=30, bitrate=5000))
    profile = jobs.stream_profile(chosen)
    assert (profile.width, profile.height, profile.max_fps, profile.bitrate) == (1280, 720, 30, 5000)
    ps4 = replace(PS4, options=StreamOptions(resolution=1080))
    assert jobs.stream_profile(ps4, "PS4").height == 720 and jobs.stream_profile(ps4, "PS4 Pro").height == 1080


def test_dialog_shows_and_returns_the_settings(qapp):
    options = StreamOptions(resolution=540, fps=30, bitrate=4000, audio_delay=120, low_latency=True, screen="fill")
    dialog = StreamOptionsDialog(replace(PS4, options=options), "PS4-728")
    assert dialog.options() == options
    assert dialog.resolution.currentText() == "540p" and dialog.bitrate.text() == "4 Mbit/s"
    dialog.bitrate.setValue(0)
    assert dialog.bitrate.text().startswith("Automatic") and dialog.options().bitrate == AUTO
    dialog.show_options(StreamOptions())                               # Restore Defaults
    assert dialog.options() == StreamOptions()
    assert dialog.audio_delay.text() == "None"
    dialog.close()
