# SPDX-License-Identifier: GPL-3.0-or-later
"""One stream from start to end, off the GUI thread: the streaming token, the session (with the queue of a cloud
game), the WebRTC offer and answer, the candidates, the keepalive every 30 s, and at the end the session's end
with the service.

The video frames are turned into images on a thread of their own, always the newest frame (one the window has
not drawn yet is replaced, so a slow moment never builds up delay). The sound is resampled to 48 kHz stereo,
16 bits, for the window's audio output. Both reach the window as Qt signals."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from . import ice
from .auth import Account, AuthError
from .net import HttpError
from .peer import Events, Peer
from .session import KEEPALIVE_S, Session, SessionError, State


def state_text(state: State) -> str:
    if state.name == "WaitingForResources":
        if state.wait_s:
            minutes = max(1, round(state.wait_s / 60))
            return f"In the queue for a cloud server: about {minutes} minute{'s' if minutes != 1 else ''}…"
        return "In the queue for a cloud server…"
    return {"Provisioning": "Getting the Xbox ready…", "ReadyToConnect": "Signing the stream in…",
            "Provisioned": "Connecting…"}.get(state.name, f"{state.name}…")


def to_image(frame) -> QImage:
    """An av.VideoFrame as a QImage (32-bit, its own copy of the pixels)."""
    rgb = frame.reformat(format="bgra")
    plane = rgb.planes[0]
    return QImage(bytes(plane), rgb.width, rgb.height, plane.line_size, QImage.Format.Format_RGB32).copy()


class FrameConverter:
    """Turns the newest video frame into an image on its own thread."""

    def __init__(self, deliver: Callable[[QImage, int, float], None], convert: Callable[[object], QImage] = to_image):
        self.deliver, self.convert = deliver, convert
        self.lock = threading.Lock()
        self.waiting = threading.Event()
        self.latest: tuple[object, float] | None = None
        self.running = True
        self.thread = threading.Thread(target=self._run, name="console-linkb-video", daemon=True)
        self.thread.start()

    def put(self, frame, arrived_ms: float) -> None:
        with self.lock:
            self.latest = (frame, arrived_ms)
        self.waiting.set()

    def _run(self) -> None:
        while self.running:
            self.waiting.wait()
            self.waiting.clear()
            with self.lock:
                item, self.latest = self.latest, None
            if item is None or not self.running:
                continue
            frame, arrived = item
            try:
                image = self.convert(frame)
            except Exception:  # noqa: BLE001  (a frame that cannot be converted is skipped)
                continue
            self.deliver(image, int(frame.pts or 0), arrived)

    def stop(self) -> None:
        self.running = False
        self.waiting.set()
        self.thread.join(2)


class SoundConverter:
    """av.AudioFrames to 48 kHz stereo 16-bit PCM."""

    def __init__(self):
        import av
        self.resampler = av.AudioResampler(format="s16", layout="stereo", rate=48000)

    def __call__(self, frame) -> bytes:
        return b"".join(bytes(out.planes[0])[:out.samples * 4] for out in self.resampler.resample(frame))


class Stream(QObject):
    status = pyqtSignal(str)                # what the stream is doing, while it starts
    ready = pyqtSignal()                    # the channels are up: the picture comes
    ended = pyqtSignal(str)                 # the reason; "" when the person ended it
    image = pyqtSignal(QImage, int, float)  # a video frame, its RTP timestamp, when it arrived (ms)
    sound = pyqtSignal(bytes)               # 48 kHz stereo 16-bit PCM
    dialog = pyqtSignal(object)             # a channels.Dialog to answer
    vibration = pyqtSignal(object)          # an inputs.Vibration for the pad
    log = pyqtSignal(str)

    def __init__(self, account: Account, kind: str, target: str, locale: str = "en-US",
                 peer_factory: Callable[[Events], Peer] = Peer, session_factory=Session, parent=None):
        """*kind*: "home" (*target*: the console's ID) or "cloud" (*target*: the game's title ID)."""
        super().__init__(parent)
        self.account, self.kind, self.target, self.locale = account, kind, target, locale
        self.peer_factory, self.session_factory = peer_factory, session_factory
        self.stopping = threading.Event()
        self.session: Session | None = None
        self.peer: Peer | None = None
        self.video: FrameConverter | None = None
        self.thread = threading.Thread(target=self._run, name="console-linkb-stream", daemon=True)
        self.closing = threading.Lock()     # one close at a time: the person's, an error's, the setup's own
        self.finished = False

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        """The person ends the stream: everything closes off the GUI thread."""
        if not self.stopping.is_set():
            self.stopping.set()
            threading.Thread(target=self._close, args=("",), daemon=True).start()

    def _end(self, reason: str) -> None:
        if not self.stopping.is_set():
            self.stopping.set()
            self._close(reason)

    def _close(self, reason: str) -> None:
        """Closes what is open (again, when the setup opened more after an earlier close) and says why, once."""
        with self.closing:
            if self.peer is not None:
                self.peer.close()
            if self.video is not None:
                self.video.stop()
            if self.session is not None:
                self.session.stop()
            if not self.finished:
                self.finished = True
                self.ended.emit(reason)

    def frame_shown(self, rtp_timestamp: int, arrived_ms: float) -> None:
        if self.peer is not None:
            self.peer.frame_shown(rtp_timestamp, arrived_ms)

    def set_pads(self, pads) -> None:
        if self.peer is not None:
            self.peer.set_pads(pads)

    def answer_dialog(self, dialog, accepted: bool) -> None:
        if self.peer is not None:
            self.peer.answer_dialog(dialog, accepted)

    def _events(self) -> Events:
        sound = SoundConverter()
        self.video = FrameConverter(lambda image, pts, arrived: self.image.emit(image, pts, arrived))

        def video(frame) -> None:
            self.video.put(frame, self.peer.now_ms())

        def audio(frame) -> None:
            try:
                self.sound.emit(sound(frame))
            except Exception:  # noqa: BLE001  (a frame that cannot be resampled is skipped)
                pass
        return Events(video=video, audio=audio, ready=self.ready.emit,
                      closed=lambda reason: threading.Thread(target=self._end, args=(reason,), daemon=True).start(),
                      dialog=self.dialog.emit, vibration=self.vibration.emit, log=self.log.emit)

    def _run(self) -> None:
        try:
            self.status.emit("Asking the streaming service…")
            token = self.account.home_token() if self.kind == "home" else self.account.cloud_token()
            self.session = self.session_factory(self.account.client, token, self.kind, self.target, self.locale)
            self.session.play()
            self.log.emit(f"Session started ({self.kind})")
            self.session.wait_until_ready(self.account.transfer_token,
                                          on_state=lambda state: self.status.emit(state_text(state)),
                                          cancelled=self.stopping.is_set)
            self.status.emit("Connecting…")
            self.peer = self.peer_factory(self._events())
            self.peer.start()
            offer = self.peer.offer()
            answer = self.session.exchange_sdp(offer)
            remote = self.session.exchange_ice(ice.local_candidates(offer))
            self.log.emit(f"Candidates: {len(ice.local_candidates(offer))} sent, {len(remote)} received")
            self.peer.answer(ice.with_candidates(answer, ice.remote_candidates(remote)))
        except (SessionError, AuthError, HttpError, TimeoutError, OSError) as error:
            if not self.stopping.is_set():
                self._end(f"{error}")
            else:
                self._close("")             # stopped while starting: end what the setup opened after the stop
            return
        if self.stopping.is_set():
            self._close("")
            return
        last = time.monotonic()
        while not self.stopping.wait(1):
            if time.monotonic() - last >= KEEPALIVE_S:
                last = time.monotonic()
                try:
                    self.session.keepalive()
                except HttpError as error:
                    self.log.emit(f"Keepalive: {error}")
                    if error.status == 404:
                        self._end("the streaming service ended the session")
