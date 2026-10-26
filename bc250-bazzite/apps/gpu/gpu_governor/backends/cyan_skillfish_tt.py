# SPDX-License-Identifier: GPL-3.0-or-later
"""Backend for cyan-skillfish-governor-tt, the older governor from the `tt` branch of
filippor/cyan-skillfish-governor. Same config layout for [timing], [frequency-thresholds], [load-target],
[temperature] and [[safe-points]] (but no timing.down-events), no [gpu-usage] fix, no [gpu] set-method, no
[frequency-range], no D-Bus; its own unit, package and config directory."""

from __future__ import annotations

from pathlib import Path

from .cyan_skillfish import SCHEMA, CyanSkillfishBackend

# default-config.toml of the tt branch (all active there).
DEFAULT_SAFE_POINTS_TT = ((350, 700), (500, 700), (1175, 700), (1400, 750), (1600, 800), (1700, 850),
                          (1850, 900), (2000, 950), (2050, 975), (2100, 1000), (2125, 1015), (2150, 1025),
                          (2200, 1045))
_TT_SECTIONS = ("timing.intervals", "timing", "timing.ramp-rates", "frequency-thresholds", "load-target",
                "temperature")


class CyanSkillfishTtBackend(CyanSkillfishBackend):
    name = "Cyan Skillfish GPU Governor (tt)"
    short_name = "tt"
    service_name = "cyan-skillfish-governor-tt.service"
    package_name = "cyan-skillfish-governor-tt"
    default_config_path = Path("/etc/cyan-skillfish-governor-tt/config.toml")
    schema = tuple(section.without("down_events") for section in SCHEMA if section.name in _TT_SECTIONS)
    features = frozenset()
    default_safe_points = DEFAULT_SAFE_POINTS_TT
    release_check = False       # the GitHub releases are the smu package; tt only ships through COPR
