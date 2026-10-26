# SPDX-License-Identifier: GPL-3.0-or-later
"""Register the recording-stop shortcut through the desktop portal."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

from dbus_next.aio.message_bus import MessageBus
from dbus_next.constants import MessageType
from dbus_next.message import Message
from dbus_next.signature import Variant

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
REQUEST = "org.freedesktop.portal.Request"
SHORTCUT_ID = "stop-recording"
TRIGGER = "<Control><Alt>F12"


def _write_event(name: str, **data: str) -> None:
    print(json.dumps({"event": name, **data}), flush=True)


async def _wait_for_response(
    request_path: str,
    responses: dict[str, tuple[int, dict[str, Variant]]],
    response_waiters: dict[str, asyncio.Future[tuple[int, dict[str, Variant]]]],
) -> tuple[int, dict[str, Variant]]:
    if request_path in responses:
        return responses.pop(request_path)
    future = asyncio.get_running_loop().create_future()
    response_waiters[request_path] = future
    try:
        return await future
    finally:
        response_waiters.pop(request_path, None)


async def _request(
    bus: MessageBus,
    member: str,
    signature: str,
    body: list[object],
    responses: dict[str, tuple[int, dict[str, Variant]]],
    response_waiters: dict[str, asyncio.Future[tuple[int, dict[str, Variant]]]],
) -> tuple[int, dict[str, Variant]]:
    reply = await bus.call(
        Message(
            destination=PORTAL,
            path=PORTAL_PATH,
            interface=SHORTCUTS,
            member=member,
            signature=signature,
            body=body,
        )
    )
    if reply is None:
        raise RuntimeError(f"The desktop returned no reply to {member}.")
    if reply.message_type == MessageType.ERROR:
        detail = reply.body[0] if reply.body else reply.error_name or "Unknown portal error"
        raise RuntimeError(str(detail))
    request_path = reply.body[0]
    return await _wait_for_response(request_path, responses, response_waiters)


async def _run() -> None:
    bus = await MessageBus().connect()
    responses: dict[str, tuple[int, dict[str, Variant]]] = {}
    response_waiters: dict[str, asyncio.Future[tuple[int, dict[str, Variant]]]] = {}

    def handle_message(message: Message) -> bool:
        if (
            message.message_type == MessageType.SIGNAL
            and message.interface == REQUEST
            and message.member == "Response"
            and message.path is not None
        ):
            response = (message.body[0], message.body[1])
            waiter = response_waiters.get(message.path)
            if waiter is not None and not waiter.done():
                waiter.set_result(response)
            else:
                responses[message.path] = response
            return True

        if (
            message.message_type == MessageType.SIGNAL
            and message.interface == SHORTCUTS
            and message.member == "Activated"
            and len(message.body) == 4
            and message.body[1] == SHORTCUT_ID
        ):
            _write_event("activated")
            return True
        return False

    bus.add_message_handler(handle_message)
    token = uuid.uuid4().hex
    code, results = await _request(
        bus,
        "CreateSession",
        "a{sv}",
        [
            {
                "handle_token": Variant("s", f"simple_media_tool_{token}"),
                "session_handle_token": Variant("s", f"simple_media_tool_session_{token}"),
            }
        ],
        responses,
        response_waiters,
    )
    if code != 0:
        raise RuntimeError("The desktop canceled creation of the global-shortcut session.")
    session_handle = results["session_handle"].value

    code, results = await _request(
        bus,
        "BindShortcuts",
        "oa(sa{sv})sa{sv}",
        [
            session_handle,
            [
                [
                    SHORTCUT_ID,
                    {
                        "description": Variant("s", "Stop OBS recording and show Media Tool"),
                        "preferred_trigger": Variant("s", TRIGGER),
                    },
                ]
            ],
            "",
            {"handle_token": Variant("s", f"simple_media_tool_bind_{token}")},
        ],
        responses,
        response_waiters,
    )
    if code != 0:
        raise RuntimeError("The desktop canceled registration of Ctrl+Alt+F12.")
    shortcuts_variant = results.get("shortcuts")
    if not isinstance(shortcuts_variant, Variant):
        raise RuntimeError("The desktop did not confirm which shortcut it registered.")
    bound = next(
        (
            properties
            for shortcut_id, properties in shortcuts_variant.value
            if shortcut_id == SHORTCUT_ID
        ),
        None,
    )
    trigger_description = bound.get("trigger_description") if bound else None
    if not isinstance(trigger_description, Variant) or not isinstance(trigger_description.value, str):
        keys = ", ".join(sorted(bound)) if bound else "no shortcut details"
        raise RuntimeError(f"The desktop registered the shortcut without a trigger description ({keys}).")
    _write_event("registered", trigger=trigger_description.value)
    await asyncio.Future()


def main() -> int:
    try:
        asyncio.run(_run())
    except Exception as exc:
        _write_event("error", message=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
