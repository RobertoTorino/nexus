# SPDX-License-Identifier: GPL-3.0-or-later
"""Everything that touches files, without Qt: the imported HelixSR payload, finding a game's FSR 3.1 DLL,
the DLL swap (deploy / remove), the stand-alone folder for OptiScaler, a comment-keeping helixsr.ini editor,
the list of known deployments and the Steam libraries of the user.

HelixSR (github.com/lonewolf0622/HelixSR) is a drop-in replacement for a game's AMD FidelityFX upscaler DLL:
the game's amd_fidelityfx_upscaler_dx12.dll (or amd_fidelityfx_dx12.dll) is renamed to *.original.dll and
HelixSR's amd_fidelityfx_dx12.dll is copied in under the original name, together with the two network files the
one-time helixsr-setup builds on the PC (helixsr_weights.bin, helixsr_kernels.pak) and an optional helixsr.ini.
No launch options are needed."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Callable

from bc250_core.steam import write_atomic


HELIXSR_DLL = "amd_fidelityfx_dx12.dll"
UPSCALER_DLL = "amd_fidelityfx_upscaler_dx12.dll"
GAME_DLLS = (UPSCALER_DLL, HELIXSR_DLL)             # what a game ships, and what HelixSR replaces
# A second FidelityFX upscaler (e.g. AMD's FSR 4) next to HelixSR in a stand-alone folder, under the name HelixSR's
# README uses; helixsr.ini's [Forwarding] UpscalerDll points at it, and OptiScaler lists its upscalers after HelixSR.
SECOND_UPSCALER_DLL = "amd_fidelityfx_upscaler_dx12.amd.dll"
WEIGHTS = "helixsr_weights.bin"
KERNELS = "helixsr_kernels.pak"
NETWORK_FILES = (WEIGHTS, KERNELS)                  # built by helixsr-setup.sh, NVIDIA's property: never shipped
# From HelixSR 1.8 on the setup appends the network to the DLL instead ("one file"): [DLL][weights][pak] and a 32-byte
# footer that starts with this magic, followed by the two sizes and a format number (u64 each).
EMBED_MAGIC = b"HXSRNET1"
INI = "helixsr.ini"
LOG = "helixsr.log"
ORIGINAL_SUFFIX = ".original.dll"
PAYLOAD_DOCS = ("README.md", "LICENSE", "LICENSE-APACHE-2.0", "THIRD_PARTY_NOTICES.md", "SOURCE.md")
PAYLOAD_FILES = (HELIXSR_DLL, WEIGHTS, KERNELS, INI, *PAYLOAD_DOCS)
ESSENTIAL_FILES = (HELIXSR_DLL, WEIGHTS, KERNELS)
MAX_SCAN_DEPTH = 12
FSRFG = "HelixSR-fsrfg"                             # HelixSR 2's folder for its DLL in the release (and helixsr.ini)
MODE_REPLACE, MODE_FOLDER = "replace", "folder"

SHARPENING_MODES = ("off", "game", "override")
SHARPENERS = ("off", "nvidia", "rcas")              # HelixSR 1.8+: NVIDIA Image Scaling's sharpening or AMD's RCAS
NETWORKS = ("auto", "nvidia", "main", "ultraperformance")

# The helixsr.ini HelixSR 1.2.0 ships; used as the template when the payload has none.
DEFAULT_INI_TEXT = """\
; helixsr.ini - optional, next to the upscaler DLL. Every key has a default.

[Sharpening]
; game     = use the game's FSR sharpening setting; if the game sends none, use Sharpness below
; override = always use Sharpness below
; off      = never sharpen (default: DLSS's network does not sharpen)
Mode = off
; 0.0 - 1.0 (FidelityFX scale: 0 = none, 1 = strongest RCAS)
Sharpness = 0.3
; Less sharpening on fast-moving pixels (uses the game's motion vectors)
MotionAdaptive = true
; Motion in output pixels per frame where the reduction starts / is complete
MotionThreshold = 2
MotionLimit = 16
; Fraction of sharpening removed at and above MotionLimit (0 - 1)
MotionReduction = 0.6

[ModelE]
; Run the Model E network. While kernels are missing the placeholder upscale is used (see the log).
Enabled = true
; auto = the main network at every scale ratio (faster than the Ultra Performance network on GPUs without matrix
;        cores, same look in our tests); nvidia = as NVIDIA's DLSS (Ultra Performance network above a 2.5 ratio);
; or main / ultraperformance
Network = auto
; Sign conventions, if a game's jitter or motion vectors come out mirrored
InvertJitter = false
InvertMotionVectors = false
; Render-resolution motion vectors: false = NVIDIA's own render-resolution input path (default, fastest);
; true = convert them to display resolution first (used anyway when the game's vectors include the jitter)
MotionVectorFrontEnd = false

[Log]
; helixsr.log next to the DLL
Enabled = true

[Forwarding]
; DLL that serves FidelityFX effects other than upscaling (frame generation, ...).
; Default: amd_fidelityfx_dx12.original.dll if present, else amd_fidelityfx_framegeneration_dx12.dll.
Dll =
; Optional: another FidelityFX upscaler DLL (e.g. AMD's amd_fidelityfx_upscaler_dx12.dll with FSR 4). Its upscalers
; are listed after HelixSR (OptiScaler: "FFX Upscaler" menu), and the one you pick runs in that DLL.
; A name without a folder is looked up next to HelixSR. Empty (default): HelixSR only.
UpscalerDll =
"""


class HelixError(Exception):
    """A payload or deployment problem the user can act on; the message is shown as is."""


# ---------------------------------------------------------------------------------------------- files
def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same_file(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
        return file_digest(a) == file_digest(b)
    except OSError:
        return False


def network_embedded(dll: Path) -> bool:
    """True when the DLL carries HelixSR's network itself (HelixSR 1.8 and newer, after its setup)."""
    try:
        with open(dll, "rb") as handle:
            handle.seek(-32, os.SEEK_END)
            return handle.read(8) == EMBED_MAGIC
    except OSError:
        return False


_DLL_VERSION_RE = re.compile(rb"HelixSR (\d+\.\d+\.\d+)")


def dll_version(dll: Path) -> str:
    """The version a HelixSR DLL names in its first 4 MB ("HelixSR 1.9.3", from 1.4.3 on); "" for any other DLL."""
    try:
        with open(dll, "rb") as handle:
            match = _DLL_VERSION_RE.search(handle.read(4 << 20))
    except OSError:
        return ""
    return match.group(1).decode() if match else ""


def original_path(dll: Path) -> Path:
    """amd_fidelityfx_upscaler_dx12.dll -> amd_fidelityfx_upscaler_dx12.original.dll (the game's own file)."""
    return dll.with_name(dll.name[:-len(".dll")] + ORIGINAL_SUFFIX)


def to_windows_path(path: Path) -> str:
    """How Proton sees a Linux path: Z: is the Linux root."""
    return "Z:" + str(path.resolve()).replace("/", "\\")


# -------------------------------------------------------------------------------------------- payload
@dataclass
class PayloadStatus:
    path: Path
    dll: bool
    weights: bool
    kernels: bool
    ini: bool
    version: str = ""           # from the README.md that comes with the release, "" when unknown
    embedded: bool = False      # the network is inside the DLL (HelixSR 1.8+): no separate network files
    optiscaler: bool = False    # the payload has the OptiScaler that HelixSR 1.7+ ships

    @property
    def ready(self) -> bool:
        return self.dll and self.network_ready

    @property
    def network_ready(self) -> bool:
        return self.embedded or (self.weights and self.kernels)

    def missing(self) -> list[str]:
        network = () if self.embedded else ((WEIGHTS, self.weights), (KERNELS, self.kernels))
        return [name for name, have in ((HELIXSR_DLL, self.dll), *network) if not have]


def payload_version(payload_dir: Path) -> str:
    readme = payload_dir / "README.md"
    try:
        match = re.search(r"\*\*Version (\d+(?:\.\d+)+)", readme.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""
    return match.group(1) if match else ""


def version_key(version: str) -> tuple[int, ...]:
    """The x.y.z in a version text as a tuple, e.g. (1, 4, 3); () when there is none."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version or "")
    return tuple(int(p) for p in match.groups()) if match else ()


def ini_ignored_fields(version: str) -> set[str]:
    """The HelixIni fields HelixSR *version* does not read (nothing for an unknown version). 1.7 behaves like DLSS and
    ignores sharpening and the network choice ("helixsr.ini's sharpening / network settings are ignored" in its
    log); 1.8 brings sharpening back with Sharpener and UseGameSlider instead of Mode."""
    key = version_key(version)
    if not key:
        return set()
    if key < (1, 7, 0):
        return set(NEW_IN_1_8)
    if key < (1, 8, 0):
        return {name for section, _, name in INI_SCHEMA if section == "Sharpening"} | {"network"}
    return {"sharpening_mode", "network"}


def payload_folder(release_dir: Path) -> Path:
    """Where an extracted release keeps HelixSR's DLL: HelixSR-fsrfg/ from 2.0 on, the release folder before."""
    return release_dir / FSRFG if (release_dir / FSRFG / HELIXSR_DLL).is_file() else release_dir


def payload_status(payload_dir: Path) -> PayloadStatus:
    have = lambda name: (payload_dir / name).is_file()
    return PayloadStatus(payload_dir, have(HELIXSR_DLL), have(WEIGHTS), have(KERNELS), have(INI),
                         payload_version(payload_dir), network_embedded(payload_dir / HELIXSR_DLL),
                         optiscaler_available(payload_dir))


@dataclass
class ImportResult:
    copied: list[str]
    missing: list[str]          # essential files the source did not have


def _find_payload_files(source: Path, max_depth: int = 3) -> dict[str, Path]:
    """The known HelixSR files under source, shallowest match wins (the release zip extracts into one folder,
    the network files appear next to the DLL after the setup)."""
    wanted = {name.lower(): name for name in PAYLOAD_FILES}
    found: dict[str, Path] = {}
    base_depth = len(source.parts)
    for root, dirs, files in os.walk(source):
        depth = len(Path(root).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        dirs.sort()
        for file in files:
            name = wanted.get(file.lower())
            if name and name not in found:
                found[name] = Path(root) / file
    return found


def import_payload(source: Path, payload_dir: Path) -> ImportResult:
    """Copy the HelixSR files from an extracted release folder (or the release zip) into the payload folder.
    Only the known files are taken, nothing else; existing payload files are replaced."""
    if not source.exists():
        raise HelixError("{0} does not exist.".format(source))
    payload_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if source.is_file():
        if not zipfile.is_zipfile(source):
            raise HelixError("{0} is not a zip archive or a folder."
                             .format(source.name))
        wanted = {name.lower(): name for name in PAYLOAD_FILES}
        with zipfile.ZipFile(source) as archive:
            for member in sorted(archive.infolist(), key=lambda m: m.filename.count("/")):
                name = wanted.get(Path(member.filename).name.lower())
                if member.is_dir() or not name or name in copied:
                    continue
                with archive.open(member) as src, open(payload_dir / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                copied.append(name)
    else:
        for name, path in _find_payload_files(source).items():
            shutil.copy2(path, payload_dir / name)
            copied.append(name)
    if HELIXSR_DLL not in copied:
        raise HelixError(("No {0} found in {1}. Pick the folder the HelixSR release was extracted to (or the release "
                          "zip itself).").format(HELIXSR_DLL, source))
    copied += _import_optiscaler(source, payload_dir)
    if network_embedded(payload_dir / HELIXSR_DLL):
        # One-file DLL: network files left from an earlier release belong to another build, and Deploy would copy them.
        for name in NETWORK_FILES:
            if name not in copied:
                (payload_dir / name).unlink(missing_ok=True)
        return ImportResult(copied, [])
    missing = [name for name in ESSENTIAL_FILES if name not in copied and not (payload_dir / name).is_file()]
    return ImportResult(copied, missing)


def _import_optiscaler(source: Path, payload_dir: Path) -> list[str]:
    """The release's optiscaler folder (HelixSR 1.7+: the official OptiScaler with fakenvapi) into the payload.
    A release without one leaves the payload's as it is: OptiScaler works with any HelixSR."""
    wanted = {name.lower(): name for name in OPTISCALER_FILES}
    found: dict[str, bytes | Path] = {}
    if source.is_file():
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                parts = Path(member.filename).parts
                name = wanted.get(parts[-1].lower()) if len(parts) >= 2 and parts[-2] == OPTISCALER_DIR else None
                if name and not member.is_dir() and name not in found:
                    found[name] = archive.read(member)
    else:
        folder = next((d for d in (source / OPTISCALER_DIR, *(c / OPTISCALER_DIR for c in sorted(source.iterdir())
                                                                if c.is_dir())) if d.is_dir()), None)
        for name in OPTISCALER_FILES if folder else ():
            if (folder / name).is_file():
                found[name] = folder / name
    if not all(name in found for name in ("OptiScaler.dll", "OptiScaler.ini")):
        return []
    target = payload_dir / OPTISCALER_DIR
    target.mkdir(parents=True, exist_ok=True)
    for name, data in found.items():
        if isinstance(data, Path):
            shutil.copy2(data, target / name)
        else:
            (target / name).write_bytes(data)
    return [f"{OPTISCALER_DIR}/{name}" for name in found]


# ------------------------------------------------------------------------------------- game discovery
@dataclass
class GameDll:
    """One FSR 3.1 upscaler DLL found in a game folder, with what is next to it."""

    path: Path
    has_backup: bool            # *.original.dll exists: HelixSR (some build) replaced the game's file
    matches_payload: bool       # the file is byte-identical to the payload's DLL
    network_files: bool         # weights and kernels next to it, or the network inside the DLL
    ini: bool
    restored: bool = False      # a backup is there, but the DLL is the game's again (a game update or a Steam check)

    @property
    def original(self) -> Path:
        return original_path(self.path)

    @property
    def deployed(self) -> bool:
        return self.has_backup or self.matches_payload

    @property
    def state(self) -> str:
        if self.has_backup and self.matches_payload:
            return "HelixSR deployed"
        if self.restored:
            return "Game's own DLL again"
        if self.has_backup:
            return "HelixSR deployed (other build)"
        if self.matches_payload:
            return "HelixSR (no original kept)"
        return "Game's own DLL"


def inspect_dll(path: Path, payload_dir: Path) -> GameDll:
    folder = path.parent
    payload_dll = payload_dir / HELIXSR_DLL
    has_backup = original_path(path).is_file()
    matches = payload_dll.is_file() and same_file(path, payload_dll)
    embedded = network_embedded(path)
    return GameDll(path, has_backup, matches,
                   all((folder / name).is_file() for name in NETWORK_FILES) or embedded,
                   (folder / INI).is_file(), has_backup and not matches and not embedded and not dll_version(path))


def find_game_dlls(game_dir: Path, payload_dir: Path, max_depth: int = MAX_SCAN_DEPTH,
                   cancelled: Callable[[], bool] | None = None) -> list[GameDll]:
    """Every amd_fidelityfx_upscaler_dx12.dll / amd_fidelityfx_dx12.dll under the game folder (Unreal games keep
    it under Engine/Plugins/.../ThirdParty/Win64), shallowest first. *.original.dll backups are not listed.
    *canceled* stops the walk early (what was found so far is returned)."""
    names = {name.lower() for name in GAME_DLLS}
    found: list[Path] = []
    base_depth = len(game_dir.parts)
    for root, dirs, files in os.walk(game_dir):
        if cancelled is not None and cancelled():
            break
        depth = len(Path(root).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        dirs.sort()
        for file in files:
            if file.lower() in names:
                found.append(Path(root) / file)
    found.sort(key=lambda p: (len(p.parts), str(p).lower()))
    return [inspect_dll(path, payload_dir) for path in found]


# ------------------------------------------------------------------------------------- deploy / remove
def _require_ready(payload_dir: Path) -> PayloadStatus:
    status = payload_status(payload_dir)
    if not status.ready:
        raise HelixError(("The payload is incomplete, missing: {0}. Import the extracted HelixSR release after running "
                          "its helixsr-setup.sh.").format(", ".join(status.missing())))
    return status


def _copy_support_files(folder: Path, payload_dir: Path, ini_text: str | None) -> list[Path]:
    written = []
    embedded = network_embedded(payload_dir / HELIXSR_DLL)
    for name in NETWORK_FILES:
        if embedded:                            # the DLL carries the network; files of an earlier build would be stale
            (folder / name).unlink(missing_ok=True)
            continue
        shutil.copy2(payload_dir / name, folder / name)
        written.append(folder / name)
    if ini_text is not None:
        (folder / INI).write_text(ini_text, encoding="utf-8")
        written.append(folder / INI)
    elif (payload_dir / INI).is_file():
        shutil.copy2(payload_dir / INI, folder / INI)
        written.append(folder / INI)
    return written


def deploy(target: Path, payload_dir: Path, ini_text: str | None = None) -> list[Path]:
    """Replace the game's upscaler DLL at `target` with HelixSR. The game's file is kept as *.original.dll (an
    existing backup is never overwritten, so re-deploying a newer HelixSR build keeps the real original).
    Returns the files written."""
    _require_ready(payload_dir)
    if target.name.lower() not in {n.lower() for n in GAME_DLLS}:
        raise HelixError("{0} is not an FSR 3.1 upscaler DLL ({1})."
                         .format(target.name, " / ".join(GAME_DLLS)))
    if not target.is_file():
        raise HelixError("{0} does not exist.".format(target))
    backup = original_path(target)
    if not backup.exists():
        target.rename(backup)
    shutil.copy2(payload_dir / HELIXSR_DLL, target)
    return [target, *_copy_support_files(target.parent, payload_dir, ini_text)]


def remove(target: Path, payload_dir: Path) -> list[Path]:
    """Undo deploy(): delete HelixSR's files next to `target` and rename *.original.dll back. Refuses when
    `target` is neither a known HelixSR build (no backup) nor identical to the payload DLL."""
    backup = original_path(target)
    payload_dll = payload_dir / HELIXSR_DLL
    if not backup.exists() and not (payload_dll.is_file() and target.is_file() and same_file(target, payload_dll)):
        raise HelixError("{0} is not HelixSR (no {1} next to it and it differs from the payload). Nothing was changed."
            .format(target.name, backup.name))
    removed = []
    for name in (*NETWORK_FILES, INI, LOG):
        path = target.parent / name
        if path.exists():
            path.unlink()
            removed.append(path)
    if target.exists():
        target.unlink()
        removed.append(target)
    if backup.exists():
        backup.rename(target)
    return removed


def deploy_folder(folder: Path, payload_dir: Path, ini_text: str | None = None,
                  second_upscaler: Path | None = None) -> list[Path]:
    """Stand-alone HelixSR folder for OptiScaler: the DLL under both FidelityFX names (OptiScaler reads
    FfxDx12Path and FfxDx12SRPath), the network files and the ini. With *second_upscaler* (another FidelityFX
    upscaler DLL, e.g. AMD's with FSR 4) that DLL is copied in as SECOND_UPSCALER_DLL and the ini's UpscalerDll
    points at it; without, a second upscaler left from an earlier deploy is removed (and UpscalerDll cleared when
    it named it)."""
    _require_ready(payload_dir)
    if second_upscaler is not None:
        if not second_upscaler.is_file():
            raise HelixError("{0} does not exist.".format(second_upscaler))
        if same_file(second_upscaler, payload_dir / HELIXSR_DLL):
            raise HelixError("{0} is HelixSR itself; pick another FidelityFX upscaler DLL, e.g. AMD's with FSR 4."
                .format(second_upscaler))
        settings = parse_ini(ini_text if ini_text is not None else ini_template(payload_dir))
        settings.upscaler_dll = SECOND_UPSCALER_DLL
        ini_text = render_ini(settings, ini_text if ini_text is not None else ini_template(payload_dir))
    elif ini_text is not None and parse_ini(ini_text).upscaler_dll == SECOND_UPSCALER_DLL:
        settings = parse_ini(ini_text)          # the second upscaler goes: do not leave the ini pointing at it
        settings.upscaler_dll = ""
        ini_text = render_ini(settings, ini_text)
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name in GAME_DLLS:
        shutil.copy2(payload_dir / HELIXSR_DLL, folder / name)
        written.append(folder / name)
    second = folder / SECOND_UPSCALER_DLL
    if second_upscaler is not None:
        if second_upscaler.resolve() != second.resolve():
            shutil.copy2(second_upscaler, second)
        written.append(second)
    elif second.exists():
        second.unlink()
    return [*written, *_copy_support_files(folder, payload_dir, ini_text)]


def remove_folder(folder: Path, payload_dir: Path) -> list[Path]:
    """Delete the files deploy_folder() wrote (only those), put back what install_optiscaler() changed, and delete
    the folder when it is empty afterwards."""
    payload_dll = payload_dir / HELIXSR_DLL
    for name in GAME_DLLS:
        dll = folder / name
        if dll.is_file() and original_path(dll).exists():
            raise HelixError(("{0} holds a game's own {1} (there is a {2}): this is a replaced DLL, not a stand-alone "
                              "folder. Use Remove on the DLL instead.").format(folder, name, original_path(dll).name))
        if dll.is_file() and payload_dll.is_file() and not same_file(dll, payload_dll) and \
                not (folder / WEIGHTS).exists() and not network_embedded(dll):
            raise HelixError("{0} is not HelixSR; nothing was changed."
                             .format(dll))
    removed = uninstall_optiscaler(folder)
    for name in (*GAME_DLLS, SECOND_UPSCALER_DLL, *NETWORK_FILES, INI, LOG):
        path = folder / name
        if path.exists():
            path.unlink()
            removed.append(path)
    try:
        folder.rmdir()
    except OSError:
        pass
    return removed


def optiscaler_snippet(folder: Path) -> str:
    """The OptiScaler.ini lines that route a game's upscaler calls to this HelixSR folder."""
    win = to_windows_path(folder)
    return (f"[Upscalers]\nDx12Upscaler=fsr31\n\n[Libraries]\n"
            f"FfxDx12Path={win}\\{HELIXSR_DLL}\nFfxDx12SRPath={win}\\{UPSCALER_DLL}\n")


# ------------------------------------------------------------------------------------------- OptiScaler
# HelixSR 1.7+ ships the official OptiScaler with fakenvapi. Installed next to the game's .exe, it hands the game's
# DLSS (or XeSS / FSR 2) inputs to the stand-alone HelixSR folder through its FSR 3.1 backend, as HelixSR's own
# installer does it. What is replaced is kept in the HelixSR folder and put back on removal.
OPTISCALER_DIR = "optiscaler"                       # in the release and in the payload
OPTISCALER_FILES = ("OptiScaler.dll", "OptiScaler.ini", "fakenvapi.dll", "fakenvapi.ini", "LICENSE-GPL-3.0.txt",
                    "fakenvapi-LICENSE.txt")
OPTISCALER_INI = "OptiScaler.ini"
# The names a game loads OptiScaler under; a game that already has OptiScaler keeps its name, else dxgi.dll.
OPTISCALER_NAMES = ("dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "d3d12.dll", "wininet.dll", "winhttp.dll",
                    "OptiScaler.asi")
OPTISCALER_EXTRA = ("fakenvapi.dll", "fakenvapi.ini")   # OptiScaler loads fakenvapi on GPUs that are not NVIDIA's
OPTISCALER_MARKER = "bc250-optiscaler.json"         # in the HelixSR folder: what was installed where
OPTISCALER_BACKUP = "backup"                        # in the HelixSR folder: the game's files OptiScaler replaced
_SKIP_EXE = re.compile(r"unins|setup|redist|crash|launcher|vc_?redist|dxsetup|easyanticheat|beservice|dotnet|"
                       r"helper|report|prereq|install|7z|ue4prereq|cefprocess|webhelper", re.I)


def optiscaler_available(payload_dir: Path) -> bool:
    return all((payload_dir / OPTISCALER_DIR / name).is_file() for name in ("OptiScaler.dll", OPTISCALER_INI))


def is_optiscaler(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            return b"OptiScaler" in handle.read(32 << 20)
    except OSError:
        return False


def find_exe_folder(game_dir: Path, max_depth: int = 7) -> Path | None:
    """The folder of the game's main .exe, where OptiScaler goes: one that already has OptiScaler, else the one with
    the largest .exe that is no installer, launcher or helper (an Unreal *-Win64-Shipping.exe always wins)."""
    best, best_size = None, -1
    base_depth = len(game_dir.parts)
    for root, dirs, files in os.walk(game_dir):
        folder = Path(root)
        if len(folder.parts) - base_depth >= max_depth:
            dirs[:] = []
        dirs[:] = sorted(d for d in dirs if d.lower() != "helixsr")
        if OPTISCALER_INI in files:
            return folder
        for name in files:
            if not name.lower().endswith(".exe") or _SKIP_EXE.search(name):
                continue
            try:
                size = (folder / name).stat().st_size
            except OSError:
                continue
            if name.lower().endswith("-win64-shipping.exe"):
                size += 1 << 40
            if size > best_size:
                best, best_size = folder, size
    return best


def set_ini_value(text: str, key: str, value: str, section: str) -> str:
    """Sets "key=value" in OptiScaler.ini text, keeping its line endings; a missing key goes at the start of
    [section]."""
    pattern = re.compile(r"(?m)^(%s)[ \t]*=[^\r\n]*" % re.escape(key))
    if len(pattern.findall(text)) > 1:
        raise HelixError("{0} has more than one {1} line.".format(OPTISCALER_INI, key))
    if pattern.search(text):
        return pattern.sub(lambda m: f"{m.group(1)}={value}", text, count=1)
    header = re.search(r"(?m)^\[%s\][ \t]*(\r?\n)" % re.escape(section), text)
    if not header:
        raise HelixError("{0} has no [{1}] section.".format(OPTISCALER_INI, section))
    return text[:header.end()] + f"{key}={value}" + header.group(1) + text[header.end():]


def _read_raw(path: Path) -> str:
    return path.read_bytes().decode("utf-8", errors="surrogateescape")


def _write_raw(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8", errors="surrogateescape"))


def optiscaler_record(folder: Path) -> dict | None:
    try:
        return json.loads((folder / OPTISCALER_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def install_optiscaler(exe_dir: Path, folder: Path, payload_dir: Path) -> list[Path]:
    """OptiScaler next to the game's .exe, its OptiScaler.ini pointed at the HelixSR *folder*. A game's own file of
    the same name goes to <folder>/backup, an existing OptiScaler.ini is kept there as a copy and edited; again on
    the same folder it updates OptiScaler and keeps the record. Returns the files written."""
    if not optiscaler_available(payload_dir):
        raise HelixError("The payload has no OptiScaler. HelixSR 1.7.0 to 1.8.1 ship it: get or import such a release.")
    if not exe_dir.is_dir():
        raise HelixError("{0} does not exist.".format(exe_dir))
    if exe_dir.resolve() == folder.resolve():
        raise HelixError(("The HelixSR folder must not be the game's .exe folder: pick a folder of its own, such as "
                          "{0}.").format(exe_dir / "HelixSR"))
    source = payload_dir / OPTISCALER_DIR
    record = optiscaler_record(folder) or {}
    if record and Path(record.get("exe_dir", "")) != exe_dir:
        raise HelixError("This HelixSR folder already serves OptiScaler in {0}. Remove it there first."
            .format(record.get("exe_dir")))
    if not record:
        name = next((n for n in OPTISCALER_NAMES if (exe_dir / n).is_file() and is_optiscaler(exe_dir / n)), "dxgi.dll")
        record = {"exe_dir": str(exe_dir), "optiscaler": name, "moved": [], "created": [], "ini": "created"}
        backup = folder / OPTISCALER_BACKUP
        if (exe_dir / name).exists():
            backup.mkdir(parents=True, exist_ok=True)
            os.replace(exe_dir / name, backup / name)
            record["moved"].append(name)
        if (exe_dir / OPTISCALER_INI).is_file():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(exe_dir / OPTISCALER_INI, backup / OPTISCALER_INI)
            record["ini"] = "edited"
        for extra in OPTISCALER_EXTRA:
            if not (exe_dir / extra).exists():
                record["created"].append(extra)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / OPTISCALER_MARKER).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    written = []
    shutil.copy2(source / "OptiScaler.dll", exe_dir / record["optiscaler"])
    written.append(exe_dir / record["optiscaler"])
    for extra in record["created"]:
        if (source / extra).is_file():
            shutil.copy2(source / extra, exe_dir / extra)
            written.append(exe_dir / extra)
    ini = exe_dir / OPTISCALER_INI
    text = _read_raw(ini) if ini.is_file() else _read_raw(source / OPTISCALER_INI)
    win = to_windows_path(folder)
    text = set_ini_value(text, "Dx12Upscaler", "fsr31", "Upscalers")
    text = set_ini_value(text, "FfxDx12Path", f"{win}\\{HELIXSR_DLL}", "Libraries")
    text = set_ini_value(text, "FfxDx12SRPath", f"{win}\\{UPSCALER_DLL}", "Libraries")
    _write_raw(ini, text)
    written.append(ini)
    return written


def uninstall_optiscaler(folder: Path) -> list[Path]:
    """Undo install_optiscaler() for the HelixSR *folder*: OptiScaler, the files it created and its OptiScaler.ini
    go, the game's own files come back. Nothing happens without the record."""
    record = optiscaler_record(folder)
    if record is None:
        return []
    exe_dir = Path(record["exe_dir"])
    backup = folder / OPTISCALER_BACKUP
    removed = []
    names = [record["optiscaler"], *record.get("created", [])]
    if record.get("ini") == "created":
        names += [OPTISCALER_INI, "OptiScaler.log"]
    for name in names:
        if (exe_dir / name).exists():
            (exe_dir / name).unlink()
            removed.append(exe_dir / name)
    for name in [*record.get("moved", []), *([OPTISCALER_INI] if record.get("ini") == "edited" else [])]:
        if (backup / name).exists():
            os.replace(backup / name, exe_dir / name)
    (folder / OPTISCALER_MARKER).unlink()
    try:
        backup.rmdir()
    except OSError:
        pass
    return removed


# --------------------------------------------------------------------------------------- Steam launch options
# Under Proton Wine loads its own dxgi.dll, not the game's, so OptiScaler only loads with WINEDLLOVERRIDES="dxgi=n,b"
# in the game's launch options. Steam keeps them per user in userdata/<user>/config/localconfig.vdf, under
# UserLocalConfigStore/Software/Valve/Steam/apps/<AppID>/LaunchOptions, in the text key-value format. Steam writes
# that file again when it exits, so the window changes it with Steam closed (bc250_core.steam.with_steam_closed); the
# OptiScaler record in the HelixSR folder keeps what was there before, for Remove.
_VDF_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|//[^\n]*')
_APPS_PATH = ("userlocalconfigstore", "software", "valve", "steam", "apps")
_OVERRIDES = re.compile(r"""\bWINEDLLOVERRIDES=("[^"]*"|'[^']*'|\S*)""")


def _vdf_unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m[1], m[1]), text)


def _vdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _vdf_entries(text: str):
    """(path, key, kind, span) for every entry of a text key-value file; path holds the enclosing keys in lower case.
    A value's span covers it with its quotes, a block's (kind "block", given at its end) its inside, from after { to
    its }."""
    stack: list[tuple[str, int]] = []
    key: str | None = None
    for match in _VDF_TOKEN.finditer(text):
        string, brace = match.groups()
        if string is None and brace is None:            # a // comment
            continue
        if brace == "{":
            if key is None:
                raise HelixError("A Steam configuration file has a block without a name.")
            stack.append((key, match.end()))
            key = None
        elif brace == "}":
            if not stack or key is not None:
                raise HelixError("A Steam configuration file is not complete.")
            name, start = stack.pop()
            yield tuple(k.lower() for k, _ in stack), name, "block", (start, match.start())
        elif key is None:
            key = _vdf_unescape(string)
        else:
            yield tuple(k.lower() for k, _ in stack), key, "value", (match.start(), match.end())
            key = None
    if stack or key is not None:
        raise HelixError("A Steam configuration file is not complete.")


def _vdf_insert(text: str, close: int, lines: list[str]) -> str:
    """*lines* at the end of the block whose } is at *close*, one tab deeper than the }."""
    start = text.rfind("\n", 0, close) + 1
    indent, lead = text[start:close], ""
    if indent.strip():                                  # the } shares its line: start a new one
        start, indent, lead = close, "", "\n"
    return text[:start] + lead + "".join(f"{indent}\t{line}\n" for line in lines) + text[start:]


def launch_configs(steam: Path) -> list[Path]:
    """Every Steam user's localconfig.vdf."""
    return sorted(p for p in (steam / "userdata").glob("*/config/localconfig.vdf") if p.is_file())


def launch_options(config: Path, app_id: str) -> str:
    """The launch options of *app_id* in one localconfig.vdf, "" without."""
    text = _read_raw(config)
    for path, key, kind, (start, end) in _vdf_entries(text):
        if kind == "value" and path == (*_APPS_PATH, app_id) and key.lower() == "launchoptions":
            return _vdf_unescape(text[start + 1:end - 1])
    return ""


def set_launch_options(config: Path, app_id: str, value: str) -> None:
    """Sets the launch options of *app_id* in one localconfig.vdf: the value replaced, else added to the game's block,
    else a block for the game added to apps. The rest of the file stays byte for byte. Only with Steam closed."""
    text = _read_raw(config)
    quoted = f'"{_vdf_escape(value)}"'
    app = apps = None
    for path, key, kind, (start, end) in _vdf_entries(text):
        if kind == "value" and path == (*_APPS_PATH, app_id) and key.lower() == "launchoptions":
            text = text[:start] + quoted + text[end:]
            break
        if kind == "block" and path == _APPS_PATH and key == app_id:
            app = end
        elif kind == "block" and path == _APPS_PATH[:-1] and key.lower() == "apps":
            apps = end
    else:
        if app is not None:
            text = _vdf_insert(text, app, [f'"LaunchOptions"\t\t{quoted}'])
        elif apps is not None:
            text = _vdf_insert(text, apps, [f'"{app_id}"', "{", f'\t"LaunchOptions"\t\t{quoted}', "}"])
        else:
            raise HelixError("{0} has no list of games (apps); start the game once from Steam first.".format(config))
    write_atomic(config, text.encode("utf-8", errors="surrogateescape"))


def with_override(options: str, dll: str) -> str:
    """The launch options with *dll* (dxgi.dll) loaded from the game's folder first: dxgi=n,b in WINEDLLOVERRIDES,
    added to one that is there, else in front of the line. The rest of the line stays."""
    name = Path(dll).stem.lower()
    match = _OVERRIDES.search(options)
    if match:
        value = match.group(1).strip("\"'")
        names = {n.strip().lower() for part in value.split(";") for n in part.split("=")[0].split(",")}
        if name in names:
            return options
        merged = f'WINEDLLOVERRIDES="{name}=n,b' + (f";{value}" if value else "") + '"'
        return options[:match.start()] + merged + options[match.end():]
    line = options.strip()
    if "%command%" in line:
        return f'WINEDLLOVERRIDES="{name}=n,b" {line}'
    return f'WINEDLLOVERRIDES="{name}=n,b" %command%' + (f" {line}" if line else "")


def record_launch_options(folder: Path, app_id: str, changes: list[tuple[Path, str, str]]) -> None:
    """Keeps (config, before, after) of the launch options set for OptiScaler in its record, so Remove can put back
    what was there. A config set before keeps its first before."""
    record = optiscaler_record(folder)
    if record is None:
        return
    entries = {(e["config"], e["app_id"]): e for e in record.get("launch", [])}
    for config, before, after in changes:
        key = (str(config), app_id)
        first = entries[key]["before"] if key in entries else before
        entries[key] = {"config": str(config), "app_id": app_id, "before": first, "after": after}
    record["launch"] = list(entries.values())
    (folder / OPTISCALER_MARKER).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


def launch_restores(entries: list[dict]) -> list[tuple[Path, str, str]]:
    """(config, AppID, value) that put back the launch options of a record's *entries*: only where they are still
    what the app set; the user's own later change stays."""
    restores = []
    for entry in entries:
        config = Path(entry["config"])
        try:
            if launch_options(config, entry["app_id"]) == entry["after"]:
                restores.append((config, entry["app_id"], entry["before"]))
        except (OSError, HelixError):
            continue
    return restores


# ------------------------------------------------------------------------------------------ helixsr.ini
@dataclass
class HelixIni:
    """The keys of helixsr.ini with HelixSR's defaults (every key is optional in the file)."""

    sharpening_mode: str = "off"
    sharpness: float = 0.3
    motion_adaptive: bool = True
    motion_threshold: float = 2.0
    motion_limit: float = 16.0
    motion_reduction: float = 0.6
    model_e_enabled: bool = True
    network: str = "auto"
    invert_jitter: bool = False
    invert_motion_vectors: bool = False
    motion_vector_front_end: bool = False
    log_enabled: bool = True
    forwarding_dll: str = ""
    upscaler_dll: str = ""
    sharpener: str = "off"
    use_game_slider: bool = False


# Keys HelixSR 1.8 added: written only when set, so a file for an older HelixSR stays as it was.
NEW_IN_1_8 = ("sharpener", "use_game_slider")
# (section, key, field) in file order; the type comes from the dataclass default.
INI_SCHEMA = (
    ("Sharpening", "Mode", "sharpening_mode"),
    ("Sharpening", "Sharpener", "sharpener"),
    ("Sharpening", "Sharpness", "sharpness"),
    ("Sharpening", "MotionAdaptive", "motion_adaptive"),
    ("Sharpening", "MotionThreshold", "motion_threshold"),
    ("Sharpening", "MotionLimit", "motion_limit"),
    ("Sharpening", "MotionReduction", "motion_reduction"),
    ("Sharpening", "UseGameSlider", "use_game_slider"),
    ("ModelE", "Enabled", "model_e_enabled"),
    ("ModelE", "Network", "network"),
    ("ModelE", "InvertJitter", "invert_jitter"),
    ("ModelE", "InvertMotionVectors", "invert_motion_vectors"),
    ("ModelE", "MotionVectorFrontEnd", "motion_vector_front_end"),
    ("Log", "Enabled", "log_enabled"),
    ("Forwarding", "Dll", "forwarding_dll"),
    ("Forwarding", "UpscalerDll", "upscaler_dll"),
)
_FIELD_TYPES = {f.name: type(f.default) for f in fields(HelixIni)}
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_KEY_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*?)(\s*;.*)?$")


def _parse_value(kind: type, raw: str):
    raw = raw.strip()
    if kind is bool:
        return raw.lower() in ("true", "1", "yes", "on")
    if kind is float:
        try:
            return float(raw)
        except ValueError:
            return None
    return raw


def _format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text not in ("", "-0") else "0"
    return str(value)


def parse_ini(text: str) -> HelixIni:
    """Read the known keys; anything missing or unparsable keeps HelixSR's default."""
    lookup = {(s.lower(), k.lower()): f for s, k, f in INI_SCHEMA}
    settings = HelixIni()
    section = ""
    for line in text.splitlines():
        header = _SECTION_RE.match(line)
        if header:
            section = header.group(1).strip().lower()
            continue
        stripped = line.strip()
        if not stripped or stripped[0] in ";#":
            continue
        match = _KEY_RE.match(line)
        if not match:
            continue
        name = lookup.get((section, match.group(2).lower()))
        if name is None:
            continue
        value = _parse_value(_FIELD_TYPES[name], match.group(4))
        if value is not None:
            setattr(settings, name, value)
    return settings


def render_ini(settings: HelixIni, template: str = DEFAULT_INI_TEXT) -> str:
    """Write the settings into the template, changing only the value of known keys: comments, spacing, order and
    unknown keys stay. Missing keys are appended to their section, missing sections at the end."""
    lines = template.splitlines()
    pending: dict[str, dict[str, str]] = {}
    for section, key, name in INI_SCHEMA:
        pending.setdefault(section, {})[key] = _format_value(getattr(settings, name))
    defaults = HelixIni()
    unset = {(section, key) for section, key, name in INI_SCHEMA         # edited in place, never appended
             if name in NEW_IN_1_8 and getattr(settings, name) == getattr(defaults, name)}
    pending_lower = {s.lower(): s for s in pending}

    out: list[str] = []
    section = ""
    section_start = -1          # index in out where the current section's content starts

    def close_section() -> None:
        """Append the keys of the just-finished section that the template did not have."""
        canonical = pending_lower.get(section.lower()) if section else None
        if not canonical or not pending.get(canonical):
            return
        insert_at = len(out)
        while insert_at > section_start and not out[insert_at - 1].strip():
            insert_at -= 1
        for key, value in pending.pop(canonical).items():
            if (canonical, key) not in unset:
                out.insert(insert_at, f"{key} = {value}".rstrip())
                insert_at += 1

    for line in lines:
        header = _SECTION_RE.match(line)
        if header:
            close_section()
            section = header.group(1).strip()
            out.append(line)
            section_start = len(out)
            continue
        match = _KEY_RE.match(line) if line.strip() and line.strip()[0] not in ";#" else None
        canonical = pending_lower.get(section.lower()) if section else None
        if match and canonical:
            keys = pending.get(canonical, {})
            key = next((k for k in keys if k.lower() == match.group(2).lower()), None)
            if key is not None:
                value = keys.pop(key)
                comment = match.group(5) or ""
                line = f"{match.group(1)}{match.group(2)}{match.group(3)}{value}{comment}".rstrip()
        out.append(line)
    close_section()
    for canonical in dict.fromkeys(s for s, _, _ in INI_SCHEMA):
        keys = {k: v for k, v in pending.pop(canonical, {}).items() if (canonical, k) not in unset}
        if not keys:
            continue
        if out and out[-1].strip():
            out.append("")
        out.append(f"[{canonical}]")
        for key, value in keys.items():
            out.append(f"{key} = {value}".rstrip())
    return "\n".join(out) + "\n"


def validate_ini(settings: HelixIni) -> list[str]:
    """Problems that would make HelixSR fall back to a default or behave oddly."""
    problems = []
    if settings.sharpening_mode not in SHARPENING_MODES:
        problems.append(f"Sharpening mode must be one of {', '.join(SHARPENING_MODES)}.")
    if settings.sharpener not in SHARPENERS:
        problems.append(f"Sharpener must be one of {', '.join(SHARPENERS)}.")
    if not 0.0 <= settings.sharpness <= 1.0:
        problems.append("Sharpness must be between 0 and 1.")
    if settings.motion_threshold < 0 or settings.motion_limit < 0:
        problems.append("Motion threshold and limit cannot be negative.")
    if settings.motion_limit <= settings.motion_threshold:
        problems.append("Motion limit must be above the motion threshold.")
    if not 0.0 <= settings.motion_reduction <= 1.0:
        problems.append("Motion reduction must be between 0 and 1.")
    if settings.network not in NETWORKS:
        problems.append(f"Network must be one of {', '.join(NETWORKS)}.")
    for name, value in (("Forwarding DLL", settings.forwarding_dll), ("Upscaler DLL", settings.upscaler_dll)):
        if value and not value.lower().endswith(".dll"):
            problems.append(f"{name} should name a .dll file.")
    return problems


def ini_template(payload_dir: Path) -> str:
    """The payload's helixsr.ini (comments of the release the user has) or the embedded one."""
    try:
        return (payload_dir / INI).read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_INI_TEXT


# ------------------------------------------------------------------------------------------ deployments
@dataclass
class Deployment:
    path: str                   # the replaced DLL (MODE_REPLACE) or the stand-alone folder (MODE_FOLDER)
    mode: str
    game: str                   # display name: the game folder
    deployed_at: str = ""       # ISO timestamp of the last deploy
    helixsr_version: str = ""

    @property
    def location(self) -> Path:
        return Path(self.path)

    @property
    def folder(self) -> Path:
        return self.location if self.mode == MODE_FOLDER else self.location.parent


OLDER, RESTORED = "Older build", "Original restored"     # the states Update older games puts right


def _other_build(dep: Deployment, payload_dir: Path) -> tuple[str, str]:
    """A deployment whose DLL is not the payload's: newer when the payload went back to an older release (the
    fallback on the Setup page), older otherwise."""
    deployed, payload = version_key(dep.helixsr_version), version_key(payload_version(payload_dir))
    if deployed and payload and deployed > payload:
        return "warn", "Newer build"
    return "warn", OLDER


def deployment_state(dep: Deployment, payload_dir: Path) -> tuple[str, str]:
    """(kind, text) for a status pill: ok = HelixSR in place, warn = partly, bad = gone / original restored."""
    folder = dep.folder
    if not folder.is_dir():
        return "bad", "Folder gone"
    if dep.mode == MODE_FOLDER:
        dll = folder / HELIXSR_DLL
        if not dll.is_file():
            return "bad", "Removed"
        if not all((folder / n).is_file() for n in NETWORK_FILES) and not network_embedded(dll):
            return "warn", "Network files missing"
        payload_dll = payload_dir / HELIXSR_DLL
        if payload_dll.is_file() and not same_file(dll, payload_dll):
            return _other_build(dep, payload_dir)
        return "ok", "In place"
    info = inspect_dll(dep.location, payload_dir) if dep.location.is_file() else None
    if info is None:
        return (("bad", "DLL missing") if not original_path(dep.location).exists()
                else ("warn", "Only the backup is left"))
    if not info.deployed or info.restored:
        return "bad", RESTORED
    if not info.network_files:
        return "warn", "Network files missing"
    return ("ok", "In place") if info.matches_payload else _other_build(dep, payload_dir)


def needs_update(dep: Deployment, payload_dir: Path) -> bool:
    """A deployment Update older games brings to the payload: an older build, or the game's DLL back in place."""
    return deployment_state(dep, payload_dir)[1] in (OLDER, RESTORED) and \
        (dep.mode == MODE_FOLDER or dep.location.is_file())


def update_deployment(dep: Deployment, payload_dir: Path) -> list[Path]:
    """Put the payload's HelixSR where *dep* is, as Deploy did, keeping the helixsr.ini there byte for byte and, in a
    stand-alone folder, its second upscaler. A game's backup is never overwritten (deploy())."""
    ini = dep.folder / INI
    kept = ini.read_bytes() if ini.is_file() else None
    if dep.mode == MODE_FOLDER:
        second = dep.folder / SECOND_UPSCALER_DLL
        written = deploy_folder(dep.folder, payload_dir, None, second if second.is_file() else None)
    else:
        written = deploy(dep.location, payload_dir)
    if kept is not None:
        ini.write_bytes(kept)
    return written


class DeploymentStore:
    """deployments.json: where HelixSR was put, so the Overview can show their state and Remove finds them."""

    def __init__(self, path: Path):
        self.path = path
        self.items: list[Deployment] = []
        self.load()

    def load(self) -> None:
        self.items = []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        known = {f.name for f in fields(Deployment)}
        for raw in data.get("deployments", []) if isinstance(data, dict) else []:
            if isinstance(raw, dict) and {"path", "mode", "game"} <= raw.keys():
                self.items.append(Deployment(**{k: str(v) for k, v in raw.items() if k in known}))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"deployments": [asdict(d) for d in self.items]}, indent=2)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def find(self, location: Path) -> Deployment | None:
        key = str(location)
        return next((d for d in self.items if d.path == key), None)

    def record(self, location: Path, mode: str, game: str, version: str) -> Deployment:
        dep = self.find(location)
        if dep is None:
            dep = Deployment(str(location), mode, game)
            self.items.append(dep)
        dep.mode, dep.game, dep.helixsr_version = mode, game, version
        dep.deployed_at = datetime.now().isoformat(timespec="seconds")
        self.items.sort(key=lambda d: (d.game.lower(), d.path))
        self.save()
        return dep

    def forget(self, location: Path) -> None:
        before = len(self.items)
        self.items = [d for d in self.items if d.path != str(location)]
        if len(self.items) != before:
            self.save()


def game_name(path: Path, libraries: list[Path] | None = None) -> str:
    """The game folder's name: the steamapps/common child when the path is inside a Steam library, else the
    first folder above the DLL that is not a plain engine subfolder."""
    for library in libraries or []:
        common = library / "common"
        try:
            relative = path.resolve().relative_to(common.resolve())
        except (ValueError, OSError):
            continue
        if relative.parts:
            return relative.parts[0]
    folder = path if path.is_dir() else path.parent
    skip = {"win64", "binaries", "thirdparty", "plugins", "engine", "bin", "x64", "helixsr"}
    for parent in (folder, *folder.parents):
        if parent.name.lower() not in skip and parent.name:
            return parent.name
    return folder.name or str(folder)


# ------------------------------------------------------------------------------------------------ steam
def steam_roots(home: Path | None = None) -> list[Path]:
    home = home or Path.home()
    candidates = (home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root",
                  home / ".var/app/com.valvesoftware.Steam/.local/share/Steam")
    roots: list[Path] = []
    for root in candidates:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if (resolved / "steamapps").is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


_VDF_PATH_RE = re.compile(r'"path"\s+"((?:[^"\\]|\\.)*)"')


def steam_libraries(home: Path | None = None) -> list[Path]:
    """Every steamapps folder: the Steam roots plus the libraries listed in libraryfolders.vdf."""
    libraries: list[Path] = []

    def add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            return
        if (resolved / "common").is_dir() and resolved not in libraries:
            libraries.append(resolved)

    for root in steam_roots(home):
        add(root / "steamapps")
        vdf = root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in _VDF_PATH_RE.findall(text):
            add(Path(raw.replace("\\\\", "\\").replace("\\", "/")) / "steamapps")
    return libraries


def steam_games(libraries: list[Path]) -> list[Path]:
    games: list[Path] = []
    for library in libraries:
        try:
            games.extend(p for p in (library / "common").iterdir() if p.is_dir())
        except OSError:
            continue
    return sorted(games, key=lambda p: p.name.lower())


_STEAM_TOOL_RE = re.compile(r"^(Proton\b.*|SteamLinuxRuntime.*|Steamworks Shared|Steam Controller Configs)$",
                            re.IGNORECASE)
_ACF_RE = {"appid": re.compile(r'"appid"\s+"(\d+)"'), "installdir": re.compile(r'"installdir"\s+"([^"]+)"')}


def is_steam_tool(folder: Path) -> bool:
    """Steam's own folders in steamapps/common (Proton, the Steam Linux Runtime, the redistributables), not games."""
    return bool(_STEAM_TOOL_RE.match(folder.name))


def steam_app_ids(libraries: list[Path]) -> dict[Path, str]:
    """The Steam AppID of each installed game folder, from the libraries' appmanifest_<id>.acf files."""
    ids: dict[Path, str] = {}
    for library in libraries:
        try:
            manifests = sorted(library.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            app_id = _ACF_RE["appid"].search(text)
            folder = _ACF_RE["installdir"].search(text)
            if app_id and folder:
                ids[library / "common" / folder.group(1)] = app_id.group(1)
    return ids


def game_running(app_id: str, proc: Path = Path("/proc")) -> bool:
    """True when a process was started by Steam for *app_id*: Steam's launcher runs every game as
    "reaper SteamLaunch AppId=<id> -- ...", Proton games included."""
    token = f"AppId={app_id}".encode()
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if token in (entry / "cmdline").read_bytes().split(b"\0"):
                return True
        except OSError:
            continue
    return False


# ------------------------------------------------------------------------------------------ games list
@dataclass
class GameScan:
    """What HelixSR could do for one game, from the FSR 3.1 DLLs in its folder."""

    folder: Path
    dlls: list[GameDll]
    app_id: str = ""            # Steam's AppID, "" outside Steam
    payload_version: str = ""

    @property
    def usable(self) -> bool:
        return bool(self.dlls)

    def targets(self) -> list[GameDll]:
        """Where Run with HelixSR puts HelixSR: the DLLs HelixSR is in (or was, before the game put its own back);
        else in each folder with FSR 3.1 its upscaler DLL, or amd_fidelityfx_dx12.dll where that is the only one."""
        deployed = [d for d in self.dlls if d.deployed]
        if deployed:
            return deployed
        per_folder: dict[Path, GameDll] = {}
        for dll in self.dlls:
            best = per_folder.get(dll.path.parent)
            if best is None or dll.path.name.lower() == UPSCALER_DLL:
                per_folder[dll.path.parent] = dll
        return list(per_folder.values())

    def state(self) -> tuple[str, str]:
        """(kind, text) for the games list."""
        if not self.dlls:
            return "neutral", "No AMD FSR 3.1 DLL: HelixSR cannot be used"
        targets = self.targets()
        if any(d.restored for d in targets):
            return "bad", "The game put its own DLL back"
        if not any(d.deployed for d in targets):
            return "info", "Not installed"
        if all(d.matches_payload for d in targets):
            return "ok", " ".join(filter(None, ("HelixSR", self.payload_version, "installed")))
        versions = sorted({dll_version(d.path) for d in targets} - {""})
        installed = "HelixSR {0}".format(", ".join(versions)) if versions else "Another HelixSR build"
        return "warn", "{0} installed; {1} is available".format(installed, self.payload_version or "the payload's")


def scan_game(folder: Path, payload_dir: Path, app_id: str = "",
              cancelled: Callable[[], bool] | None = None) -> GameScan:
    return GameScan(folder, find_game_dlls(folder, payload_dir, cancelled=cancelled), app_id,
                    payload_version(payload_dir))
