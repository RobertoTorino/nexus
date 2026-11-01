# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network steps the window starts, each run off the window's thread. Each returns an Outcome, never raises: the
window only shows the message and uses the value. Console Link's steps (the BC250 Bazzite Suite's jobs.py), the
search, the account ID, registering, waking, the test session and rest mode; not Console Link's stream."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import discovery, psn, regist, session
from .consoles import RegisteredConsole
from .httpmsg import ProtocolError
from .target import Target

TEST_SECONDS = 3.0                      # how long a test session stays open, answering heartbeats
REST_GRACE = 0.5                        # time for the rest-mode message to reach the console before closing
SESSION_CODEC = "h264"                  # what the control connection names (a PS5 asks for it); no stream follows


@dataclass
class Outcome:
    ok: bool
    message: str
    value: object = None
    log: list[str] = field(default_factory=list)


def find(address: str = discovery.BROADCAST, timeout: float = 2.0, **ports) -> Outcome:
    try:
        consoles = discovery.search(address, timeout, **ports)
    except OSError as error:
        return Outcome(False, f"The search could not be sent: {error}.")
    if not consoles:
        where = "on the network" if address == discovery.BROADCAST else f"at {address}"
        return Outcome(True, f"No console answered {where}.", [])
    return Outcome(True, f"{len(consoles)} console{'s' if len(consoles) != 1 else ''} found.", consoles)


def psn_account(redirect: str, **kwargs) -> Outcome:
    """The account ID from the PlayStation sign-in: *redirect* is the address the sign-in sent the browser to."""
    try:
        account = psn.account_id(psn.code_from_redirect(redirect), **kwargs)
    except psn.PsnError as error:
        return Outcome(False, str(error))
    name = f" ({account.online_id})" if account.online_id else ""
    return Outcome(True, f"Account ID of your PSN account{name}: {account.code}, filled in for registration.", account)


def register(console: discovery.Console, account_id: bytes, pin: int, **kwargs) -> Outcome:
    target = console.target
    if target.unknown:
        target = Target.PS5_1 if console.ps5 else Target.PS4_10
    try:
        registration = regist.register(console.address, target, account_id, pin, **kwargs)
    except regist.RegistError as error:
        return Outcome(False, str(error))
    except (OSError, ProtocolError) as error:
        return Outcome(False, f"Registration failed: {error}.")
    registered = RegisteredConsole.from_registration(registration, console.address, console.host_id)
    return Outcome(True, f"Registered with {registered.nickname or console.host_name or console.address}.", registered)


def wake(console: RegisteredConsole, **kwargs) -> Outcome:
    try:
        discovery.wake(console.address, console.regist_key, console.ps5, **kwargs)
    except (OSError, ValueError) as error:
        return Outcome(False, f"The wake-up could not be sent: {error}.")
    return Outcome(True, f"Wake-up sent to {console.nickname or console.address}. It takes the console about 20 "
                         "seconds to come out of rest mode.")


def _session(console: RegisteredConsole, then, **kwargs) -> Outcome:
    kwargs.setdefault("codec", SESSION_CODEC)
    started = session.Session(console.address, console.target, console.regist_key, console.rp_key,
                              login_pin=console.login_pin, **kwargs)
    try:
        with started:
            info = started.start()
            message = then(started)
    except session.SessionError as error:
        return Outcome(False, str(error), started.info, started.info.log)
    except (OSError, ProtocolError) as error:
        return Outcome(False, f"The session broke off: {error}.", started.info, started.info.log)
    return Outcome(True, message, info, info.log)


def test_session(console: RegisteredConsole, seconds: float = TEST_SECONDS, **kwargs) -> Outcome:
    """Start a session, keep it for *seconds* and close it: proves the registration and the control connection."""
    def hold(started: session.Session) -> str:
        started.keep_alive(seconds)
        return (f"Session with {console.nickname or console.address} started and closed again "
                f"({started.info.server_type or console.target.console}).")
    return _session(console, hold, **kwargs)


def rest_mode(console: RegisteredConsole, **kwargs) -> Outcome:
    def bed(started: session.Session) -> str:
        started.goto_bed()
        time.sleep(REST_GRACE)
        return f"{console.nickname or console.address} goes to rest mode."
    return _session(console, bed, **kwargs)
