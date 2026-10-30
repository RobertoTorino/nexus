# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract PKG on the handheld: a package (.pkg: a game, its update or add-on content) unpacked into a game folder in
the layout shadPS4 loads, as the BC250 suite's shadPS4 Manager's Extract PKG window does it (its extract_dialog.py,
ExtractionWorker in normal mode) with the same pkgxtractor. The window runs it off its thread and shows the files
done; there is no preview, salvage mode, comparison or renaming here (the BC250 window's tools for a damaged or
unknown package).

The packages are the ones put in the game folders (owner, 30-10-2026: drop them there, the manager takes care of
them): waiting() finds those still to unpack, place() says where each goes. A game goes into a folder named by its
title ID (CUSA00001) beside its package; an update (CATEGORY gp) beside its game, in a folder named like the game's
with -UPDATE, which shadPS4 lays over the game when it starts (fs.cpp in 0.20.0), so the game stays as it was. Without
its game a gp package goes into CUSA00001: a game with its update in it says gp too. A folder that is there already is
never written into, except an older update: the new one is unpacked into a folder beside it and takes its place only
when every file was written, else the old one stays."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .pkgxtractor.pkg import PKG, PKGError, is_pkg_file, sanitize_folder_name
from .games import read_sfo
from .pkgxtractor.psf import PSF, PSFError

PACKAGE_SUFFIXES = (".pkg",)            # what the browser shows when a package is looked for
ERRORS = "extraction_errors.txt"        # beside the files, when some could not be written (as the BC250 app)
FILE_LIST = "filelist.txt"
TRIES = 3                               # a package on an SD card that wakes up slowly: opened again after a moment

Progress = Callable[[int, int], None]   # files done, files in all


class ExtractError(Exception):
    pass


@dataclass(frozen=True)
class Package:
    """What a package says of itself before it is unpacked."""
    path: Path
    title_id: str
    title: str
    category: str                       # gd a game, gp an update, ac add-on content; "" when unknown
    version: str = ""                   # APP_VER: 01.05

    @property
    def kind(self) -> str:
        return {"gd": "game", "gp": "update", "ac": "add-on"}.get(self.category, "package")


def _open(pkg: PKG, path: Path) -> None:
    """The package opened, a few times when it does not open at once; ExtractError with the reason."""
    reason = ""
    for attempt in range(TRIES):
        try:
            pkg.open(path)
            return
        except PKGError as error:
            reason = str(error)
        if attempt < TRIES - 1:
            time.sleep(0.12)
    raise ExtractError(f"{path.name} could not be opened: {reason}")


def _category(sfo: bytes) -> tuple[str, str, str]:
    """(CATEGORY in lower case, TITLE, APP_VER) from the package's param.sfo; "" for what is not there."""
    if not sfo:
        return "", "", ""
    try:
        psf = PSF.from_bytes(sfo)
    except PSFError:
        return "", "", ""

    def clean(value: str | None) -> str:
        return (value or "").replace("\x00", "").strip()
    return (clean(psf.get_string("CATEGORY")).lower(), clean(psf.get_string("TITLE")),
            clean(psf.get_string("APP_VER")))


def read_package(path: Path) -> Package:
    """The package's title ID, title, category and version; ExtractError when it is not a package or cannot be read."""
    if not path.is_file() or not is_pkg_file(path):
        raise ExtractError(f"{path.name} is not a PS4 package.")
    with PKG() as pkg:
        _open(pkg, path)
        category, title, version = _category(pkg.sfo)
        return Package(path, pkg.title_id.replace("\x00", "").strip(), title, category, version)


_read: dict[tuple[str, int, int], Package | None] = {}     # waiting()'s packages read, by path, size and time
ORDER = {"gd": 0, "gp": 1}              # Unpack all unpacks the games first, so their updates find them


def _packages(root: Path, depth: int):
    try:
        entries = list(os.scandir(root))
    except OSError:
        return
    for entry in entries:
        if entry.name.lower().endswith(PACKAGE_SUFFIXES) and entry.is_file():
            yield entry
    if depth > 0:
        for entry in entries:
            if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".") and entry.name != "sce_sys":
                yield from _packages(Path(entry.path), depth - 1)


def update_folder(game: Path) -> Path:
    """Where shadPS4 0.20.0 looks for a game's update: a folder named like the game's with -UPDATE (fs.cpp)."""
    return game.with_name(f"{game.name}-UPDATE")


def _version(folder: Path) -> str:
    try:
        return str(read_sfo((folder / "sce_sys" / "param.sfo").read_bytes()).get("APP_VER") or "")
    except OSError:
        return ""


def waiting(folders: list[Path], unpacked: dict[str, Path], depth: int = 5) -> list[Package]:
    """The packages in the game folders (and up to *depth* folders below them, as games.scan looks) that wait to be
    unpacked (owner, 30-10-2026: drop a .pkg in the folder, the manager takes care of it): a game (gd) whose title ID
    is not in *unpacked* (title ID: its game's folder), an update (gp) unless its game has that version of it beside
    it already. An add-on (ac) is left out: shadPS4 keeps add-ons elsewhere, which the app does not unpack into; so is
    a file that is no package. Sorted as Unpack all takes them, the games first. A package is read once while it
    stays the same."""
    found: dict[str, Package] = {}
    for folder in folders:
        for entry in _packages(folder, depth):
            try:
                stat = entry.stat()
            except OSError:
                continue
            key = (os.path.normcase(entry.path), stat.st_size, stat.st_mtime_ns)
            if key not in _read:
                try:
                    _read[key] = read_package(Path(entry.path))
                except (ExtractError, OSError):
                    _read[key] = None
            package = _read[key]
            if package is None or package.category not in ORDER or not package.title_id:
                continue
            game = unpacked.get(package.title_id)
            if package.category == "gd" and game is not None:
                continue
            if (package.category == "gp" and game is not None and package.version
                    and _version(update_folder(game)) == package.version):
                continue
            found.setdefault(key[0], package)
    return sorted(found.values(), key=lambda p: (ORDER[p.category], (p.title or p.path.name).casefold(), str(p.path)))


def place(package: Package, unpacked: dict[str, Path]) -> tuple[Path, Path | None]:
    """Where a waiting package goes: (the folder it is unpacked into, its game's folder for an update beside it, else
    None). A game goes into a folder named by its title ID beside the package; an update beside its game, wherever
    that is; an update without its game is a game of its own (a game with its update in it says gp too)."""
    game = unpacked.get(package.title_id) if package.category == "gp" else None
    if game is not None:
        return update_folder(game), game
    return package.path.parent / sanitize_folder_name(package.title_id or "unknown_title"), None


def _is_dir(folder: Path) -> bool:
    try:
        return folder.is_dir()
    except OSError:                                 # an SD card that cannot be read: no folder to replace
        return False


def has_entries(folder: Path) -> bool:
    """Whether *folder* is there and not empty (a file in its place counts as full)."""
    try:
        if not folder.exists():
            return False
        if not folder.is_dir():
            return True
        with os.scandir(folder) as entries:
            return next(entries, None) is not None
    except OSError:
        return True


def target(output_root: Path, package: Package, beside: Path | None = None) -> tuple[Path, bool]:
    """The folder a package goes into, and whether it is an update beside its game (the BC250 app's
    extraction_target): beside *beside* when it is the game's folder (named as the user named it), else beside the
    title ID's folder in *output_root*."""
    if package.category == "gp" and beside is not None:
        return update_folder(beside), True
    game = output_root / sanitize_folder_name(package.title_id or "unknown_title")
    if package.category == "gp" and game.is_dir() and has_entries(game):
        return update_folder(game), True
    return game, False


def unpack(package: Package, output_root: Path, replace_update: bool = False, progress: Progress = lambda d, t: None,
           log: Callable[[str], None] = lambda line: None, beside: Path | None = None) -> tuple[Path, int, int]:
    """Unpack *package* into its folder in *output_root* (target). Returns (the folder, the files written, the files
    that failed); ExtractError when nothing could be unpacked, the folder is taken, or a replaced update failed (the
    old one then stays). *log* gets what the BC250 app's window logs, without a line per file."""
    final, update = target(output_root, package, beside)
    folder = final
    if has_entries(final):
        if not (update and replace_update and final.is_dir()):
            raise ExtractError(f"{final.name} is in {output_root.name or output_root} already: the app never writes "
                               "over a folder that is there.")
        folder = final.with_name(f".{final.name}.new")  # the new update first, beside the old one
        shutil.rmtree(folder, ignore_errors=True)
        log(f"Replacing the update in {final}: extracting into {folder.name} first.")
    elif update:
        log(f"An update for the game in {final.with_name(final.name.removesuffix('-UPDATE'))}: extracting into "
            f"{final.name}, which shadPS4 lays over the game.")
    with PKG() as pkg:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            pkg.extract(package.path, folder)
        except PKGError as error:
            if folder != final:
                shutil.rmtree(folder, ignore_errors=True)
            raise ExtractError(f"{package.path.name} could not be extracted: {error}") from error
        except OSError as error:
            raise ExtractError(f"{folder} could not be written: {error.strerror or error}") from error
        for warning in pkg.warnings:
            log(f"Warning: {warning}")
        total = pkg.num_files
        if not pkg.export_file_list(folder / FILE_LIST):
            log("The file list could not be written.")
        log(f"{package.path.name}: {total} file(s) into {folder}.")
        errors: list[str] = []
        for index in range(total):
            ok, reason = pkg.can_extract_file(index)
            if not ok:
                errors.append(f"File {index + 1}: {reason}; the extraction stopped there.")
                progress(index + 1, total)
                break
            try:
                pkg.extract_files(index)
            except Exception as error:  # noqa: BLE001 (recorded, and the next file follows: the BC250 app's way)
                errors.append(f"File {index + 1}: {error}")
            progress(index + 1, total)
    written = total - len(errors)
    if errors:
        try:
            (folder / ERRORS).write_text("pkgxtractor Extraction Error Report\n"
                                         "================================\n"
                                         f"PKG: {package.path}\nMode: normal\nTotal files: {total}\n"
                                         f"Error entries: {len(errors)}\n\n" + "\n".join(errors) + "\n",
                                         encoding="utf-8")
        except OSError:
            log(f"{ERRORS} could not be written.")
        for line in errors[:20]:
            log(line)
    if folder != final:
        if errors:
            shutil.rmtree(folder, ignore_errors=True)
            raise ExtractError(f"The new update could not be extracted ({len(errors)} file(s) failed): the update in "
                               f"{final.name} stays as it was.")
        old = final.with_name(f".{final.name}.old")
        shutil.rmtree(old, ignore_errors=True)
        final.rename(old)
        folder.rename(final)
        shutil.rmtree(old, ignore_errors=True)
        log(f"The new update replaced the old one in {final}.")
    return final, written, len(errors)
