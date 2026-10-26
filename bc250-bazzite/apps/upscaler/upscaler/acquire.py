# SPDX-License-Identifier: GPL-3.0-or-later
"""Getting HelixSR onto this PC and keeping it current.

* supported_release(): the newest GitHub release of HelixSR that this app sets up (SUPPORTED_MAJOR), and a newer major
  one it does not, for the update check (this app is updated by the portal).
* parse_pins(): the exact URLs and SHA-256 sums that a HelixSR release's setup scripts pin for NVIDIA's DLSS DLL,
  Microsoft's DXC and the portable Python, so the app downloads what the script would download, in parallel.
* SetupWorker: downloads the release zip, the prerequisites it still needs, then builds the network with its output
  streamed to the GUI: helixsr-setup.sh --yes for 1.x, HelixSR's own builder for 2.x (see BUILDER_FROM). The network
  files it builds are NVIDIA's property and stay on this PC.

Nothing here is Qt except the thread wrappers at the bottom; the functions can be tested with file:// URLs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import APP_ID, DATA_HOME, HELIXSR_RELEASES_URL, __version__
from .backend import FSRFG, HELIXSR_DLL, HelixError, file_digest, payload_folder, payload_status, version_key

HELIXSR_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases?per_page=30"
# The newest HelixSR major version this app sets up (1.x too). tools/check_upstream.py reports a newer major.
SUPPORTED_MAJOR = 2
# The newest HelixSR release this app was checked against. tools/check_upstream.py reports a newer one every week.
KNOWN_VERSION = "2.0.0"
# The release HelixSR's developer points to when the latest one does not work ("If 1.9.0 does not work for you, use
# HelixSR 1.8.1"): the Setup page offers it next to the latest. tools/check_upstream.py reports when the latest
# release's notes name another one.
FALLBACK_VERSION = "1.8.1"
FALLBACK_TAG = f"v{FALLBACK_VERSION}"
HELIXSR_TAG_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases/tags/{tag}"
HELIXSR_DATA_DIR = DATA_HOME / "HelixSR"            # where helixsr-setup.sh keeps its Python and DXC
WORK_DIR = DATA_HOME / APP_ID / "work"              # downloaded releases live here until imported
SETUP_SCRIPT = "helixsr-setup.sh"
# Written by the setup of HelixSR 1.7+ for installs by hand, with more copies of the network; not used here.
UNUSED_OUTPUT = ("manual-install", "fsr3-drop-in")
# The start of that game installer's first line ("... with DLSS, XeSS or FSR", from 1.9.0 on "... with FSR 3.1"):
# what follows are its questions, which the app does not answer.
INSTALLER_START = "looking for games with"
# HelixSR 2's helixsr-setup.sh hands --yes on to its game installer, which then puts HelixSR Scaler (with frame
# generation) into every game it finds; without --yes it asks on the terminal. From 2.0.0 on the app therefore runs
# what the script runs before the games: HelixSR's own builder, unchanged (its license allows running the setup, not
# changing it), on the release's HelixSR-fsrfg folder, with the Python, the shader compiler and NVIDIA's DLL the app
# fetched, through Wine as the script does. The games stay the Deploy and Games pages'.
BUILDER_FROM = (2, 0, 0)
BUILDER = "setup/helixsr_setup.py"
DXC_WRAPPER = "dxc-wine.sh"                         # the app's own, in its work folder
# Where the script looks for Wine to run Microsoft's shader compiler, in its order: Steam's Proton, then custom Proton
# builds, then a system Wine (below the home folder; "wine" on PATH last).
WINE_GLOBS = (".local/share/Steam/steamapps/common/Proton*/files/bin/wine",
              ".steam/steam/steamapps/common/Proton*/files/bin/wine",
              ".local/share/Steam/compatibilitytools.d/*/files/bin/wine",
              ".steam/root/compatibilitytools.d/*/files/bin/wine")
# From HelixSR 1.9.0 on the setup also builds frame generation for HelixSR Scaler (about 400 MB from NVIDIA), which
# the app does not deploy: --no-fg skips it. Older setups do not know the option.
NO_FG_FROM = (1, 9, 0)
DLSS_DLL = "nvngx_dlss.dll"
# What a setup takes while it runs: the release, NVIDIA's DLL, the shader compiler, a portable Python with numpy and
# the build's temporary files. Download and build does not start with less free space.
REQUIRED_DISK_MB = 1500
TIMEOUT = 15
CHUNK = 1 << 18
# A server that is busy for a moment (GitHub's raw files answer 502 now and then): the download tries this often in
# all, RETRY_PAUSE seconds apart, before it says the server is not available.
DOWNLOAD_TRIES = 5
RETRY_CODES = (502, 503, 504)
RETRY_PAUSE = 3
_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_USER_AGENT = f"{APP_ID}/{__version__}"


version_tuple = version_key


# ------------------------------------------------------------------------------------------ releases
@dataclass
class ReleaseInfo:
    version: str = ""               # "1.2.0", "" when unknown
    tag: str = ""
    url: str = ""                   # release page
    published: str = ""             # YYYY-MM-DD
    asset_name: str = ""            # the release's HelixSR-x.y.z.zip, else its first zip
    asset_url: str = ""
    asset_size: int = 0
    asset_sha256: str = ""          # from GitHub's digest of the zip, "" when it gives none
    error: str = ""


def _get_json(url: str, timeout: int = TIMEOUT) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _fetch(api_url: str, page_url: str) -> tuple[object, ReleaseInfo | None]:
    """GitHub's answer for *api_url*, or a ReleaseInfo that carries the error."""
    try:
        return _get_json(api_url), None
    except urllib.error.HTTPError as exc:
        return None, ReleaseInfo(url=page_url, error="GitHub answered {0}".format(exc.code))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        reason = str(getattr(exc, "reason", exc)).split(":")[0].strip() or exc.__class__.__name__
        return None, ReleaseInfo(url=page_url, error="no connection ({0})".format(reason[:60]))


def latest_release(api_url: str, page_url: str) -> ReleaseInfo:
    """The release *api_url* answers with (one by tag); never raises, errors land in .error."""
    data, failed = _fetch(api_url, page_url)
    return failed or release_info(data, page_url)


def supported_release(api_url: str = HELIXSR_API, page_url: str = HELIXSR_RELEASES_URL) -> tuple[ReleaseInfo, str]:
    """From GitHub's list of releases: the newest stable one of SUPPORTED_MAJOR with its HelixSR-x.y.z.zip, and the
    version of a newer stable release of a later major ("" when there is none). Never raises, errors land in .error."""
    data, failed = _fetch(api_url, page_url)
    if failed:
        return failed, ""
    if not isinstance(data, list):
        return ReleaseInfo(url=page_url, error="unexpected answer from GitHub"), ""
    stable = [release_info(r, page_url) for r in data
              if isinstance(r, dict) and not r.get("draft") and not r.get("prerelease")]
    stable = [r for r in stable if not r.error]
    newest = max(stable, key=lambda r: version_tuple(r.version), default=None)
    supported = [r for r in stable if 1 <= version_tuple(r.version)[0] <= SUPPORTED_MAJOR
                 and r.asset_name.lower() == f"helixsr-{r.version}.zip"]
    best = max(supported, key=lambda r: version_tuple(r.version), default=None)
    if best is None:
        best = ReleaseInfo(url=page_url, error="no HelixSR release up to {0}.x found".format(SUPPORTED_MAJOR))
    newer = newest.version if newest and version_tuple(newest.version)[0] > SUPPORTED_MAJOR else ""
    return best, newer


def release_info(data: dict, page_url: str) -> ReleaseInfo:
    """One release of GitHub's answer; errors land in .error."""
    tag = str(data.get("tag_name", ""))
    match = _VERSION_RE.search(tag)
    if not match:
        return ReleaseInfo(tag=tag, url=page_url, error="unexpected tag {0}".format(repr(tag)))
    info = ReleaseInfo(match.group(0), tag, str(data.get("html_url") or page_url),
                       str(data.get("published_at", ""))[:10])
    zips = [a for a in data.get("assets", []) if str(a.get("name", "")).lower().endswith(".zip")]
    # From 1.9.0 on a release has other zips too (HelixSR Scaler): HelixSR's own is the one named after the version.
    zips.sort(key=lambda a: str(a.get("name", "")).lower() != f"helixsr-{info.version}.zip")
    if zips:
        info.asset_name, info.asset_url = str(zips[0]["name"]), str(zips[0]["browser_download_url"])
        info.asset_size = int(zips[0].get("size") or 0)
        digest = str(zips[0].get("digest") or "")
        info.asset_sha256 = digest[len("sha256:"):].lower() if digest.startswith("sha256:") else ""
    return info


@dataclass
class UpdateStatus:
    """What the update check tells about the HelixSR payload."""

    name: str
    installed: str                  # "" when nothing is installed
    latest: ReleaseInfo             # the newest release of SUPPORTED_MAJOR
    unsupported: str = ""           # a newer major release this app does not set up yet, "" when there is none

    @property
    def update_available(self) -> bool:
        return bool(self.installed and self.latest.version) and \
            version_tuple(self.latest.version) > version_tuple(self.installed)

    @property
    def kind(self) -> str:
        if self.latest.error or not self.latest.version:
            return "neutral"
        if not self.installed:
            return "info"
        return "warn" if self.update_available else "ok"

    @property
    def summary(self) -> str:
        installed = self.installed or "not installed"
        latest = self.latest
        if latest.error:
            return "{0} (latest: unknown, {1})".format(installed, latest.error)
        if not latest.version:
            return "{0} (latest: unknown)".format(installed)
        if self.update_available:
            text = "{0} → {1} available ({2})".format(installed, latest.version, latest.published)
        elif self.installed:
            text = "{0} (up to date, released {1})".format(installed, latest.published)
        else:
            text = "{0}; latest release {1} ({2})".format(installed, latest.version, latest.published)
        if self.unsupported:
            text += "; HelixSR {0} is out, this app does not support it yet".format(self.unsupported)
        return text


def fallback_release() -> ReleaseInfo:
    """The pinned fallback release (FALLBACK_TAG); never raises, errors land in .error."""
    return latest_release(HELIXSR_TAG_API.format(tag=FALLBACK_TAG), HELIXSR_RELEASES_URL)


def check_updates(payload_version: str) -> dict[str, UpdateStatus]:
    # This app itself is updated through the BC250 Bazzite Suite portal.
    latest, unsupported = supported_release()
    return {"helixsr": UpdateStatus("HelixSR", payload_version, latest, unsupported)}


# ---------------------------------------------------------------------------------------- downloads
Progress = Callable[[str, int, int], None]      # name, bytes done, bytes total (0 when unknown)
Cancelled = Callable[[], bool]


class Aborted(HelixError):
    pass


def download(url: str, dest: Path, sha256: str = "", progress: Progress | None = None,
             cancelled: Cancelled | None = None, name: str = "") -> Path:
    """Fetch url to dest (through a .part file), verify the SHA-256 when given. Raises HelixError."""
    name = name or dest.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    for attempt in range(1, DOWNLOAD_TRIES + 1):
        try:
            digest = _download_once(request, part, name, progress, cancelled)
            break
        except urllib.error.HTTPError as exc:
            part.unlink(missing_ok=True)
            if exc.code not in RETRY_CODES:
                raise HelixError("{0}: server answered {1} for {2}".format(name, exc.code, url)) from exc
            if attempt == DOWNLOAD_TRIES:
                raise HelixError("{0}: Server currently not available. Try again later.".format(name)) from exc
        _pause(RETRY_PAUSE, cancelled)
    if sha256 and digest.hexdigest() != sha256.lower():
        part.unlink(missing_ok=True)
        raise HelixError(("{0}: checksum mismatch, the download is not the file HelixSR expects. "
                          "Nothing was kept.").format(name))
    part.replace(dest)
    return dest


def _pause(seconds: float, cancelled: Cancelled | None) -> None:
    """Wait *seconds* before the next try, in short steps so a cancel is not kept waiting."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cancelled and cancelled():
            raise Aborted("cancelled")
        time.sleep(min(0.2, max(0.0, end - time.monotonic())))


def _download_once(request: urllib.request.Request, part: Path, name: str, progress: Progress | None,
                   cancelled: Cancelled | None):
    """One try at fetching *request* to *part*; returns its SHA-256 object. HTTP errors are the caller's."""
    digest = hashlib.sha256()
    done = 0
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            if progress:
                progress(name, 0, total)
            while True:
                if cancelled and cancelled():
                    raise Aborted("cancelled")
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(name, done, total)
    except Aborted:
        part.unlink(missing_ok=True)
        raise
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, OSError) as exc:
        part.unlink(missing_ok=True)
        raise HelixError("{0}: download failed ({1})".format(name, getattr(exc, "reason", exc))) from exc
    return digest


# ------------------------------------------------------------------------------------ pinned sources
@dataclass
class Pin:
    key: str                        # dlss | dxc | python
    url: str
    sha256: str
    label: str

    @property
    def filename(self) -> str:
        return urllib.request.unquote(self.url.rsplit("/", 1)[-1]) or self.key


_PIN_PATTERNS = {
    # key: (file in the release, url regex, sha regex, label)
    "dlss": ("setup/helixsr_setup.py", r"DLSS_URL\s*=\s*['\"]([^'\"]+)['\"]", r"DLSS_SHA256\s*=\s*['\"]([0-9a-fA-F]{64})['\"]",
             "NVIDIA DLSS DLL"),
    "dxc": (SETUP_SCRIPT, r"DXCWIN_URL=['\"]([^'\"]+)['\"]", r"DXCWIN_SHA=['\"]([0-9a-fA-F]{64})['\"]",
            "DirectX Shader Compiler"),
    "python": (SETUP_SCRIPT, r"PY_URL=['\"]([^'\"]+)['\"]", r"PY_SHA=['\"]([0-9a-fA-F]{64})['\"]", "portable Python"),
}


def parse_pins(release_dir: Path) -> dict[str, Pin]:
    """The downloads a release's setup scripts pin (URL + SHA-256). Missing ones are simply absent: the script
    then fetches them itself."""
    pins: dict[str, Pin] = {}
    for key, (rel, url_re, sha_re, label) in _PIN_PATTERNS.items():
        try:
            text = (release_dir / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        url, sha = re.search(url_re, text), re.search(sha_re, text)
        if url and sha:
            pins[key] = Pin(key, url.group(1), sha.group(1).lower(), label)
    return pins


def find_release_dir(extracted: Path) -> Path:
    """The folder that holds helixsr-setup.sh (the zip extracts into HelixSR-x.y.z/)."""
    if (extracted / SETUP_SCRIPT).is_file():
        return extracted
    for child in sorted(p for p in extracted.iterdir() if p.is_dir()):
        if (child / SETUP_SCRIPT).is_file():
            return child
    raise HelixError("No {0} in {1}: not a HelixSR release.".format(SETUP_SCRIPT, extracted))


def extract_zip(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):
                raise HelixError("{0} contains an unsafe path: {1}".format(archive.name, member.filename))
        zf.extractall(dest)
    release_dir = find_release_dir(dest)
    script = release_dir / SETUP_SCRIPT
    script.chmod(script.stat().st_mode | 0o755)
    for sub in ("setup/lib/model/launch_synth",):
        binary = release_dir / sub
        if binary.is_file():
            binary.chmod(binary.stat().st_mode | 0o755)
    return release_dir


# --------------------------------------------------------------------------------- prerequisites
def dxc_present(helix_data: Path) -> bool:
    return (helix_data / "dxc-win" / "bin" / "x64" / "dxc.exe").is_file()


def portable_python_present(helix_data: Path) -> bool:
    return os.access(helix_data / "python" / "bin" / "python3", os.X_OK)


def python_has_numpy(python: str) -> bool:
    try:
        return subprocess.run([python, "-c", "import numpy"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def system_python_has_numpy() -> bool:
    python = shutil.which("python3")
    return bool(python) and python_has_numpy(python)


def unpack_dxc(archive: Path, helix_data: Path) -> None:
    """bin/x64/* of Microsoft's zip (which stores Windows paths) to <data>/dxc-win, as the script does."""
    with zipfile.ZipFile(archive) as zf:
        count = 0
        for name in zf.namelist():
            posix = name.replace("\\", "/")
            if posix.startswith("bin/x64/") and not posix.endswith("/"):
                target = helix_data / "dxc-win" / posix
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
                count += 1
    if not count:
        raise HelixError("the shader compiler archive has no bin/x64 folder")


def unpack_python(archive: Path, helix_data: Path) -> None:
    """python-build-standalone's install_only tarball extracts to python/; the script expects <data>/python."""
    helix_data.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise HelixError("unsafe path in {0}: {1}".format(archive.name, member.name))
        kwargs = {"filter": "data"} if sys.version_info >= (3, 12) else {}
        tar.extractall(helix_data, **kwargs)
    if not portable_python_present(helix_data):
        raise HelixError("the portable Python archive did not produce python/bin/python3")


def find_wine(home: Path | None = None) -> str:
    """The Wine that runs Microsoft's shader compiler, where HelixSR's setup looks for it; "" when there is none."""
    home = home or Path.home()
    for pattern in WINE_GLOBS:
        for wine in sorted(home.glob(pattern)):
            if os.access(wine, os.X_OK):
                return str(wine)
    return shutil.which("wine") or ""


def write_dxc_wrapper(path: Path, wine: str, helix_data: Path) -> Path:
    """A script that runs the Windows shader compiler through *wine* in its own prefix, with absolute Linux paths
    turned into Z:\\ paths, for HelixSR's builder (--dxc)."""
    dxc = helix_data / "dxc-win" / "bin" / "x64" / "dxc.exe"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\n"
                    "# Written by the BC-250 Upscaler Manager: Microsoft's shader compiler through Wine for HelixSR's builder.\n"
                    "args=()\n"
                    "for arg in \"$@\"; do\n"
                    "    [[ $arg == /* ]] && arg=\"Z:${arg//\\//\\\\}\"\n"
                    "    args+=(\"$arg\")\n"
                    "done\n"
                    f"export WINEPREFIX={shlex.quote(str(helix_data / 'wineprefix'))} WINEDEBUG=-all\n"
                    f"exec {shlex.quote(wine)} {shlex.quote(str(dxc))} \"${{args[@]}}\"\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def needed_pins(pins: dict[str, Pin], helix_data: Path, dlss_file: Path | None, immutable: bool) -> list[Pin]:
    """Which of the pinned downloads the setup would still fetch on this PC."""
    needed = []
    if "dlss" in pins and dlss_file is None:
        needed.append(pins["dlss"])
    if "dxc" in pins and not dxc_present(helix_data):
        needed.append(pins["dxc"])
    if "python" in pins and not portable_python_present(helix_data):
        # On a mutable distro the script offers the package manager first; the portable Python is the fallback
        # it uses on Bazzite/SteamOS (and when the system Python has no numpy).
        if immutable or not system_python_has_numpy():
            needed.append(pins["python"])
    return needed


def free_mb(path: Path) -> int:
    """Free space in MB where *path* is (or would be created); -1 when it cannot be read."""
    for folder in (path, *path.parents):
        if folder.exists():
            try:
                return shutil.disk_usage(folder).free // (1 << 20)
            except OSError:
                return -1
    return -1


def is_immutable_system() -> bool:
    if Path("/run/ostree-booted").exists():
        return True
    try:
        return "ID=steamos" in Path("/etc/os-release").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def find_dlss_dlls(libraries: list[Path], sha256: str, max_depth: int = 8,
                   cancelled: Cancelled | None = None) -> list[Path]:
    """nvngx_dlss.dll files in the Steam libraries whose checksum is the one HelixSR pins (only those are
    accepted by the setup without a download)."""
    hits: list[Path] = []
    for library in libraries:
        common = library / "common"
        base_depth = len(common.parts)
        for root, dirs, files in os.walk(common):
            if cancelled and cancelled():
                return hits
            if len(Path(root).parts) - base_depth >= max_depth:
                dirs[:] = []
            for file in files:
                if file.lower() == DLSS_DLL:
                    path = Path(root) / file
                    try:
                        if file_digest(path) == sha256:
                            hits.append(path)
                    except OSError:
                        pass
    return hits


# ------------------------------------------------------------------------------------ the whole run
@dataclass
class SetupRequest:
    release: ReleaseInfo | None = None          # None: look up the latest
    work_dir: Path = WORK_DIR
    helix_data: Path = HELIXSR_DATA_DIR
    dlss_file: Path | None = None               # a local nvngx_dlss.dll instead of the download
    fallback: bool = False                      # with release None: the fallback release instead of the latest
    extra_args: list[str] = field(default_factory=list)
    script_env: dict[str, str] = field(default_factory=dict)


@dataclass
class SetupOutcome:
    ok: bool
    release_dir: Path | None
    version: str
    message: str
    seconds: float


class SetupWorker(QThread):
    """Runs the whole acquisition off the GUI thread. Signals arrive on the GUI thread."""

    log = pyqtSignal(str)
    progress = pyqtSignal(str, int, int)        # name, done, total
    stage = pyqtSignal(str)
    finished_with = pyqtSignal(object)          # SetupOutcome

    def __init__(self, request: SetupRequest, parent: QObject | None = None):
        super().__init__(parent)
        self.request = request
        self._cancel = False
        self._process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancel = True
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()

    def _cancelled(self) -> bool:
        return self._cancel

    def _say(self, text: str) -> None:
        self.log.emit(text)

    def run(self) -> None:
        started = time.monotonic()
        try:
            release_dir, version = self._run()
        except Aborted:
            self.finished_with.emit(SetupOutcome(False, None, "", "Cancelled.", time.monotonic() - started))
        except (HelixError, OSError) as exc:
            self.finished_with.emit(SetupOutcome(False, None, "", str(exc), time.monotonic() - started))
        else:
            self.finished_with.emit(SetupOutcome(True, release_dir, version,
                                                 "HelixSR {0} is built in {1}".format(version, release_dir),
                                                 time.monotonic() - started))

    def _run(self) -> tuple[Path, str]:
        req = self.request
        release = req.release or (fallback_release() if req.fallback else supported_release()[0])
        if release.error:
            raise HelixError("Could not look up the latest HelixSR release: {0}".format(release.error)
                             if not req.fallback else
                             "Could not look up HelixSR {0}: {1}".format(FALLBACK_VERSION, release.error))
        if not release.asset_url:
            raise HelixError("HelixSR {0} has no zip to download; see {1}".format(release.version, release.url))
        if not 1 <= version_tuple(release.version)[0] <= SUPPORTED_MAJOR:
            raise HelixError("HelixSR {0} is not supported yet: this app sets up HelixSR up to {1}.x.".format(
                release.version, SUPPORTED_MAJOR))
        for folder in (req.work_dir, req.helix_data):
            free = free_mb(folder)
            if 0 <= free < REQUIRED_DISK_MB:
                raise HelixError(("Only {free} MB free for {folder}: the setup needs about {need:.1f} GB while it "
                                  "runs. Free some space and start again.").format(
                                      free=free, folder=folder, need=REQUIRED_DISK_MB / 1000))
        req.work_dir.mkdir(parents=True, exist_ok=True)

        self.stage.emit("Downloading HelixSR {0}".format(release.version))
        archive = req.work_dir / release.asset_name
        if archive.is_file() and (not release.asset_size or archive.stat().st_size == release.asset_size) and \
                (not release.asset_sha256 or file_digest(archive) == release.asset_sha256):
            self._say("Using the already downloaded {0}".format(archive.name))
        else:
            self._say("Downloading {0}".format(release.asset_url))
            download(release.asset_url, archive, release.asset_sha256, progress=self.progress.emit,
                     cancelled=self._cancelled, name=release.asset_name)
        extracted = req.work_dir / f"HelixSR-{release.version}"
        if extracted.exists():
            shutil.rmtree(extracted)
        release_dir = extract_zip(archive, extracted)
        self._say("Extracted to {0}".format(release_dir))
        payload = payload_folder(release_dir)
        if not (payload / HELIXSR_DLL).is_file():
            raise HelixError("The release has no {0}.".format(HELIXSR_DLL))

        pins = parse_pins(release_dir)
        needed = needed_pins(pins, req.helix_data, req.dlss_file, is_immutable_system())
        unparsed = [k for k in ("dlss", "dxc", "python") if k not in pins]
        if unparsed:
            self._say(("Could not read the pinned source(s) for {0} from the setup scripts; "
                       "the script will download them itself.").format(", ".join(unparsed)))
        downloads: dict[str, Path] = {}
        if needed:
            self.stage.emit("Downloading {0} in parallel".format(", ".join(p.label for p in needed)))
            for pin in needed:
                self._say(f"{pin.label}: {pin.url}")
            with ThreadPoolExecutor(max_workers=len(needed)) as pool:
                futures = {pin.key: pool.submit(download, pin.url, req.work_dir / pin.filename, pin.sha256,
                                                self.progress.emit, self._cancelled, pin.label) for pin in needed}
                errors = []
                for key, future in futures.items():
                    try:
                        downloads[key] = future.result()
                    except Aborted:
                        raise
                    except HelixError as exc:
                        errors.append(str(exc))
            if errors:
                raise HelixError("\n".join(errors))
            if "dxc" in downloads:
                unpack_dxc(downloads["dxc"], req.helix_data)
                downloads["dxc"].unlink(missing_ok=True)
                self._say("Shader compiler unpacked to {0}".format(req.helix_data / "dxc-win"))
            if "python" in downloads:
                unpack_python(downloads["python"], req.helix_data)
                downloads["python"].unlink(missing_ok=True)
                self._say("Portable Python unpacked to {0}".format(req.helix_data / "python"))
        if self._cancelled():
            raise Aborted("cancelled")

        dlss = req.dlss_file or downloads.get("dlss")
        try:
            if version_tuple(release.version) >= BUILDER_FROM:
                code = self._build(release_dir, dlss)
            else:
                code = self._run_script(release_dir, release.version, dlss)
        finally:
            if "dlss" in downloads:
                downloads["dlss"].unlink(missing_ok=True)     # NVIDIA's DLL is used once and deleted
                self._say("Deleted the downloaded {0}".format(DLSS_DLL))
        for name in UNUSED_OUTPUT:
            if (release_dir / name).is_dir():
                shutil.rmtree(release_dir / name, ignore_errors=True)
        if self._cancelled():
            raise Aborted("cancelled")
        if code != 0:
            raise HelixError("{0} exited with code {1}; see the output above.".format(
                BUILDER if version_tuple(release.version) >= BUILDER_FROM else SETUP_SCRIPT, code))
        # HelixSR 1.8+ builds the network into its DLL; older releases leave the two files next to it.
        missing = payload_status(payload).missing()
        if missing:
            raise HelixError("The setup finished but did not produce {0}".format(", ".join(missing)))
        return release_dir, release.version

    def _stream(self, command: list[str], cwd: Path, env: dict[str, str], name: str,
                stop_at: str = "") -> int:
        """Runs *command* with its output in the log, up to a line with *stop_at* (the rest is not shown)."""
        self._say("$ " + shlex.join(command))
        try:
            self._process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1, env=env)
        except OSError as exc:
            raise HelixError("Could not start {0}: {1}".format(name, exc)) from exc
        assert self._process.stdout is not None
        stopped = False
        for line in self._process.stdout:
            if stopped:
                continue
            if stop_at and stop_at in line:
                stopped = True
                self._say(("The network is built. HelixSR's own game installer is "
                           "skipped: use the Deploy page to put HelixSR into a game."))
                continue
            self._say(line.rstrip("\n"))
        code = self._process.wait()
        self._process = None
        return code

    def _run_script(self, release_dir: Path, version: str, dlss: Path | None) -> int:
        """HelixSR 1.x: its helixsr-setup.sh --yes."""
        req = self.request
        # From HelixSR 1.7 on the script ends with its own game installer, which asks per Steam game (--yes does not
        # answer those). Without input it stops at the first question, so the setup only builds the network files.
        command = ["bash", str(release_dir / SETUP_SCRIPT), "--yes", *req.extra_args]
        if dlss is not None:
            command += ["--dlss", str(dlss)]
        if version_tuple(version) >= NO_FG_FROM:
            command.append("--no-fg")
        self.stage.emit("Building the network files (about 5-6 minutes on a BC-250)")
        env = {**os.environ, **req.script_env}
        env.setdefault("XDG_DATA_HOME", str(req.helix_data.parent))
        return self._stream(command, release_dir, env, SETUP_SCRIPT, stop_at=INSTALLER_START)

    def _python(self) -> str:
        """The Python with numpy for HelixSR's builder, as its setup script picks one: the portable Python when it
        has numpy, else the system's python3 with numpy, else the portable Python with numpy installed by pip."""
        req = self.request
        portable = req.helix_data / "python" / "bin" / "python3"
        candidates = ([str(portable)] if portable_python_present(req.helix_data) else []) + \
            [p for p in (shutil.which("python3"),) if p]
        for python in candidates:
            if python_has_numpy(python):
                return python
        if not portable_python_present(req.helix_data):
            raise HelixError("No Python with numpy for HelixSR's setup, and the portable Python could not be fetched.")
        self._say("Installing numpy into the portable Python ({0})".format(portable))
        code = self._stream([str(portable), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "numpy"],
                            req.helix_data, dict(os.environ), "pip")
        if self._cancelled():
            raise Aborted("cancelled")
        if code != 0 or not python_has_numpy(str(portable)):
            raise HelixError("numpy could not be installed into the portable Python; see the output above.")
        return str(portable)

    def _build(self, release_dir: Path, dlss: Path | None) -> int:
        """HelixSR 2.x: its builder on HelixSR-fsrfg, without frame generation (--no-fg) and without the games."""
        req = self.request
        if not dxc_present(req.helix_data):
            raise HelixError("The shader compiler is missing in {0}.".format(req.helix_data / "dxc-win"))
        env = {**os.environ, **req.script_env}
        wine = find_wine(Path(env["HOME"]) if env.get("HOME") else None)
        if not wine:
            raise HelixError("No Proton or Wine found to run the shader compiler: install Proton in Steam (any "
                             "version) and start again.")
        python = self._python()
        dxc = write_dxc_wrapper(req.work_dir / DXC_WRAPPER, wine, req.helix_data)
        self._say("Shader compiler through {0}".format(wine))
        builder = release_dir / BUILDER
        payload = release_dir / FSRFG
        command = [python, str(builder), str(payload), "--dxc", str(dxc), "--yes", "--no-fg", *req.extra_args]
        if dlss is not None:
            command += ["--dlss", str(dlss)]
        self.stage.emit("Building the network (about 5-6 minutes on a BC-250)")
        try:
            code = self._stream(command, release_dir, env, BUILDER)
        finally:
            shutil.rmtree(req.helix_data / "wineprefix", ignore_errors=True)   # the compiler's temporary prefix
        if code != 0 or self._cancelled():
            return code
        try:
            status = subprocess.run([python, str(builder), str(payload), "--status"], capture_output=True, text=True,
                                    errors="replace", timeout=60, env=env).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            status = str(exc)
        self._say("{0}: {1}".format(FSRFG, status))
        if "network=1" not in status.split():
            raise HelixError("The build finished but {0} does not carry the network ({1}).".format(FSRFG, status))
        return 0


class UpdateChecker(QObject):
    """check_updates() off the GUI thread; finished(dict[str, UpdateStatus]) on the GUI thread."""

    finished = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread: _UpdateThread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None

    def start(self, payload_version: str) -> bool:
        if self._thread is not None:
            return False
        self._thread = _UpdateThread(payload_version)
        self._thread.result.connect(self._done)
        self._thread.start()
        return True

    def _done(self, result: dict) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.wait()
            thread.deleteLater()
        self.finished.emit(result)

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.wait(TIMEOUT * 2000 + 1000)
            self._thread = None


class _UpdateThread(QThread):
    result = pyqtSignal(object)

    def __init__(self, payload_version: str):
        super().__init__()
        self.payload_version = payload_version

    def run(self) -> None:
        self.result.emit(check_updates(self.payload_version))


class DlssFinder(QThread):
    """Scans the Steam libraries for a DLSS DLL with the pinned checksum."""

    found = pyqtSignal(object)      # list[Path]

    def __init__(self, libraries: list[Path], sha256: str, parent: QObject | None = None):
        super().__init__(parent)
        self.libraries, self.sha256 = libraries, sha256
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        self.found.emit(find_dlss_dlls(self.libraries, self.sha256, cancelled=lambda: self._cancel))


def pinned_dlss_sha(release_dir: Path | None) -> str:
    """The DLSS checksum from an extracted release, or the one HelixSR 1.2.0 pins when none is at hand."""
    if release_dir is not None:
        pin = parse_pins(release_dir).get("dlss")
        if pin:
            return pin.sha256
    return "be6e434a94ca32499515eb62ca0e6c274526055d568d0426e4c652dcdfb6ee6e"


def latest_work_release(work_dir: Path = WORK_DIR) -> Path | None:
    """The newest extracted release in the work folder, if any."""
    found: list[tuple[tuple[int, ...], Path]] = []
    try:
        for child in work_dir.iterdir():
            if child.is_dir():
                try:
                    found.append((version_tuple(child.name), find_release_dir(child)))
                except (HelixError, OSError):
                    pass
    except OSError:
        return None
    return max(found, default=(None, None))[1]
