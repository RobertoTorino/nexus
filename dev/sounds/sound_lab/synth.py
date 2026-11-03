# SPDX-License-Identifier: GPL-3.0-or-later
"""The sound: a short effect from a handful of numbers (the window's sliders), rendered from arithmetic alone at
44.1 kHz, 16-bit mono. One tone of a waveform whose pitch slides from its start to its end, with an attack, an
exponential decay and a burst of noise over it; a further tone an interval higher for each tone asked (a blip);
silence before it when asked. The presets are starting points: the ticks and clicks a menu makes while one moves
through it."""

from __future__ import annotations

import math
import random
import struct
import wave
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

RATE = 44100
WAVES = ("sine", "triangle", "square", "saw", "noise")
FILTER = 0.35                           # the noise waveform's one-pole low-pass: takes the hiss off a click


@dataclass(frozen=True)
class Sound:
    """The numbers of one sound; every field but the waveform is a slider of the window (RANGES)."""

    wave: str = "sine"
    start_hz: int = 1200                # the pitch at the start of each tone
    end_hz: int = 1200                  # and at its end: a sweep when they differ
    length_ms: int = 50                 # one tone
    attack_ms: int = 1                  # the rise to full volume: longer is softer, 0 is a hard edge
    decay: int = 40                     # per second: the volume is down to a third after 1/decay s
    tones: int = 1                      # each further tone comes after the one before, the interval higher
    interval: int = 7                   # semitones between the tones (7: a fifth; negative: downward)
    noise: int = 0                      # percent of noise mixed over the tone, with its own decay
    noise_decay: int = 150
    lead_ms: int = 0                    # silence before the sound (see the window's explanation)
    volume: int = 80                    # percent of full scale: the peak

    def seconds(self) -> float:
        return self.lead_ms / 1000 + self.tones * self.length_ms / 1000


# field: (least, most, unit, label), in the order of the window's sliders
RANGES: dict[str, tuple[int, int, str, str]] = {
    "start_hz": (50, 4000, "Hz", "Pitch at the start"),
    "end_hz": (50, 4000, "Hz", "Pitch at the end"),
    "length_ms": (5, 500, "ms", "Length of a tone"),
    "attack_ms": (0, 50, "ms", "Attack"),
    "decay": (0, 200, "/s", "Decay"),
    "tones": (1, 3, "", "Tones"),
    "interval": (-12, 12, "semitones", "Interval between tones"),
    "noise": (0, 100, "%", "Noise"),
    "noise_decay": (10, 500, "/s", "Noise decay"),
    "lead_ms": (0, 1000, "ms", "Silence before"),
    "volume": (0, 100, "%", "Volume"),
}

PRESETS: dict[str, Sound] = {
    "Tick": Sound(),
    "High tick": Sound(start_hz=2400, end_hz=2400, length_ms=30, decay=80),
    "Blip": Sound(start_hz=880, end_hz=880, length_ms=45, decay=30, tones=2),
    "Thock": Sound(start_hz=220, end_hz=220, length_ms=70, decay=35, noise=50),
    "Click": Sound(wave="noise", length_ms=20, decay=120),
    "Select": Sound(start_hz=600, end_hz=1800, length_ms=120, decay=25),
    "Back": Sound(start_hz=1400, end_hz=500, length_ms=120, decay=25),
    "Error": Sound(wave="square", start_hz=220, end_hz=200, length_ms=140, attack_ms=5, decay=15, tones=2,
                   interval=-2),
    "Tick after silence": Sound(lead_ms=400),
}


def clamp(sound: Sound) -> Sound:
    """*sound* with every number inside its slider's range and a known waveform (settings written by another
    version, or by hand)."""
    values = {name: min(most, max(least, int(getattr(sound, name)))) for name, (least, most, _u, _l) in RANGES.items()}
    return replace(sound, wave=sound.wave if sound.wave in WAVES else WAVES[0], **values)


def from_values(values: dict[str, object]) -> Sound:
    """A Sound from strings or numbers by field name (the settings); a missing or unreadable field keeps the
    default."""
    kwargs: dict[str, object] = {}
    for field in fields(Sound):
        value = values.get(field.name)
        if value is None:
            continue
        try:
            kwargs[field.name] = str(value) if field.type == "str" else int(value)
        except (TypeError, ValueError):
            continue
    return clamp(Sound(**kwargs))


def to_values(sound: Sound) -> dict[str, object]:
    return asdict(sound)


def _oscillator(wave_name: str, phase: float) -> float:
    """One sample of the waveform at *phase* (0 to 1), from -1 to 1."""
    if wave_name == "triangle":
        return 4 * abs(phase - 0.5) - 1
    if wave_name == "square":
        return 1.0 if phase < 0.5 else -1.0
    if wave_name == "saw":
        return 2 * phase - 1
    return math.sin(2 * math.pi * phase)


def render(sound: Sound) -> list[float]:
    """The sound's samples, -1 to 1, the peak at its volume."""
    sound = clamp(sound)
    rng = random.Random(7)                              # the same noise every time: a saved sound is repeatable
    out = [0.0] * int(sound.lead_ms / 1000 * RATE)
    count = int(sound.length_ms / 1000 * RATE)
    for index in range(sound.tones):
        ratio = 2 ** (sound.interval * index / 12)
        phase, low = 0.0, 0.0
        for n in range(count):
            t = n / RATE
            hz = (sound.start_hz + (sound.end_hz - sound.start_hz) * n / max(1, count - 1)) * ratio
            phase = (phase + hz / RATE) % 1
            attack = min(1.0, t * 1000 / sound.attack_ms) if sound.attack_ms else 1.0
            if sound.wave == "noise":
                low += FILTER * (rng.uniform(-1, 1) - low)
                value = low
            else:
                value = _oscillator(sound.wave, phase)
            value *= math.exp(-sound.decay * t) * attack
            if sound.noise:
                value += rng.uniform(-1, 1) * sound.noise / 100 * math.exp(-sound.noise_decay * t) * attack
            out.append(value)
    top = max((abs(v) for v in out), default=0.0)
    if not top or not sound.volume:
        return [0.0] * len(out)
    gain = sound.volume / 100 / top
    return [v * gain for v in out]


def encode(frames: list[float]) -> bytes:
    return b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767)) for v in frames)


def write_wav(path: Path, frames: list[float]) -> None:
    """*frames* as a 16-bit mono WAV at RATE."""
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(encode(frames))


def silence(seconds: float = 1.0) -> list[float]:
    return [0.0] * int(seconds * RATE)


__all__ = ["PRESETS", "RANGES", "RATE", "WAVES", "Sound", "clamp", "encode", "from_values", "render", "silence",
           "to_values", "write_wav"]
