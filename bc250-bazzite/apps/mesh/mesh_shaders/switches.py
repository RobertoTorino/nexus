# SPDX-License-Identifier: GPL-3.0-or-later
"""The DirectMesh driver's switches for one game: environment variables in front of the launch options, for
comparisons and for finding the cause of a problem, and one for games that need it. All off is the driver as
DirectMesh ships it."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from bc250_core import window_title


@dataclass(frozen=True)
class Switch:
    variable: str
    value: str
    label: str
    help: str

    @property
    def setting(self) -> str:
        return f"switch/{self.variable}"

    @property
    def assignment(self) -> str:
        return f"{self.variable}={self.value}"


SWITCHES = (
    Switch("RADV_BC250_MESH_IDXPASS", "0", "No indexed mesh draws",
           "Keeps DirectMesh's protected mesh routes, without its indexed mesh draws."),
    Switch("RADV_BC250_MESH_SAFE_COMPACT", "0", "No renumbered vertices",
           "A workgroup whose culling left unused vertices exports private triangle corners instead of only the "
           "vertices it uses."),
    Switch("RADV_BC250_MESH_SAFE_ADAPTIVE", "0", "Private corners only",
           "No shared vertices at all: every triangle exports its own corners. Slower; the most cautious route."),
    Switch("RADV_DIRECTMESH", "0", "DirectMesh off",
           "The driver falls back to its base BC-250 settings, for a comparison on the same driver."),
    Switch("RADV_DEBUG", "nomeshshader", "Hide mesh shaders",
           "The game does not see mesh shaders and takes its own path without them, for a comparison."),
    Switch("RADV_BC250_MESH_SPLIT_WRITES", "1", "Split mesh shaders that write memory",
           "For a game whose large mesh shaders write to buffers (PS5 emulators): the driver splits them anyway and "
           "runs those writes once. It cannot check that the game never reads them back in the same draw, so only "
           "for the game that needs it."),
)


def launch_options(base: str, chosen: list[Switch]) -> str:
    """The launch options with the chosen switches in front: "RADV_DIRECTMESH=0 /usr/local/bin/… %command%"."""
    return " ".join([*(switch.assignment for switch in chosen), base]) if base else ""


class SwitchesDialog(QDialog):
    def __init__(self, chosen: list[Switch], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(window_title("Switches"))
        lay = QVBoxLayout(self)
        intro = QLabel("For comparisons and for finding the cause of a problem in one game. Leave them all off to "
                       "play, unless the game needs one: off is the driver as DirectMesh ships it.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        self.boxes: dict[Switch, QCheckBox] = {}
        for switch in SWITCHES:
            box = QCheckBox(f"{switch.label} ({switch.assignment})")
            box.setChecked(switch in chosen)
            box.setToolTip(switch.help)
            help_text = QLabel(switch.help)
            help_text.setWordWrap(True)
            help_text.setStyleSheet("color:palette(placeholder-text); margin-left:24px;")
            lay.addWidget(box)
            lay.addWidget(help_text)
            self.boxes[switch] = box
        hint = QLabel("They go into the launch options: copy those again for the game after a change.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:palette(placeholder-text);")
        lay.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: [box.setChecked(False) for box in self.boxes.values()])
        lay.addWidget(buttons)
        self.resize(560, self.sizeHint().height())

    def chosen(self) -> list[Switch]:
        return [switch for switch, box in self.boxes.items() if box.isChecked()]
