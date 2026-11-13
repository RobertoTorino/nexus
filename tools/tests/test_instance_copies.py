# SPDX-License-Identifier: GPL-3.0-or-later
"""The apps that are not on bc250_core yet carry copies of core's instance.py, upstream.py, theme.py and exit_keys.py:
the copies must not drift. Only the SPDX line may differ (acpi is MIT)."""

from __future__ import annotations

from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[2]


def copies(name: str) -> list[Path]:
    """The apps' copies of core's *name*, in the suites on Nexus's core: a suite with a core of its own
    (<suite>/core/, tools/suites.py: the Bazzite Console Suite) keeps its copies in step with that one."""
    return sorted(p for p in SUITE.glob(f"*/apps/*/*/{name}") if not any((p.parents[3] / "core").glob("*/__init__.py")))


CORE = SUITE / "core" / "bc250_core" / "instance.py"
COPIES = copies("instance.py")
UPSTREAM = SUITE / "core" / "bc250_core" / "upstream.py"
UPSTREAM_COPIES = copies("upstream.py")
THEME = SUITE / "core" / "bc250_core" / "theme.py"
THEME_COPIES = copies("theme.py")
EXIT_KEYS = SUITE / "core" / "bc250_core" / "exit_keys.py"
EXIT_KEYS_COPIES = copies("exit_keys.py")


def body(path: Path) -> str:
    first, _, rest = path.read_text(encoding="utf-8").partition("\n")
    assert first.startswith("# SPDX-License-Identifier: "), path
    return rest


def test_copies_exist():
    packages = {p.parent.name for p in COPIES}
    assert {"upscaler", "cu_bisect", "cu_unlock", "cores_bisect",
            "cores_unlock", "oc_bisect", "locked_acpi"} <= packages
    assert {p.parent.name for p in UPSTREAM_COPIES} >= {"upscaler"}
    assert {p.parent.name for p in THEME_COPIES} == {p.parent.name for p in COPIES}
    assert {p.parent.name for p in EXIT_KEYS_COPIES} == {p.parent.name for p in COPIES}


@pytest.mark.parametrize("copy", [p for p in COPIES if p.parent.name != "gpu_governor"],
                         ids=lambda p: str(p.relative_to(SUITE)))
def test_copy_matches_core(copy):
    assert body(copy) == body(CORE), f"{copy.relative_to(SUITE)} differs from core/bc250_core/instance.py"


@pytest.mark.parametrize("copy", UPSTREAM_COPIES, ids=lambda p: str(p.relative_to(SUITE)))
def test_upstream_copy_matches_core(copy):
    assert body(copy) == body(UPSTREAM), f"{copy.relative_to(SUITE)} differs from core/bc250_core/upstream.py"


@pytest.mark.parametrize("copy", THEME_COPIES, ids=lambda p: str(p.relative_to(SUITE)))
def test_theme_copy_matches_core(copy):
    assert body(copy) == body(THEME), f"{copy.relative_to(SUITE)} differs from core/bc250_core/theme.py"


@pytest.mark.parametrize("copy", EXIT_KEYS_COPIES, ids=lambda p: str(p.relative_to(SUITE)))
def test_exit_keys_copy_matches_core(copy):
    assert body(copy) == body(EXIT_KEYS), f"{copy.relative_to(SUITE)} differs from core/bc250_core/exit_keys.py"
