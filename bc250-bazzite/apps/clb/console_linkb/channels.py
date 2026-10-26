# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from Greenlight (packages/player/src/client/lib/channel/message.ts, message/handler.ts and control.ts),
# MIT, Copyright (c) 2019 UnknownSKL (Jim Kroon); the MIT notice is in the README's License section.
"""What goes over the message and control channels, as JSON text.

The message channel opens with a handshake; when the service acknowledges it, the control channel authorizes the
client and announces the pad, the input channel starts and the client sends its configuration (no system UI of its
own, the screen size). After that the service sends messages and transactions: the stream's end
(serverInitiatedDisconnect) and dialogs to answer (ShowMessageDialog); the others are left alone, as the
reference leaves them."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

HANDSHAKE_ID = "be0bfc6d-1e83-4c8a-90ed-fa8601c5a179"         # the reference's fixed values
ACCESS_KEY = "4BDB3609-C1F1-4195-9B37-FEFF45DA8B8E"
CLIENT_APP_INSTALL_ID = "c97d7ee0-73b2-4239-bf1d-9d805a338429"
DISCONNECT = "/streaming/sessionLifetimeManagement/serverInitiatedDisconnect"
DIALOG = "/streaming/systemUi/messages/ShowMessageDialog"


def handshake() -> str:
    return json.dumps({"type": "Handshake", "version": "messageV1", "id": HANDSHAKE_ID, "cv": "0"})


def message(target: str, content: object, message_id: str | None = None) -> str:
    return json.dumps({"type": "Message", "content": json.dumps(content), "id": message_id or str(uuid.uuid4()),
                       "target": target, "cv": ""})


def configuration(width: int = 1920, height: int = 1080) -> list[str]:
    """The client's configuration, sent once the handshake is acknowledged."""
    return [
        message("/streaming/systemUi/configuration", {"version": [0, 2, 0], "systemUis": []}),
        message("/streaming/properties/clientappinstallidchanged", {"clientAppInstallId": CLIENT_APP_INSTALL_ID}),
        message("/streaming/characteristics/orientationchanged", {"orientation": 0}),
        message("/streaming/characteristics/touchinputenabledchanged", {"touchInputEnabled": False}),
        message("/streaming/characteristics/clientdevicecapabilities", {}),
        message("/streaming/characteristics/dimensionschanged", {
            "horizontal": width, "vertical": height, "preferredWidth": width, "preferredHeight": height,
            "safeAreaLeft": 0, "safeAreaTop": 0, "safeAreaRight": width, "safeAreaBottom": height,
            "supportsCustomResolution": True}),
    ]


def complete(transaction_id: str, content: object) -> str:
    return json.dumps({"type": "TransactionComplete", "content": json.dumps(content), "id": transaction_id,
                       "cv": ""})


@dataclass
class Dialog:
    """A dialog the service asks the person to answer (e.g. a game that wants to quit)."""

    transaction_id: str
    title: str
    text: str


@dataclass
class Incoming:
    """What a message from the service means for the client."""

    handshake_done: bool = False
    disconnect: bool = False
    dialog: Dialog | None = None
    replies: tuple[str, ...] = ()           # to send back at once


def _content(data: dict) -> dict:
    try:
        content = json.loads(data.get("content") or "{}")
    except (TypeError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def handle(text: str) -> Incoming:
    try:
        data = json.loads(text)
    except ValueError:
        return Incoming()
    if not isinstance(data, dict):
        return Incoming()
    kind = data.get("type")
    if kind == "HandshakeAck":
        return Incoming(handshake_done=True)
    if kind not in ("TransactionStart", "Message"):
        return Incoming()
    target, transaction = data.get("target"), str(data.get("id", ""))
    if target == DISCONNECT:
        return Incoming(disconnect=True, replies=(complete(transaction, ""),))
    if target == DIALOG:
        content = _content(data)
        return Incoming(dialog=Dialog(transaction, str(content.get("TitleText", "")),
                                      str(content.get("ContentText", ""))))
    return Incoming()


def dialog_answer(dialog: Dialog, accepted: bool) -> str:
    """The answer to a dialog: Result 0 for its first button, 1 for the other (as the reference answers)."""
    return complete(dialog.transaction_id, {"Result": 0 if accepted else 1})


# --- Control channel --------------------------------------------------------------------------------------------

def authorization() -> str:
    return json.dumps({"message": "authorizationRequest", "accessKey": ACCESS_KEY})


def gamepad_changed(index: int, added: bool) -> str:
    return json.dumps({"message": "gamepadChanged", "gamepadIndex": index, "wasAdded": added})


def keyframe_request(full: bool = True) -> str:
    return json.dumps({"message": "videoKeyframeRequested", "ifrRequested": full})
