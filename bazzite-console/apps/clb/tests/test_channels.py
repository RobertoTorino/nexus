# SPDX-License-Identifier: GPL-3.0-or-later
"""The message and control channels' JSON."""

from __future__ import annotations

import json

from console_linkb import channels


def test_handshake_and_its_acknowledgement():
    assert json.loads(channels.handshake()) == {"type": "Handshake", "version": "messageV1",
                                                "id": channels.HANDSHAKE_ID, "cv": "0"}
    assert channels.handle(json.dumps({"type": "HandshakeAck"})).handshake_done


def test_the_configuration_messages():
    sent = [json.loads(m) for m in channels.configuration(1280, 720)]
    targets = [m["target"] for m in sent]
    assert targets[0] == "/streaming/systemUi/configuration"
    assert targets[-1] == "/streaming/characteristics/dimensionschanged"
    size = json.loads(sent[-1]["content"])
    assert (size["horizontal"], size["vertical"], size["safeAreaBottom"]) == (1280, 720, 720)
    assert len({m["id"] for m in sent}) == len(sent)
    assert json.loads(sent[0]["content"]) == {"version": [0, 2, 0], "systemUis": []}


def test_the_service_ends_the_stream():
    incoming = channels.handle(json.dumps({"type": "TransactionStart", "target": channels.DISCONNECT, "id": "T1",
                                           "content": "{}"}))
    assert incoming.disconnect
    assert json.loads(incoming.replies[0]) == {"type": "TransactionComplete", "content": '""', "id": "T1", "cv": ""}


def test_a_dialog_and_its_answer():
    content = json.dumps({"TitleText": "Quit?", "ContentText": "Unsaved progress is lost."})
    incoming = channels.handle(json.dumps({"type": "TransactionStart", "target": channels.DIALOG, "id": "T2",
                                           "content": content}))
    assert incoming.dialog == channels.Dialog("T2", "Quit?", "Unsaved progress is lost.")
    assert json.loads(json.loads(channels.dialog_answer(incoming.dialog, True))["content"]) == {"Result": 0}
    assert json.loads(json.loads(channels.dialog_answer(incoming.dialog, False))["content"]) == {"Result": 1}


def test_other_messages_are_left_alone():
    for text in ("not json", "[]", json.dumps({"type": "Message", "target": "/streaming/properties/titleinfo",
                                               "content": "{}"}), json.dumps({"type": "Other"})):
        assert channels.handle(text) == channels.Incoming()


def test_control_messages():
    assert json.loads(channels.authorization()) == {"message": "authorizationRequest",
                                                     "accessKey": channels.ACCESS_KEY}
    assert json.loads(channels.gamepad_changed(0, True)) == {"message": "gamepadChanged", "gamepadIndex": 0,
                                                             "wasAdded": True}
    assert json.loads(channels.keyframe_request()) == {"message": "videoKeyframeRequested", "ifrRequested": True}
