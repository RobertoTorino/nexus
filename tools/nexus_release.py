#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Which suites a Nexus release carries (owner, 30-10-2026: "if we have 10 suites and only 1 has a change only the
Nexus workflow and that suite's workflow will run"), for .github/workflows/release-nexus.yml:

    python3 tools/nexus_release.py suites       # suites=<JSON list>, for $GITHUB_OUTPUT

A suite is carried when it is on the Nexus release (its release-<suite>.yml can be called: workflow_call) and its
portal version (<suite>/portal/VERSION) has no published release yet: every app release of a suite comes with a
portal release that pins it, so a suite whose portal is out has nothing to release. A draft counts as not released
(the device test did not say yes yet). A suite not on the Nexus release yet (bc250-bazzite, until stage 3 of the
release redesign) keeps releasing by the tags pushed by hand. GitHub is asked with the gh CLI (GH_TOKEN)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nexus_suites = _load("nexus_suites", ROOT / "tools" / "suites.py")


def published(tag: str) -> bool:
    """Whether *tag* has a release on GitHub that is not a draft."""
    result = subprocess.run(["gh", "release", "view", tag, "--json", "isDraft", "--jq", ".isDraft"],
                            capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "false"


def release_workflow(root: Path, folder: Path) -> Path:
    return root / ".github" / "workflows" / f"release-{folder.name}.yml"


def on_nexus_release(root: Path, folder: Path) -> bool:
    """Whether release-nexus.yml can call the suite's release workflow."""
    workflow = release_workflow(root, folder)
    return workflow.is_file() and "workflow_call:" in workflow.read_text(encoding="utf-8")


def portal_tag(folder: Path) -> str:
    version = (folder / "portal" / "VERSION").read_text(encoding="utf-8").strip()
    return f"{nexus_suites.tag_prefix(folder)}portal-v{version}"


def carried(root: Path = ROOT, released: Callable[[str], bool] = published) -> list[str]:
    """The suites the Nexus release carries, by folder name."""
    return [folder.name for folder in nexus_suites.suites(root)
            if on_nexus_release(root, folder) and not released(portal_tag(folder))]


def main(argv: list[str]) -> int:
    if argv != ["suites"]:
        print(__doc__.strip().splitlines()[4].strip(), file=sys.stderr)
        return 2
    print(f"suites={json.dumps(carried())}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
