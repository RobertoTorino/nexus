# SPDX-License-Identifier: AGPL-3.0-only
"""The launch spec: the JSON in the BIG message that tells the console the
resolution, frame rate, bitrate and codec to stream. Its text is the reference's byte for byte, placeholders included
(the account, region and title fields are not used on the local network)."""

from __future__ import annotations

import base64

from .rpcrypt import RPCrypt
from .target import Target

_FORMAT = (
    '{{"sessionId":"sessionId4321","streamResolutions":[{{"resolution":{{"width":{width},"height":{height}}},'
    '"maxFps":{max_fps},"score":10}}],"network":{{"bwKbpsSent":{bitrate},"bwLoss":0.001000,"mtu":{mtu},'
    '"rtt":{rtt},"ports":[53,2053]}},"slotId":1,"appSpecification":{{"minFps":30,"minBandwidth":0,'
    '"extTitleId":"ps3","version":1,"timeLimit":1,"startTimeout":100,"afkTimeout":100,"afkTimeoutDisconnect":100}},'
    '"konan":{{"ps3AccessToken":"accessToken","ps3RefreshToken":"refreshToken"}},"requestGameSpecification":{{'
    '"model":"bravia_tv","platform":"android","audioChannels":"5.1","language":"sp","acceptButton":"X",'
    '"connectedControllers":["xinput","ds3","ds4"],"yuvCoefficient":"bt601","videoEncoderProfile":"hw4.1",'
    '"audioEncoderProfile":"audio1"{adaptive}}},"userProfile":{{"onlineId":"psnId","npId":"npId","region":"US",'
    '"languagesUsed":["en","jp"]}},{codec}{range}"handshakeKey":"{handshake_key}"}}'
)


def format_spec(target: Target, width: int, height: int, max_fps: int, codec: str, bitrate: int, mtu: int,
                rtt_ms: int, handshake_key: bytes) -> str:
    """codec: h264, h265 or h265_hdr (as in the control connection). The PS5 gets the codec and dynamic range; the
    PS4 only streams H.264 and gets neither."""
    adaptive = codec_text = range_text = ""
    if target.ps5:
        adaptive = ',"adaptiveStreamMode": "resize"'
        codec_text = '"videoCodec":"hevc",' if codec in ("h265", "h265_hdr") else '"videoCodec":"avc",'
        range_text = '"dynamicRange":"HDR",' if codec == "h265_hdr" else '"dynamicRange":"SDR",'
    return _FORMAT.format(width=width, height=height, max_fps=max_fps, bitrate=bitrate, mtu=mtu, rtt=rtt_ms,
                          adaptive=adaptive, codec=codec_text, range=range_text,
                          handshake_key=base64.b64encode(handshake_key).decode())


def encode_for_big(crypt: RPCrypt, spec: str) -> str:
    """The launch spec as BIG carries it: the session crypto's key stream for counter 0 (zeros encrypted) XORed
    with the JSON and its closing NUL, in base64. This is not CFB-encrypting the JSON itself."""
    plain = spec.encode() + b"\0"
    stream = crypt.encrypt(0, bytes(len(plain)))
    return base64.b64encode(bytes(a ^ b for a, b in zip(stream, plain))).decode()
