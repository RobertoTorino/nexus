# SPDX-License-Identifier: GPL-3.0-or-later
"""Every README's badges (owner, 28-10-2026: every README gets a beta, a workflow status and a license badge at the
top): above its title, the Beta badge in its system's color (a design per system: the BC250 suite's purple, the
Windows Portable Suite's amber, Nexus's teal), the CI workflow that tests its folder, and its license as its SPDX line
and its LICENSE say."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COLORS = {"bc250-bazzite": "8b4fd8", "windows-portable": "f5a524"}         # every other folder is Nexus's
NEXUS = "17b6a7"
WORKFLOWS = {"bc250-bazzite": "ci.yml", "windows-portable": "ci-windows-portable.yml"}
# The first line of a LICENSE file, and the SPDX identifiers it may stand for
FAMILIES = {"GNU GENERAL PUBLIC LICENSE Version 3": ("GPL-3.0-only", "GPL-3.0-or-later"),
            "GNU AFFERO GENERAL PUBLIC LICENSE Version 3": ("AGPL-3.0-only", "AGPL-3.0-or-later"),
            "GNU GENERAL PUBLIC LICENSE Version 2": ("GPL-2.0-only", "GPL-2.0-or-later"),
            "MIT License": ("MIT",)}
LICENSE_BADGE = re.compile(r"^\[!\[License: (\S+)\]\(https://img\.shields\.io/badge/license-(\S+)-blue\)\]\((\S+)\)$")
CI_BADGE = re.compile(r"^\[!\[[^\]]+\]\(https://github\.com/RobertoTorino/nexus/actions/workflows/([\w.-]+)/badge\.svg\)\]"
                      r"\(https://github\.com/RobertoTorino/nexus/actions/workflows/([\w.-]+)\)$")


def readmes() -> list[str]:
    return subprocess.run(["git", "ls-files", "*README.md"], cwd=ROOT, capture_output=True, text=True).stdout.split()


def family(license_file: Path) -> tuple[str, ...]:
    words = " ".join(license_file.read_text(encoding="utf-8").split()[:8])
    return next(ids for start, ids in FAMILIES.items() if words.startswith(start))


def license_of(folder: Path) -> Path:
    while not (folder / "LICENSE").is_file():
        folder = folder.parent
    return folder / "LICENSE"


def test_every_readme_has_the_three_badges():
    names = readmes()
    assert "README.md" in names and len(names) > 30
    for name in names:
        path = ROOT / name
        lines = path.read_text(encoding="utf-8").split("\n")
        spdx = re.match(r"^<!-- SPDX-License-Identifier: (\S+) -->$", lines[0])
        assert spdx, f"{name}: no SPDX line first"
        top = lines[1:next(i for i, line in enumerate(lines) if line.startswith("# "))]
        badges = [line for line in top if line.strip()]
        system = name.split("/")[0]
        assert badges[0] == f"![Status: Beta](https://img.shields.io/badge/status-Beta-{COLORS.get(system, NEXUS)})", name
        workflows = [CI_BADGE.match(line) for line in badges[1:-1]]
        assert workflows and all(workflows), f"{name}: a CI badge"
        for found in workflows:
            assert found[1] == found[2] and (ROOT / ".github" / "workflows" / found[1]).is_file(), name
        wanted = {"README.md": {"ci-nexus.yml", "ci.yml", "ci-windows-portable.yml"}}.get(
            name, {WORKFLOWS.get(system, "ci-nexus.yml")})
        assert {found[1] for found in workflows} == wanted, name
        badge = LICENSE_BADGE.match(badges[-1])
        assert badge, f"{name}: the license badge last"
        identifier, shield, link = badge.groups()
        license_file = license_of(path.parent)
        assert identifier == spdx[1] and identifier in family(license_file), name
        assert shield == identifier.replace("-", "--").replace("_", "__"), name
        assert link == os.path.relpath(license_file, path.parent).replace(os.sep, "/"), name
