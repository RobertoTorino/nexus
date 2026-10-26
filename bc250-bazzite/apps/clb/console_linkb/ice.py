# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from Greenlight (packages/player/src/client/lib/ice.ts, teredo.ts and
# packages/desktop/main/helpers/xcloudapi.ts), MIT, Copyright (c) 2019 UnknownSKL (Jim Kroon); the MIT notice is in
# the README's License section.
"""The ICE candidates of the stream, in the form the streaming service exchanges them.

aiortc gathers the board's candidates before the offer and puts them in its SDP, so they are read from there. The
service's candidates come back as "a=candidate:..." lines. An Xbox at home announces a Teredo address (2001::/32)
among them; as in the reference, the IPv4 address and port inside it are added as two more candidates (the port the
Teredo address names, and 9002), since that is where the console answers."""

from __future__ import annotations

import ipaddress


def local_candidates(sdp: str) -> list[dict]:
    """The candidates in the board's SDP: {candidate, sdpMid, sdpMLineIndex} for those of the first media section
    (the offer bundles all sections on its transport)."""
    lines, index, mid = [], -1, "0"
    for line in sdp.splitlines():
        line = line.strip()
        if line.startswith("m="):
            index += 1
            if index > 0:
                break
        elif index == 0 and line.startswith("a=mid:"):
            mid = line[len("a=mid:"):]
        elif index == 0 and line.startswith("a=candidate:"):
            lines.append(line[len("a="):])
    return [{"candidate": text, "sdpMid": mid, "sdpMLineIndex": 0} for text in lines]


def teredo(address: str) -> tuple[str, int] | None:
    """The IPv4 address and UDP port inside a Teredo address (both stored inverted); None for another address."""
    try:
        ip = ipaddress.IPv6Address(address)
    except ValueError:
        return None
    if ip.teredo is None:
        return None
    _server, client = ip.teredo
    port = (~int.from_bytes(ip.packed[10:12], "big")) & 0xFFFF
    return str(client), port


def candidate_line(candidate: dict) -> str:
    """The candidate's text without "a=" or "candidate:"."""
    text = str(candidate.get("candidate", "")).strip()
    if text.startswith("a="):
        text = text[2:]
    if text.startswith("candidate:"):
        text = text[len("candidate:"):]
    return text


def remote_candidates(candidates: list[dict]) -> list[dict]:
    """The service's candidates, with the Teredo ones' IPv4 address added as two host candidates before each, and
    the end-of-candidates marker left out."""
    out: list[dict] = []
    for candidate in candidates:
        text = candidate_line(candidate)
        if not text or text == "end-of-candidates" or str(candidate.get("candidate", "")).strip() == \
                "a=end-of-candidates":
            continue
        parts = text.split()
        inner = teredo(parts[4]) if len(parts) > 4 and parts[4].lower().startswith("2001") else None
        if inner is not None:
            ipv4, port = inner
            for foundation, at in (("10", 9002), ("11", port)):
                out.append({"candidate": f"candidate:{foundation} 1 UDP 1 {ipv4} {at} typ host",
                            "sdpMid": "0", "sdpMLineIndex": 0})
        out.append({"candidate": f"candidate:{text}", "sdpMid": str(candidate.get("sdpMid", "0")),
                    "sdpMLineIndex": int(candidate.get("sdpMLineIndex", 0) or 0)})
    return out


def with_candidates(sdp: str, candidates: list[dict]) -> str:
    """The service's answer with its exchanged candidates (remote_candidates()) added to every media section, and
    the end of candidates: aiortc then starts its checks with all of them at once."""
    extra = [f"a={c['candidate']}" for c in candidates] + ["a=end-of-candidates"]
    out: list[str] = []
    in_media = False
    for line in sdp.replace("\r\n", "\n").split("\n"):
        if line.startswith("m=") and in_media:
            out.extend(extra)
        if line.startswith("m="):
            in_media = True
        if line == "a=end-of-candidates":
            continue                    # added once, after the exchanged candidates
        if line and line not in extra:
            out.append(line)
    if in_media:
        out.extend(extra)
    return "\r\n".join(out) + "\r\n"
