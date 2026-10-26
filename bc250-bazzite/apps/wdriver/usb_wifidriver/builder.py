# SPDX-License-Identifier: GPL-3.0-or-later
"""Building the driver as your own user: the sources fetched into ~/.local/share/bc250-usb-wifi/src/<branch>, the
two modules built against the running kernel's build tree, and the result laid out for the loader:

    build/<branch>/<kernel>/aic_load_fw.ko, aic8800_fdrv.ko, build.log
    build/<branch>/<kernel>/fw/            the AIC8800D80 firmware, flat, with an aic8800D80 link to itself

The firmware layout is the driver's doing: the loader reads <aic_fw_path>/<file>, the Wi-Fi module appends
/aic8800D80 to the same variable (once per probe) and writes an RF calibration file there, so one folder with a
link to itself serves both (seen in the sources, 17-10-2026).

The sources come from a mirror under the suite owner's account first and from the upstream repository when the
mirror does not answer (owner, 17-10-2026: a vanished upstream must not stop a fresh install). Normally the pinned
commit is fetched; the "newest sources" choice fetches the branch's current head instead, untested, as a way out
when a new kernel breaks the pinned build before a release moves the pin.

The steps are command lines, run by the window one after the other with their output shown; nothing here runs
them, so the tests check the commands and the layout without git or a compiler."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

MIRROR = "https://github.com/RobertoTorino/aic8800d80"
UPSTREAM = "https://github.com/shenmintao/aic8800d80"
REMOTES = (("mirror", MIRROR), ("upstream", UPSTREAM))
FW_FOLDER = "aic8800D80"
MODULE_FILES = ("aic_load_fw/aic_load_fw.ko", "aic8800_fdrv/aic8800_fdrv.ko")
NEWEST = "newest"                               # in the commit file: the branch head was fetched, not the pin


@dataclass(frozen=True)
class Pin:
    branch: str
    commit: str
    date: str                                   # of the commit, DD-MM-YYYY
    chips: str                                  # which chips it is for


# shenmintao/aic8800d80 (GPL-2.0-only), the fork with the AIC8800D80 USB IDs, both firmware sets and fixes for
# kernels up to 7.3 (checked 17-10-2026). The owner's UGREEN AX900 reports chip_mcu_id 1 and runs on legacy-mcu1.
PINS = {
    "main": Pin("main", "43db8006cb9b5fcd2b3191ecb7e3ea5962d39aaa", "08-10-2026",
                "chips that report chip_mcu_id 0, or an unknown MCU"),
    "legacy-mcu1": Pin("legacy-mcu1", "1d1b8fff4627857484758d7b8a5f24ac929b933e", "08-10-2026",
                       "chips that report chip_mcu_id 1 (the UGREEN AX900)"),
}
BRANCHES = tuple(PINS)


@dataclass(frozen=True)
class Step:
    """One command of the build; when it fails and a fallback is given, the fallback runs in its place."""
    argv: list[str]
    fallback: list[str] | None = None
    note: str = ""                              # shown before the fallback runs


@dataclass(frozen=True)
class Layout:
    data_home: Path                             # ~/.local/share/bc250-usb-wifi
    branch: str
    kernel: str
    newest: bool = False                        # the branch head instead of the pin

    @property
    def source(self) -> Path:
        return self.data_home / "src" / self.branch

    @property
    def output(self) -> Path:
        return self.data_home / "build" / (f"{self.branch}-{NEWEST}" if self.newest else self.branch) / self.kernel

    @property
    def module_dir(self) -> Path:
        return self.source / "drivers" / "aic8800"

    @property
    def firmware(self) -> Path:
        return self.source / "fw" / FW_FOLDER

    @property
    def commit_file(self) -> Path:
        return self.source / ".bc250-commit"

    @property
    def wanted(self) -> str:
        """What the source folder should hold: the pin's hash, or NEWEST."""
        return NEWEST if self.newest else PINS[self.branch].commit


def checked_out(layout: Layout) -> str:
    """What the source folder holds: the pin's hash, NEWEST, or "" when nothing is marked."""
    try:
        return layout.commit_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def head_commit(layout: Layout) -> str:
    """The commit git has checked out (detached after a checkout of FETCH_HEAD), "" when unknown."""
    try:
        head = (layout.source / ".git/HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return head if len(head) == 40 and not head.startswith("ref:") else ""


def source_commit(layout: Layout) -> str:
    """The commit the sources are at: the pin, or for the newest sources what git checked out."""
    return head_commit(layout) if layout.newest else PINS[layout.branch].commit


def fetch_steps(layout: Layout) -> list[Step]:
    """git commands that put the wanted sources in the source folder: a shallow fetch of one commit (GitHub serves
    a commit by its hash), or of the branch head for the newest sources, from the mirror and from upstream when
    the mirror fails. Nothing when the pinned commit is there already; the newest sources are always fetched
    again, they may have moved."""
    if not layout.newest and checked_out(layout) == layout.wanted and layout.module_dir.is_dir():
        return []
    src = str(layout.source)
    steps: list[Step] = []
    if not (layout.source / ".git").is_dir():
        steps.append(Step(["git", "init", "-q", src]))
        for name, url in REMOTES:
            steps.append(Step(["git", "-C", src, "remote", "add", name, url]))
    what = layout.branch if layout.newest else PINS[layout.branch].commit
    fetch = ["git", "-C", src, "fetch", "-q", "--depth", "1"]
    steps.append(Step(fetch + ["mirror", what], fallback=fetch + ["upstream", what],
                      note=f"The mirror {MIRROR} did not answer; fetching from {UPSTREAM} instead."))
    steps.append(Step(["git", "-C", src, "checkout", "-q", "--force", "FETCH_HEAD"]))
    return steps


def mark_checked_out(layout: Layout) -> None:
    layout.commit_file.write_text(layout.wanted + "\n", encoding="utf-8")


def make_step(layout: Layout, build_tree: Path, jobs: int | None = None) -> Step:
    """The kernel's own build system builds the modules in place (as the fork's Makefile does)."""
    return Step(["make", "-C", str(build_tree), f"M={layout.module_dir}", f"-j{jobs or os.cpu_count() or 2}",
                 "modules"])


def built_modules(layout: Layout) -> list[Path]:
    return [layout.module_dir / f for f in MODULE_FILES]


def collect(layout: Layout) -> str:
    """The built modules and the firmware into the output folder. Returns what is missing, "" when all is there."""
    missing = [p.name for p in built_modules(layout) if not p.is_file()]
    if missing:
        return f"The build left no {', '.join(missing)}: see the build log."
    if not layout.firmware.is_dir():
        return f"The sources have no {FW_FOLDER} firmware folder."
    shutil.rmtree(layout.output, ignore_errors=True)
    layout.output.mkdir(parents=True)
    for module in built_modules(layout):
        shutil.copy2(module, layout.output / module.name)
    place_firmware(layout.firmware, layout.output / "fw")
    (layout.output / "commit").write_text(source_commit(layout) + "\n", encoding="utf-8")
    return ""


def output_commit(folder: Path) -> str:
    """The commit a build output was made from, "" when unknown."""
    try:
        return (folder / "commit").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def place_firmware(source: Path, target: Path) -> None:
    """The firmware files flat in target, with the aic8800D80 link to the folder itself (see the module docstring)."""
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for f in sorted(source.iterdir()):
        if f.is_file():
            shutil.copy2(f, target / f.name)
    (target / FW_FOLDER).symlink_to(".")


def complete(folder: Path) -> bool:
    """Whether a build output folder holds both modules and the firmware."""
    return all((folder / Path(f).name).is_file() for f in MODULE_FILES) and (folder / "fw" / FW_FOLDER).exists()
