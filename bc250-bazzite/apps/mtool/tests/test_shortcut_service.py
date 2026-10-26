# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio

from dbus_next.message import Message
from dbus_next.signature import Variant

from media_tool import shortcut_service


def test_shortcut_service_creates_session_binds_key_and_forwards_activation(monkeypatch):
    session_path = "/org/freedesktop/portal/desktop/session/test"

    class FakeBus:
        def __init__(self):
            self.handlers = []
            self.calls = []

        async def connect(self):
            return self

        def add_message_handler(self, handler):
            self.handlers.append(handler)

        async def call(self, request):
            self.calls.append(request)
            request.serial = 1
            request_path = f"/org/freedesktop/portal/desktop/request/test/{request.member.lower()}"
            if request.member == "CreateSession":
                results = {"session_handle": Variant("o", session_path)}
            else:
                results = {
                    "shortcuts": Variant(
                        "a(sa{sv})",
                        [
                            [
                                "stop-recording",
                                {"trigger_description": Variant("s", "Ctrl+Alt+End")},
                            ]
                        ],
                    )
                }
            signal = Message.new_signal(
                request_path,
                shortcut_service.REQUEST,
                "Response",
                "ua{sv}",
                [0, results],
            )
            asyncio.get_running_loop().call_soon(self._send, signal)
            return Message.new_method_return(request, "o", [request_path])

        def _send(self, message):
            for handler in self.handlers:
                handler(message)

    async def exercise_service(bus, events):
        task = asyncio.create_task(shortcut_service._run())
        try:
            for _ in range(100):
                await asyncio.sleep(0)
                if any(event["event"] == "registered" for event in events):
                    break
            assert [call.member for call in bus.calls] == ["CreateSession", "BindShortcuts"]
            bind = bus.calls[1]
            assert bind.signature == "oa(sa{sv})sa{sv}"
            assert bind.body[1][0][0] == shortcut_service.SHORTCUT_ID
            assert bind.body[1][0][1]["preferred_trigger"].value == shortcut_service.TRIGGER
            assert {"event": "registered", "trigger": "Ctrl+Alt+End"} in events

            activated = Message.new_signal(
                shortcut_service.PORTAL_PATH,
                shortcut_service.SHORTCUTS,
                "Activated",
                "osta{sv}",
                [session_path, shortcut_service.SHORTCUT_ID, 1, {}],
            )
            bus._send(activated)
            await asyncio.sleep(0)
            assert events[-1] == {"event": "activated"}
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    bus = FakeBus()
    events = []
    monkeypatch.setattr(shortcut_service, "MessageBus", lambda: bus)
    monkeypatch.setattr(shortcut_service, "_write_event", lambda name, **data: events.append({"event": name, **data}))

    asyncio.run(exercise_service(bus, events))
