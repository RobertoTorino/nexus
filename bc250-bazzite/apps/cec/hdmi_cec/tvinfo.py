# SPDX-License-Identifier: GPL-3.0-or-later
"""TV info: what the TV tells about itself over CEC. Only questions (Get CEC Version, Give OSD Name, …): nothing on
the TV changes. Each answer becomes one row of the TV Info window.

TVs differ: a CEC 1.4 TV refuses the CEC 2.0 questions, a CEC 2.0 TV answers them, and the rows show what each one
says. The 2.0 answers are decoded from cec-ctl's names for them (`cec-ctl --help-all`)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import cec
from .runner import Result

_REPLY_FIELD = re.compile(r"^\t(?P<key>[a-z][a-z-]*):\s*(?P<value>.+?)\s*$")
_CODE = re.compile(r"\s*\(0x[0-9a-f]+\)$")
_WORD = re.compile(r"[a-z][a-z0-9-]*")

# CEC vendor ids (IEEE OUIs) of common TVs and audio systems.
VENDORS = {
    0x0000F0: "Samsung", 0x00E091: "LG", 0x080046: "Sony", 0x00903E: "Philips", 0x008045: "Panasonic",
    0x000039: "Toshiba", 0x08001F: "Sharp", 0x00A0DE: "Yamaha", 0x0009B0: "Onkyo", 0x0005CD: "Denon",
    0x001582: "Pulse-Eight",
}


@dataclass(frozen=True)
class Reply:
    state: str                                      # "answer", "unsupported", "no reply", "no answer"
    fields: dict[str, str] = field(default_factory=dict)
    words: frozenset[str] = frozenset()             # every name in the reply's values: "tv", "sink-has-arc-tx", …

    def get(self, key: str) -> str:
        return _CODE.sub("", self.fields.get(key, ""))

    def number(self, key: str) -> int | None:
        value = self.get(key)
        return int(value) if value.isdigit() else None


def parse_reply(text: str) -> Reply:
    """cec-ctl's output for one question: the fields of the reply, or why there is none."""
    if not cec.acked(text):
        return Reply("no answer")
    if "Feature Abort" in text:
        return Reply("unsupported")
    _head, received, tail = text.partition("Received from")
    if not received:
        return Reply("no reply")
    fields: dict[str, str] = {}
    words: set[str] = set()
    for line in tail.splitlines():
        match = _REPLY_FIELD.match(line)
        if match:
            fields.setdefault(match["key"], match["value"])
            words.update(_WORD.findall(match["value"]))
    return Reply("answer", fields, frozenset(words))


def vendor_name(vendor: str) -> str:
    """ "0x6d746b, 7173227" -> the vendor's name, or the id as three letters when they spell something ("mtk")."""
    try:
        number = int(vendor.split(",")[0], 16)
    except ValueError:
        return vendor
    if number in VENDORS:
        return f"{VENDORS[number]} (0x{number:06x})"
    letters = number.to_bytes(3, "big")
    if letters.isalpha():
        return f'0x{number:06x} = "{letters.decode()}"'
    return f"0x{number:06x}"


def _version(text: str) -> str:
    """ "version-1-4" -> "1.4" """
    return text.removeprefix("version-").replace("-", ".")


QUESTIONS = (
    # key, label, cec-ctl arguments after "--to <tv>"
    ("version", "CEC version", ["--get-cec-version"]),
    ("power", "Power status", ["--give-device-power-status"]),
    ("name", "Its name and type", ["--give-osd-name"]),
    ("address", "", ["--give-physical-addr"]),
    ("vendor", "Vendor ID", ["--give-device-vendor-id"]),
    ("language", "Menu language", ["--get-menu-language"]),
    ("features", "CEC 2.0 feature list", ["--give-features"]),
    ("audio", "Volume and mute status", ["--give-audio-status"]),
)


def ask(run: Callable[[list[str]], Result], device: str) -> dict[str, Reply]:
    def question(to: int, *args: str) -> Reply:
        return parse_reply(run([cec.CEC_CTL, "-d", device, "-s", "--to", str(to), *args]).out)

    replies = {key: question(cec.TV, *args) for key, _label, args in QUESTIONS}
    tv_address = replies["address"].get("phys-addr") or "0.0.0.0"
    replies["latency"] = question(cec.BROADCAST, "--request-current-latency", f"phys-addr={tv_address}")
    replies["receiver"] = parse_reply(run([cec.CEC_CTL, *cec.poll(device, cec.AUDIO_SYSTEM)]).out)
    if replies["receiver"].state != "no answer":        # an AV receiver or soundbar took the poll: who is it?
        replies["receiver name"] = question(cec.AUDIO_SYSTEM, "--give-osd-name")
        replies["receiver audio"] = question(cec.AUDIO_SYSTEM, "--give-audio-status")
    return replies


LANGUAGES = {"eng": "English", "dut": "Dutch", "nld": "Dutch", "ger": "German", "deu": "German",
             "fre": "French", "fra": "French", "spa": "Spanish", "ita": "Italian"}


# The CEC 2.0 feature list (Report Features), as cec-ctl names its flags.
FEATURES = (
    ("sink-has-arc-tx", "sends its sound to a receiver (ARC)"),
    ("source-has-arc-rx", "takes the TV's sound (ARC)"),
    ("has-set-audio-volume-level", "takes an exact volume"),
    ("has-set-audio-rate", "changes the audio speed"),
    ("has-deck-control", "deck control"),
    ("has-set-osd-string", "shows messages from devices"),
    ("has-record-tv-screen", "records what the TV shows"),
)
DEVICE_TYPES = (("tv", "TV"), ("record", "recorder"), ("tuner", "tuner"), ("playback", "player"),
                ("audiosystem", "audio system"), ("switch", "switch"))


def features(reply: Reply) -> str:
    """ "CEC 2.0; TV; remote profile 1; sends its sound to a receiver (ARC)" from Report Features."""
    words = reply.words
    parts = [f"CEC {_version(reply.get('cec-version'))}" if reply.get("cec-version") else ""]
    parts.append(", ".join(text for word, text in DEVICE_TYPES if word in words))
    parts += [f"remote profile {n}" for n in "1234" if f"tv-profile-{n}" in words]
    parts += [text for word, text in FEATURES if word in words]
    return "; ".join(p for p in parts if p)


def audio(reply: Reply) -> str:
    """ "volume 30, not muted" from Report Audio Status (the volume is 0-100; 127 is unknown)."""
    volume = reply.number("aud-vol-status")
    mute = reply.get("aud-mute-status")
    parts = [f"volume {volume}" if volume is not None and volume <= 100 else "volume unknown",
             {"on": "muted", "off": "not muted"}.get(mute, "")]
    return ", ".join(p for p in parts if p)


def _ms(value: int | None) -> str:
    """CEC latency values are milliseconds / 2 + 1 (1-251)."""
    return f"{(value - 1) * 2} ms" if value is not None and 1 <= value <= 251 else "unknown"


def latency(reply: Reply) -> str:
    """ "picture 20 ms, low-latency mode off, sound 40 ms" from Report Current Latency."""
    parts = [f"picture {_ms(reply.number('video-latency'))}"]
    if reply.get("low-latency-mode"):
        parts.append(f"low-latency mode {reply.get('low-latency-mode')}")
    compensated = reply.get("audio-out-compensated")
    if compensated == "partial-delay":
        parts.append(f"sound {_ms(reply.number('audio-out-delay'))}")
    elif compensated in ("delay", "no-delay"):
        parts.append("sound delayed to match" if compensated == "delay" else "sound not delayed")
    return ", ".join(parts)


def _receiver(replies: dict[str, Reply]) -> str:
    """ 'connected: "Soundbar", volume 30, not muted' """
    if replies["receiver"].state == "no answer":
        return "none connected"
    name, sound = replies.get("receiver name"), replies.get("receiver audio")
    parts = [f'"{name.get("name")}"' if name and name.get("name") else "",
             audio(sound) if sound and sound.state == "answer" else ""]
    return ": ".join(["connected", ", ".join(p for p in parts if p)]).rstrip(": ")


def _who(replies: dict[str, Reply]) -> str:
    """ 'name "Game", type TV, HDMI address 0.0.0.0' from the OSD name and the physical address replies."""
    name, kind = replies["name"].get("name"), replies["address"].get("prim-devtype")
    address = replies["address"].get("phys-addr")
    parts = [f'name "{name}"' if name else "", f"type {'TV' if kind == 'tv' else kind}" if kind else "",
             f"HDMI address {address}" if address else ""]
    return ", ".join(p for p in parts if p)


def rows(replies: dict[str, Reply]) -> list[tuple[str, str]]:
    """The TV Info table: (question, answer)."""
    def answer(key: str, text: Callable[[Reply], str], unsupported: str = "not supported",
               no_reply: str = "no answer") -> str:
        r = replies[key]
        if r.state == "answer":
            return text(r)
        return {"unsupported": unsupported, "no reply": no_reply}.get(r.state, "no answer (is the TV on?)")

    return [
        ("CEC version", answer("version", lambda r: _version(r.get("cec-version")) or "?")),
        ("Power status", answer("power", lambda r: f"yes ({r.get('pwr-state') or '?'})")),
        ("Its name and type", _who(replies) or answer("name", lambda r: "?")),
        ("Vendor ID", answer("vendor", lambda r: vendor_name(r.fields.get("vendor-id", "")))),
        ("Menu language", answer("language", lambda r: LANGUAGES.get(r.get("language"), r.get("language")))),
        ("CEC 2.0 feature list", answer("features", lambda r: f"supported: {features(r)}" if features(r)
                                        else "supported")),
        ("Volume and mute status", answer("audio", audio, "not supported (it does not report its volume)")),
        ("Lip-sync delay", answer("latency", latency, no_reply="no answer (a CEC 2.0 feature)")),
        # A poll brings no reply: it went through ("no reply") when a device took it.
        ("AV receiver or soundbar", _receiver(replies)),
    ]
