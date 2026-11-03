# SPDX-License-Identifier: GPL-3.0-or-later
"""The synthesizer: every preset renders to its length with its peak at its volume, the sweeps, tones and the
lead-in do what they say, the settings round-trip, and the WAV is 16-bit mono at 44.1 kHz."""

import wave
from dataclasses import replace

from sound_lab import synth
from sound_lab.synth import PRESETS, RANGES, RATE, WAVES, Sound


def test_every_preset_renders_to_its_length_with_its_peak_at_its_volume():
    for name, sound in PRESETS.items():
        frames = synth.render(sound)
        assert len(frames) == int(sound.lead_ms / 1000 * RATE) + sound.tones * int(sound.length_ms / 1000 * RATE), name
        assert abs(max(abs(v) for v in frames) - sound.volume / 100) < 1e-9, name
        assert synth.clamp(sound) == sound, f"{name} is outside a slider's range"


def test_the_tick_is_the_demos_tick():
    """The default: a 1200 Hz sine, 50 ms, dying off with exp(-40 t), its peak at 80 %."""
    frames = synth.render(Sound())
    assert len(frames) == 2205
    assert frames[0] == 0.0 and frames[1] > 0                   # a sine starts at zero and rises
    half = frames[len(frames) // 2:]
    assert max(abs(v) for v in half) < 0.8 * 0.5                # well down by the middle


def test_the_lead_in_is_silence_then_the_sound():
    frames = synth.render(Sound(lead_ms=400))
    lead = int(0.4 * RATE)
    assert frames[:lead] == [0.0] * lead and max(abs(v) for v in frames[lead:]) > 0.7


def test_more_tones_follow_each_an_interval_higher():
    """Two tones a fifth apart: the second has about 1.5 times the zero crossings of the first."""
    sound = Sound(start_hz=880, end_hz=880, length_ms=100, decay=0, tones=2, interval=7)
    frames = synth.render(sound)
    count = int(0.1 * RATE)
    first, second = frames[:count], frames[count:]

    def crossings(samples):
        return sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    assert 1.4 < crossings(second) / crossings(first) < 1.6


def test_a_sweep_changes_the_pitch_over_the_tone():
    up = synth.render(Sound(start_hz=400, end_hz=1600, length_ms=200, decay=0))
    flat = synth.render(Sound(start_hz=400, end_hz=400, length_ms=200, decay=0))

    def crossings(samples):
        return sum(1 for a, b in zip(samples, samples[1:]) if (a < 0) != (b < 0))
    assert crossings(up[-1000:]) > 2 * crossings(flat[-1000:])


def test_every_waveform_renders_and_noise_has_no_phase():
    for name in WAVES:
        frames = synth.render(Sound(wave=name, length_ms=20))
        assert len(frames) == int(0.02 * RATE) and max(abs(v) for v in frames) > 0.79, name
    assert synth.render(Sound(wave="noise")) == synth.render(Sound(wave="noise"))     # repeatable


def test_zero_volume_or_zero_decay_still_render():
    assert synth.render(Sound(volume=0)) == [0.0] * 2205
    assert max(abs(v) for v in synth.render(Sound(decay=0))) > 0.79


def test_clamp_keeps_every_number_in_its_range_and_the_waveform_known():
    wild = Sound(wave="bell", start_hz=99999, end_hz=-5, length_ms=0, attack_ms=999, decay=-1, tones=9,
                 interval=100, noise=500, noise_decay=0, lead_ms=-3, volume=250)
    tame = synth.clamp(wild)
    assert tame.wave == "sine"
    for name, (least, most, _unit, _label) in RANGES.items():
        assert least <= getattr(tame, name) <= most, name
    assert tame.tones == 3 and tame.volume == 100 and tame.start_hz == 4000 and tame.end_hz == 50


def test_values_round_trip_through_strings_as_the_settings_keep_them():
    sound = replace(PRESETS["Blip"], noise=12)
    values = {key: str(value) for key, value in synth.to_values(sound).items()}
    assert synth.from_values(values) == sound
    assert synth.from_values({"start_hz": "abc", "wave": "saw", "bogus": 1}) == Sound(wave="saw")
    assert synth.from_values({}) == Sound()


def test_write_wav_is_16_bit_mono_at_44100(tmp_path):
    frames = synth.render(PRESETS["Blip"])
    synth.write_wav(tmp_path / "blip.wav", frames)
    with wave.open(str(tmp_path / "blip.wav"), "rb") as sound:
        params = sound.getparams()
        assert (params.nchannels, params.sampwidth, params.framerate, params.nframes) == (1, 2, RATE, len(frames))
    assert len(synth.encode([2.0, -2.0])) == 4                 # clipped, never an overflow
    assert len(synth.silence(0.5)) == RATE // 2
