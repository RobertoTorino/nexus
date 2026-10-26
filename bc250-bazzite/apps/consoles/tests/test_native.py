# SPDX-License-Identifier: AGPL-3.0-or-later
"""The native core (native/, Rust through PyO3) as Python sees it, against the vectors printed by the reference's own C
code (gkcrypt.c, ecdh.c and takion.c at commit c8bea2642d0e, built with OpenSSL on 12-10-2026), and the FEC against
frames recorded by the reference (fec_vectors.json), and the video decoder against clips and their pictures as the
system's FFmpeg decodes them (video_vectors.json; only when the core is built with it). The Rust tests (cargo test)
check the same vectors; these check the module the app imports.

The module is built from native/ (maturin build, then pip install the wheel); CI builds it before these tests. Without
it they are skipped, with the reason."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

core = pytest.importorskip("bc250_console_link_core", reason="the native core is not built: see native/pyproject.toml")

VECTORS = json.loads((Path(__file__).parent / "takion_vectors.json").read_text(encoding="utf-8"))
FEC = json.loads((Path(__file__).parent / "fec_vectors.json").read_text(encoding="utf-8"))["cases"]
h = bytes.fromhex


@pytest.mark.parametrize("v", VECTORS["gkcrypt"], ids=lambda v: f"index{v['index']}")
def test_gkcrypt(v):
    crypt = core.GkCrypt(v["index"], h(v["handshake_key"]), h(v["secret"]))
    assert (crypt.key_base, crypt.iv, crypt.key_gmac_base) == (h(v["key_base"]), h(v["iv"]), h(v["key_gmac_base"]))
    assert crypt.key_stream(0, 64) == h(v["stream_0"])
    assert crypt.key_stream(0xfff0, 48) == h(v["stream_fff0"])
    assert crypt.crypt(0x105, h(v["plain"])) == h(v["crypt_105"])
    assert crypt.crypt(0x105, h(v["crypt_105"])) == h(v["plain"])
    for pos, mac in v["gmacs"]:                         # in this order: the GMAC key moves on and comes back
        assert crypt.gmac(pos, h(v["gmac_msg"])) == h(mac), pos


@pytest.mark.parametrize("v", VECTORS["ecdh"], ids=lambda v: v["private"][:8])
def test_ecdh(v):
    ecdh = core.Ecdh(h(v["private"]))
    public, signature = ecdh.signed_public_key(h(v["handshake_key"]))
    assert (public, signature) == (h(v["public"]), h(v["signature"]))
    assert core.verify_signature(h(v["handshake_key"]), public, signature)
    assert not core.verify_signature(h(v["handshake_key"]), public, bytes(32))
    assert ecdh.derive_secret(h(v["remote_public"])) == h(v["secret"])


def test_ecdh_both_sides_agree_and_bad_keys():
    a, b = core.Ecdh(), core.Ecdh()
    assert len(a.public_key()) == 65 and a.public_key()[0] == 4
    assert a.derive_secret(b.public_key()) == b.derive_secret(a.public_key())
    with pytest.raises(ValueError):
        a.derive_secret(b"\x04" * 65)
    with pytest.raises(ValueError):
        core.Ecdh(bytes(32))


def test_packet_mac_and_verify():
    v = VECTORS["packet_mac"]
    crypt = core.GkCrypt(v["index"], h(v["handshake_key"]), h(v["secret"]))
    for case in v["packets"]:
        packet, mac, _old = core.packet_mac(crypt, h(case["packet"]), case["key_pos"])
        assert (packet, mac) == (h(case["with_mac"]), h(case["mac"]))
        assert core.verify_packet(crypt, core.KeyState(), packet) == case["key_pos"]
        tampered = packet[:1] + bytes([packet[1] ^ 1]) + packet[2:]
        with pytest.raises(ValueError, match="MacMismatch"):
            core.verify_packet(crypt, core.KeyState(), tampered)
    # Without crypto (before the key exchange) the MAC field is zeroed and every packet passes.
    plain, mac, _old = core.packet_mac(None, h(v["packets"][0]["with_mac"]), 0)
    assert mac == bytes(4) and core.verify_packet(None, core.KeyState(), plain) == 0


@pytest.mark.parametrize("case", VECTORS["av"], ids=lambda c: f"{c['parser']}-{c['packet'][:2]}")
def test_av_parse(case):
    version = {"v7": 7, "v9": 9, "v12": 12}[case["parser"]]
    parsed = core.parse_av(version, h(case["packet"]), core.KeyState())
    for key in ("packet_index", "frame_index", "nalu", "video", "haptics", "unit_index", "units_total", "units_fec",
                "codec", "word_at_0x18", "adaptive_stream_index", "byte_at_0x2c", "key_pos", "data_offset"):
        assert parsed[key] == case[key], key
    assert len(h(case["packet"])) - parsed["data_offset"] == case["data_size"]


def test_av_parse_refuses_short_and_unknown():
    with pytest.raises(ValueError, match="TooSmall"):
        core.parse_av(12, b"\x13" * 0x14, core.KeyState())
    with pytest.raises(ValueError, match="InvalidData"):
        core.parse_av(10, b"\x02" * 0x40, core.KeyState())


def test_congestion_and_key_state():
    v = VECTORS["congestion"]
    assert core.congestion_packet(v["word_0"], v["received"], v["lost"], v["key_pos"]) == h(v["packet"])
    state = core.KeyState()
    assert [state.request_pos(low) for low, _pos in VECTORS["key_state"]] == [pos for _low, pos in VECTORS["key_state"]]


def test_handshake_messages():
    tag_local, tag_remote = 0x11223344, 0xcafe
    init = core.init_packet(tag_local, tag_local)
    message = core.parse_message(init[1:], 0, core.KeyState())
    assert message["chunk_type"] == core.CHUNK_INIT and message["payload"][:4] == tag_local.to_bytes(4, "big")
    payload = (tag_remote.to_bytes(4, "big") + core.A_RWND.to_bytes(4, "big") + (0x64).to_bytes(2, "big") * 2
               + (7).to_bytes(4, "big") + b"\xab" * 32)
    ack = core.message_packet(tag_local, 0, core.CHUNK_INIT_ACK, 0, payload)
    parsed = core.parse_init_ack(core.parse_message(ack[1:], tag_local, core.KeyState())["payload"])
    assert parsed["tag"] == tag_remote and parsed["cookie"] == b"\xab" * 32
    with pytest.raises(ValueError):
        core.parse_init_ack(payload[:-1])
    cookie = core.cookie_packet(tag_remote, parsed["cookie"])
    assert core.parse_message(cookie[1:], tag_remote, core.KeyState())["chunk_type"] == core.CHUNK_COOKIE


def test_data_and_ack():
    packet = core.data_packet(5, 0x40, 1, 9, 2, b"protobuf")
    message = core.parse_message(packet[1:], 5, core.KeyState())
    assert core.parse_data(message["payload"]) == (9, 2, 0, b"protobuf")
    ack = core.data_ack_packet(5, 0x60, 9, core.A_RWND)
    assert core.parse_data_ack(core.parse_message(ack[1:], 5, core.KeyState())["payload"]) == (9, core.A_RWND)
    with pytest.raises(ValueError, match="TagMismatch"):
        core.parse_message(packet[1:], 6, core.KeyState())
    assert core.key_pos_advance(20) == 24


@pytest.mark.parametrize("name", sorted(VECTORS["v7_header"]))
def test_v7_header(name):
    v = VECTORS["v7_header"][name]
    header = core.v7_av_header(video=bool(v["video"]), nalu=bool(v["nalu"]), packet_index=v["packet_index"],
                               frame_index=v["frame_index"], unit_index=v["unit_index"], units_total=v["units_total"],
                               units_fec=v["units_fec"], codec=v["codec"], key_pos=v["key_pos"],
                               word_at_0x18=v["word_at_0x18"], adaptive_stream_index=v["adaptive_stream_index"])
    assert header == h(v["header"])


@pytest.mark.parametrize("v", FEC, ids=lambda v: f"k{v['k']}m{v['m']}-{'-'.join(map(str, v['erasures']))}")
def test_fec(v):
    k, m, size = v["k"], v["m"], v["unit_size"]
    frame = base64.b64decode(v["frame"])
    units = [frame[i * size:(i + 1) * size] for i in range(k + m)]
    damaged = b"".join(bytes([0x42]) * size if i in v["erasures"] else unit for i, unit in enumerate(units))
    assert core.fec_decode(damaged, size, k, m, v["erasures"]) == frame[:k * size]
    encoded = core.fec_encode(frame[:k * size], size, k, m)
    assert all(encoded[i * size:(i + 1) * size] == units[i] for i in range(k, k + m) if i not in v["erasures"])
    with pytest.raises(ValueError, match="TooManyErasures"):
        core.fec_decode(damaged, size, k, m, list(range(m + 1)))


@pytest.mark.skipif(not getattr(core, "DECODER", False), reason="the native core is built without the decoders")
def test_audio_decoder():
    v = json.loads((Path(__file__).parent / "audio_vectors.json").read_text(encoding="utf-8"))
    decoder = core.AudioDecoder(v["rate"], v["channels"], v["frame_size"])
    pcm = b"".join(decoder.decode(base64.b64decode(frame)) for frame in v["frames"])
    reference = base64.b64decode(v["pcm"])
    skip = v["pre_skip"] * v["channels"] * 2
    ours = pcm[skip:skip + len(reference)]
    pairs = zip(memoryview(ours).cast("h"), memoryview(reference).cast("h"))
    assert len(ours) == len(reference) and all(abs(a - b) <= 1 for a, b in pairs)
    assert decoder.decode(None) == bytes(480 * 2 * 2)               # a lost frame: 10 ms of silence
    with pytest.raises(ValueError):
        core.AudioDecoder(48000, 0, 480)


@pytest.mark.skipif(not getattr(core, "DECODER", False), reason="the native core is built without the video decoder")
@pytest.mark.parametrize("codec", ["h264", "hevc"])
def test_decoder(codec):
    clip = json.loads((Path(__file__).parent / "video_vectors.json").read_text(encoding="utf-8"))["clips"][codec]
    decoder = core.Decoder(codec, hw=False)
    assert not decoder.hw and decoder.hw_error is None
    pictures = hashlib.sha256()
    frames = 0
    for sample in clip["samples"]:
        for frame in decoder.decode(base64.b64decode(sample)):
            assert (frame["width"], frame["height"], frame["hw"]) == (clip["width"], clip["height"], False)
            image = decoder.image()
            assert (image["format"], image["width"], image["height"]) == ("yuv420p", clip["width"], clip["height"])
            assert image["colorspace"] == 2 and not image["full_range"]     # x264/x265 leave the matrix unset
            pictures.update(image["data"])
            frames += 1
    assert frames == clip["frames"] and pictures.hexdigest() == clip["sha256"]
    with pytest.raises(ValueError, match="codec"):
        core.Decoder("vp9")


ORIENTATION = json.loads((Path(__file__).parent / "orientation_vectors.json").read_text(encoding="utf-8"))


def test_orientation_tracker_matches_reference():
    """The tracker as the module gives it, against the reference's orientation.c (orientation_vectors.json)."""
    tracker = core.OrientationTracker()
    assert tracker.accel == (0.0, 1.0, 0.0) and abs(tracker.orientation[0]) < 1e-7
    for sample in ORIENTATION["samples"]:
        if sample["gyro"]:
            tracker.update(tuple(sample["data"]), tracker.accel, sample["timestamp"], accel_zero_applied=True)
        else:
            tracker.update(tracker.gyro, tuple(sample["data"]), sample["timestamp"])
        assert list(tracker.orientation) == pytest.approx(sample["orient"], rel=1e-6, abs=1e-9)
        assert list(tracker.accel) == pytest.approx(sample["state_accel"], rel=1e-6)
    zero = ORIENTATION["zero"]
    tracker = core.OrientationTracker()
    tracker.update((0, 0, 0), (0.3, 1.2, 0.1), 1000, accel_zero=tuple(zero["zero"]))
    tracker.update((0.5, 0, 0), (0.3, 1.2, 0.1), 5000, accel_zero=tuple(zero["zero"]))
    assert list(tracker.orientation) == pytest.approx(zero["orient"], rel=1e-6, abs=1e-9)
