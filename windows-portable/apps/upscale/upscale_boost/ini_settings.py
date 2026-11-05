# SPDX-License-Identifier: GPL-3.0-or-later
"""helixsr.ini's settings as the Settings card shows them: the BC-250 Upscaler Manager's helixsr.ini page (a form of
combo boxes, spin boxes, check boxes and two text fields) as rows a controller steps through, in tabs (LB and RB).
A on a row steps to its next value (a number through the values that make sense, a DLL name through the names
HelixSR's README uses), as Xenia Manager's settings do. Every row is a field of backend.HelixIni; the rows the
payload's HelixSR does not read are left out (backend.ini_ignored_fields), where the BC250 app grayed them out.

Qt-free."""

from __future__ import annotations

from dataclasses import dataclass

from .backend import NETWORKS, SECOND_UPSCALER_DLL, SHARPENERS, SHARPENING_MODES, HelixIni, ini_ignored_fields


@dataclass(frozen=True)
class Setting:
    key: str                        # the HelixIni field
    label: str
    values: tuple                   # what A steps through, in order
    tip: str

    def shown(self, value: object) -> str:
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, float):
            text = f"{value:.2f}".rstrip("0").rstrip(".")
            return text or "0"
        return str(value) or "default"

    def next_value(self, value: object) -> object:
        """The value after *value*; one that is not among the values (written by hand) steps to the next larger one,
        else to the first."""
        if value in self.values:
            return self.values[(self.values.index(value) + 1) % len(self.values)]
        if isinstance(value, float) and not isinstance(value, bool):
            return next((v for v in self.values if v > value), self.values[0])
        return self.values[0]


def _steps(low: float, high: float, step: float) -> tuple[float, ...]:
    count = round((high - low) / step)
    return tuple(round(low + n * step, 4) for n in range(count + 1))


ON_OFF = (True, False)
FORWARDING = ("", "amd_fidelityfx_dx12.original.dll", "amd_fidelityfx_framegeneration_dx12.dll")

SHARPENING = (
    Setting("sharpening_mode", "Mode", SHARPENING_MODES,
            "off: never sharpen (DLSS's network does not). game: the game's FSR sharpness, or Sharpness below if it "
            "sends none. override: always Sharpness below."),
    Setting("sharpener", "Sharpener", SHARPENERS,
            "off (as DLSS 4), nvidia (NVIDIA's sharpening filter, as the driver's Image Sharpening) or rcas (AMD "
            "FSR's)."),
    Setting("sharpness", "Sharpness", _steps(0.0, 1.0, 0.1), "0 = none, 1 = strongest (FidelityFX scale)."),
    Setting("use_game_slider", "Use the game's slider", (False, True),
            "Follow the game's sharpness slider when it has one."),
    Setting("motion_adaptive", "Motion adaptive", ON_OFF, "Less sharpening on fast-moving pixels."),
    Setting("motion_threshold", "Motion threshold", (0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 8.0),
            "Motion in output pixels per frame where the reduction starts."),
    Setting("motion_limit", "Motion limit", (8.0, 12.0, 16.0, 24.0, 32.0, 48.0),
            "Motion where the reduction is complete; above the threshold."),
    Setting("motion_reduction", "Motion reduction", _steps(0.0, 1.0, 0.1),
            "Fraction of sharpening removed at and above the motion limit."),
)
MODEL_E = (
    Setting("model_e_enabled", "Model E network", ON_OFF,
            "Run the Model E network. Off, or while the network is missing, a placeholder upscale is used."),
    Setting("network", "Network", NETWORKS,
            "auto: the main network at every scale ratio (faster than the Ultra Performance network on GPUs without "
            "matrix cores). nvidia: as DLSS selects it. Or force one."),
    Setting("invert_jitter", "Invert jitter", (False, True), "When the game's jitter comes out mirrored."),
    Setting("invert_motion_vectors", "Invert motion vectors", (False, True),
            "When the game's motion vectors come out mirrored."),
    Setting("motion_vector_front_end", "Motion vector front end", (False, True),
            "Convert render-resolution motion vectors first. Used anyway when the game's vectors include the jitter; "
            "otherwise NVIDIA's render-resolution path is faster."),
)
MORE = (
    Setting("log_enabled", "helixsr.log", ON_OFF, "Write helixsr.log next to the DLL: attach it to a problem report."),
    Setting("forwarding_dll", "Forwarding DLL", FORWARDING,
            "The DLL that serves FidelityFX effects other than upscaling (frame generation). default: "
            "amd_fidelityfx_dx12.original.dll if present, else amd_fidelityfx_framegeneration_dx12.dll."),
    Setting("upscaler_dll", "Second upscaler", ("", SECOND_UPSCALER_DLL),
            "A second FidelityFX upscaler DLL (e.g. AMD's with FSR 4) listed after HelixSR in OptiScaler's menu. "
            "default: HelixSR only. The OptiScaler page puts that DLL into a game's HelixSR folder."),
)
TABS = (("sharpening", "Sharpening", SHARPENING), ("model", "Model E", MODEL_E), ("more", "More", MORE))
SETTINGS = (*SHARPENING, *MODEL_E, *MORE)


def shown_settings(version: str) -> list[Setting]:
    """The rows the payload's HelixSR *version* reads (all of them for an unknown version)."""
    ignored = ini_ignored_fields(version)
    return [s for s in SETTINGS if s.key not in ignored]


def value(settings: HelixIni, setting: Setting) -> object:
    return getattr(settings, setting.key)
