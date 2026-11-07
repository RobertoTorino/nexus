# SPDX-License-Identifier: GPL-3.0-or-later
"""The app's settings, shared by the window and the load service (python -m usb_hdcam --load --auto)."""

from __future__ import annotations

import json

from bc250_core.settings import SettingsStore

# Each half of a side-by-side frame is the lens on that side as one faces the camera.
VIEWS = {"both": "Whole frame", "left": "Left half: the lens on your left",
         "right": "Right half: the lens on your right"}
# Start with automatic exposure; the user can change it in the controls.
CONTROL_DEFAULTS = {"auto_exposure": 0}
BANDWIDTH_NAMES = {"reduced": "Reduced: for USB controllers that cannot handle full bandwidth",
                   "full": "Full: every mode at every rate, if the USB controller allows it"}


class CameraSettings(SettingsStore):
    DEFAULTS = {"autoload": True,           # the load service sends the firmware when the camera is plugged in
                "bandwidth": "reduced",     # loader.BANDWIDTHS: the video endpoint the firmware is sent with
                "mode": "",                 # the preview's mode, "<width>x<height>@<fps>"; "": the camera's default
                "view": "both",             # VIEWS: what the preview shows of a stereo mode
                "gray": False,              # the full screen in black and white
                "controls": ""}             # JSON {control key: value}: the picture settings the user chose

    def controls(self) -> dict[str, int]:
        """The picture settings to set: the user's, over the app's CONTROL_DEFAULTS."""
        try:
            chosen = json.loads(self.get("controls") or "{}")
        except ValueError:
            chosen = {}
        if not isinstance(chosen, dict):
            chosen = {}
        return {**CONTROL_DEFAULTS, **{str(key): value for key, value in chosen.items() if isinstance(value, int)}}

    def set_controls(self, chosen: dict[str, int]) -> None:
        self.set("controls", json.dumps(chosen, sort_keys=True) if chosen else "")
