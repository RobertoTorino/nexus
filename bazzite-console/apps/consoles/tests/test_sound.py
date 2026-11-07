# SPDX-License-Identifier: AGPL-3.0-or-later
"""sound.py and sound_out.py: the buffer between the stream and the sound card (order, silence, dropping the oldest
when it piles up), the device the sink reads, and the player without an audio output (as on CI)."""

from __future__ import annotations

from PyQt6.QtCore import QIODevice
from PyQt6.QtMultimedia import QAudioDevice

from consoles_link import sound_out
from consoles_link.sound import SoundBuffer

TEN_MS = 480 * 4                        # 48 kHz stereo, 16 bits


def test_reads_in_order_and_whole_samples():
    buffer = SoundBuffer()
    buffer.push(bytes(range(8)))
    assert buffer.read(6) == bytes(range(4))                    # 6 rounds down to one stereo sample of 4 bytes
    assert buffer.read(100) == bytes(range(4, 8))
    assert buffer.buffered == 0


def test_empty_gives_silence_of_at_most_10_ms():
    buffer = SoundBuffer()
    assert buffer.read(100_000) == bytes(TEN_MS)
    assert buffer.read(8) == bytes(8) and buffer.silence_bytes == TEN_MS + 8


def test_piling_up_drops_the_oldest():
    buffer = SoundBuffer(max_ms=100, target_ms=40)
    for i in range(11):                                          # 110 ms: over the 100 ms
        buffer.push(bytes([i]) * TEN_MS)
    assert buffer.buffered == 4 * TEN_MS and buffer.dropped_bytes == 7 * TEN_MS
    assert buffer.read(TEN_MS) == bytes([7]) * TEN_MS            # the newest 40 ms are kept


def test_device_reads_the_buffer(qapp):
    buffer = SoundBuffer()
    device = sound_out.SoundDevice(buffer)
    assert device.open(QIODevice.OpenModeFlag.ReadOnly) and device.isSequential()
    buffer.push(b"\x01\x02\x03\x04")
    assert device.read(4) == b"\x01\x02\x03\x04"
    assert device.read(4) == bytes(4)                            # nothing left: silence


def test_player_without_an_audio_output(qapp, monkeypatch):
    monkeypatch.setattr(sound_out.QMediaDevices, "defaultAudioOutput", staticmethod(lambda: QAudioDevice()))
    player = sound_out.SoundPlayer()
    player.push(bytes(TEN_MS), 48000, 2)                         # the first push starts the sink (here: cannot)
    qapp.processEvents()
    assert player.error == "no audio output" and player.buffer is None
    player.push(bytes(TEN_MS), 48000, 2)                         # later sound is dropped, not queued
    player.stop()


def test_audio_delay_holds_the_sound_back():
    buffer = SoundBuffer(48000, 2, delay_ms=50)                 # 50 ms = 9600 bytes
    ten_ms = bytes(range(240)) * 8                              # 10 ms of 48 kHz stereo: 1920 bytes
    buffer.push(ten_ms * 4)                                     # 40 ms: not enough yet, silence
    assert buffer.read(1920) == bytes(1920) and buffer.buffered == 4 * 1920
    buffer.push(ten_ms)                                         # 50 ms: it plays, from the oldest
    assert buffer.read(1920) == ten_ms
    assert buffer.read(4 * 1920) == ten_ms * 4                  # all of it
    assert buffer.read(1920) == bytes(1920)                     # a gap: filling again from here
    buffer.push(ten_ms)
    assert buffer.read(1920) == bytes(1920)
    # The drop limits move up by the delay: 150 ms of sound is kept, 160 ms drops to the target of 90.
    full = SoundBuffer(48000, 2, delay_ms=50)
    full.push(ten_ms * 15)
    assert full.dropped_bytes == 0
    full.push(ten_ms)
    assert full.buffered == 9 * 1920


def test_player_takes_the_settings(qapp):
    player = sound_out.SoundPlayer(None, delay_ms=80, low_latency=True)
    assert (player.delay_ms, player.low_latency) == (80, True)
