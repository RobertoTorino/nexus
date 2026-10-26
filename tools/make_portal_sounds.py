#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthesise the portal's two sounds into portal/bc250_portal/sounds/, from nothing but arithmetic (the files are
original work; replace them with any WAV of the same name to change the sound):

    python3 tools/make_portal_sounds.py            # write swoosh.wav and bigpicture.wav

swoosh.wav        the start-up swoosh: band-passed noise whose center rises and falls, about 0.9 s.
bigpicture.wav    the Suite Big Picture Mode intro: a low thump, a rising sweep and a bell arpeggio, about 3 s."""

from __future__ import annotations

import math
import random
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "portal" / "bc250_portal" / "sounds"
RATE = 44100
PEAK = 0.8                       # of full scale: no clipping on any device


def _smooth(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def swoosh() -> list[tuple[float, float]]:
    """A low, soft swoosh: noise through a band-pass whose center rises from 70 Hz to about 900 Hz and falls again,
    then a low-pass, so there is little above 2 kHz; under it a sine sliding down from 140 to 70 Hz, for the weight (low
    enough to be bass, high enough for a laptop or a handheld speaker)."""
    rng = random.Random(250)
    seconds = 1.0
    low = band = 0.0
    smooth = 0.0
    phase = 0.0
    frames = []
    for n in range(int(seconds * RATE)):
        t = n / RATE / seconds
        centre = 70 * (13 ** math.sin(math.pi * t ** 0.8))              # 70 Hz up to 900 Hz and back
        f = 2 * math.sin(math.pi * centre / RATE)
        q = 0.45
        noise = rng.uniform(-1, 1)
        low += f * band
        high = noise - low - q * band
        band += f * high
        smooth += (1 - math.exp(-2 * math.pi * 1400 / RATE)) * (band - smooth)     # nothing bright
        envelope = math.sin(math.pi * t) ** 1.4 * (1 - 0.2 * t)
        phase += 2 * math.pi * (140 - 70 * _smooth(t)) / RATE
        weight = math.sin(phase) * math.sin(math.pi * min(1.0, t * 1.15)) ** 2 * 0.9
        value = smooth * envelope * 0.9 + weight * 0.55
        pan = _smooth(t)
        frames.append((value * (1 - 0.5 * pan), value * (0.5 + 0.5 * pan)))
    return frames


def _bell(frames: list[list[float]], start: float, hz: float, length: float, gain: float, pan: float) -> None:
    """A small FM bell: a sine whose own sine decays quicker than its volume."""
    first = int(start * RATE)
    for n in range(int(length * RATE)):
        if first + n >= len(frames):
            break
        t = n / RATE
        index = 2.5 * math.exp(-t * 7)
        value = math.sin(2 * math.pi * hz * t + index * math.sin(2 * math.pi * hz * 3.5 * t))
        value *= gain * math.exp(-t * 3.2) * min(1.0, t * 400)
        frames[first + n][0] += value * (1 - pan)
        frames[first + n][1] += value * pan


def big_picture() -> list[tuple[float, float]]:
    seconds = 3.2                                   # the intro lasts three seconds (owner, 26-10-2026)
    count = int(seconds * RATE)
    frames = [[0.0, 0.0] for _ in range(count)]
    rng = random.Random(1010)
    phase = [0.0, 0.0, 0.0]
    low = 0.0
    for n in range(count):
        t = n / RATE
        # The thump: a sine falling from 110 Hz to 40 Hz in the first 0.35 s.
        thump = math.sin(2 * math.pi * (40 * t + 70 * (1 - math.exp(-t * 9)) / 9)) * math.exp(-t * 5) * 0.9
        # The sweep: three detuned saws rising from 80 Hz to 1.2 kHz over 1.2 s, through a rising low-pass.
        rise = _smooth(t / 1.2)
        base = 80 * (15 ** rise)
        saw = 0.0
        for i, detune in enumerate((0.994, 1.0, 1.007)):
            phase[i] = (phase[i] + base * detune / RATE) % 1
            saw += (2 * phase[i] - 1) / 3
        cutoff = 300 + 5200 * rise
        low += (1 - math.exp(-2 * math.pi * cutoff / RATE)) * (saw - low)
        sweep = low * 0.5 * _smooth(t / 0.4) * (1 - _smooth((t - 1.2) / 0.5))
        # A thin shimmer of noise riding the sweep.
        shimmer = rng.uniform(-1, 1) * 0.05 * rise * (1 - _smooth((t - 1.2) / 0.4))
        value = thump + sweep + shimmer
        frames[n][0] += value
        frames[n][1] += value
    # The arpeggio lands when the sweep ends: A minor 9 going up, spread across the stereo field.
    for i, (hz, pan) in enumerate(((440.0, 0.3), (659.3, 0.5), (880.0, 0.7), (1318.5, 0.4), (1760.0, 0.6))):
        _bell(frames, 1.05 + 0.09 * i, hz, 2.0, 0.16, pan)
    # A short echo, so the end is not dry.
    delay = int(0.21 * RATE)
    for n in range(delay, count):
        frames[n][0] += frames[n - delay][1] * 0.28
        frames[n][1] += frames[n - delay][0] * 0.28
    fade = int(0.6 * RATE)                          # a long fade: the bells die away instead of being cut
    for n in range(fade):
        frames[count - 1 - n][0] *= n / fade
        frames[count - 1 - n][1] *= n / fade
    return [(left, right) for left, right in frames]


def _normalise(frames: list[tuple[float, float]]) -> list[tuple[float, float]]:
    top = max(max(abs(left), abs(right)) for left, right in frames) or 1.0
    return [(left * PEAK / top, right * PEAK / top) for left, right in frames]


def encode(frames: list[tuple[float, float]]) -> bytes:
    return b"".join(struct.pack("<hh", int(left * 32767), int(right * 32767)) for left, right in _normalise(frames))


def write(path: Path, frames: list[tuple[float, float]]) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(encode(frames))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in (("swoosh.wav", swoosh), ("bigpicture.wav", big_picture)):
        path = OUT / name
        frames = make()
        write(path, frames)
        print(f"wrote {path.relative_to(ROOT)} ({len(frames) / RATE:.2f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
