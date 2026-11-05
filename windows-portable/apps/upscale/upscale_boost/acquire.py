# SPDX-License-Identifier: GPL-3.0-or-later
"""Getting HelixSR onto this PC and keeping it current: the BC250 Bazzite Suite's BC-250 Upscaler Manager's
acquire.py, on Windows.

* supported_release(): the newest GitHub release of HelixSR that this app sets up (SUPPORTED_MAJOR), and a newer major
  one it does not, for the update check (this app is updated by the portal).
* parse_pins(): the exact URLs and SHA-256 sums that a HelixSR release's setup scripts pin for NVIDIA's DLSS DLL, the
  embeddable Python and numpy, and Microsoft's DXC, so the app downloads what the script would download, in parallel.
* Setup: downloads the release zip (checked against the SHA-256 GitHub publishes for it), the prerequisites it still
  needs, then runs HelixSR's own builder (setup\\helixsr_setup.py, unchanged: its license allows running the setup,
  not changing it) with its output streamed to the window. The network files it builds are NVIDIA's property and stay
  on this PC.

On Windows HelixSR's setup is native: helixsr-setup.ps1 fetches the embeddable Python (with numpy) and the shader
compiler, then runs the builder, then its game installer, which asks about every game on the console. The app does
what the script does before the games, with the same pinned files, and leaves the games to its own Games and
Deployments cards. Nothing runs under Wine, and nothing needs an administrator.

Nothing here is Qt; the window runs Setup.run() off its thread. The functions can be tested with file:// URLs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bc250_core.platform import NO_WINDOW, outside_bundle

from . import APP_ID, HELIXSR_RELEASES_URL, __version__
from .backend import HelixError, file_digest, payload_folder, payload_status, version_key

HELIXSR_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases?per_page=30"
# The newest HelixSR major version this app sets up (1.x too). HelixSR 3 changed what a game gets (its network is no
# longer an FFX DLL to swap in): the app stays on 2.x until the owner decides (MIGRATION.md, HelixSR 3).
SUPPORTED_MAJOR = 2
# The newest HelixSR release this app was checked against.
KNOWN_VERSION = "2.0.0"
# The release HelixSR's developer points to when the latest one does not work ("If 1.9.0 does not work for you, use
# HelixSR 1.8.1"): the HelixSR card offers it next to the latest.
FALLBACK_VERSION = "1.8.1"
FALLBACK_TAG = f"v{FALLBACK_VERSION}"
HELIXSR_TAG_API = "https://api.github.com/repos/lonewolf0622/HelixSR/releases/tags/{tag}"
SETUP_SCRIPT = "helixsr-setup.ps1"                 # HelixSR's setup for Windows (helixsr-setup.bat starts it)
BUILDER = "setup/helixsr_setup.py"
# Written by the setup for installs by hand, with more copies of the network; not used here.
UNUSED_OUTPUT = ("manual-install", "fsr3-drop-in")
# From HelixSR 1.9.0 on the builder also builds frame generation for HelixSR Scaler (about 400 MB from NVIDIA), which
# the app does not deploy: --no-fg skips it. Older builders do not know the option.
NO_FG_FROM = (1, 9, 0)
# From HelixSR 2.0.0 on the builder tells what is built (--status: "network=1 fg=0"), checked after the build.
STATUS_FROM = (2, 0, 0)
DLSS_DLL = "nvngx_dlss.dll"
# What a setup takes while it runs: the release, NVIDIA's DLL, the shader compiler, the Python with numpy and the
# build's temporary files. Get HelixSR does not start with less free space.
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


def _get_json(url: str, timeout: int = TIMEOUT) -> object:
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


def release_info(data: object, page_url: str) -> ReleaseInfo:
    """One release of GitHub's answer; errors land in .error."""
    if not isinstance(data, dict):
        return ReleaseInfo(url=page_url, error="unexpected answer from GitHub")
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


def check_updates(payload_version: str) -> UpdateStatus:
    """The payload against the newest HelixSR release this app sets up. The app itself is updated by the portal."""
    latest, unsupported = supported_release()
    return UpdateStatus("HelixSR", payload_version, latest, unsupported)


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
    key: str                        # dlss | python | numpy | dxc
    url: str
    sha256: str
    label: str

    @property
    def filename(self) -> str:
        return urllib.request.unquote(self.url.rsplit("/", 1)[-1]) or self.key


def _ps_pin(key: str) -> tuple[str, str]:
    """helixsr-setup.ps1's $Downloads entry for *key*: key = @{ url = '...' sha = '...' }."""
    return (rf"\b{key}\s*=\s*@\{{\s*url\s*=\s*'([^']+)'",
            rf"\b{key}\s*=\s*@\{{\s*url\s*=\s*'[^']+'\s*sha\s*=\s*'([0-9a-fA-F]{{64}})'")


_PIN_PATTERNS = {
    # key: (file in the release, url regex, sha regex, label)
    "dlss": (BUILDER, r"DLSS_URL\s*=\s*['\"]([^'\"]+)['\"]", r"DLSS_SHA256\s*=\s*['\"]([0-9a-fA-F]{64})['\"]",
             "NVIDIA DLSS DLL"),
    "python": (SETUP_SCRIPT, *_ps_pin("python"), "Python"),
    "numpy": (SETUP_SCRIPT, *_ps_pin("numpy"), "numpy"),
    "dxc": (SETUP_SCRIPT, *_ps_pin("dxc"), "DirectX Shader Compiler"),
}
PREREQUISITES = ("python", "numpy", "dxc")      # what the builder needs besides the release and NVIDIA's DLL


def parse_pins(release_dir: Path) -> dict[str, Pin]:
    """The downloads a release's setup scripts pin (URL + SHA-256). Missing ones are simply absent."""
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
    """The folder that holds helixsr-setup.ps1 (the zip extracts into HelixSR-x.y.z\\)."""
    if (extracted / SETUP_SCRIPT).is_file():
        return extracted
    for child in sorted(p for p in extracted.iterdir() if p.is_dir()):
        if (child / SETUP_SCRIPT).is_file():
            return child
    raise HelixError("No {0} in {1}: not a HelixSR release.".format(SETUP_SCRIPT, extracted))


def extract_zip(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        root = dest.resolve()
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if target != root and root not in target.parents:
                raise HelixError("{0} contains an unsafe path: {1}".format(archive.name, member.filename))
        zf.extractall(dest)
    return find_release_dir(dest)


# --------------------------------------------------------------------------------- prerequisites
# Where they go, as helixsr-setup.ps1 lays them out in its own %LOCALAPPDATA%\HelixSR: python\python.exe with numpy
# in python\numpy, the shader compiler in dxc\. The app keeps its own copy in its folder (the suite's rule:
# everything in %LOCALAPPDATA%\windows-portable-suite).
def python_exe(helix_data: Path) -> Path:
    return helix_data / "python" / "python.exe"


def dxc_exe(helix_data: Path) -> Path:
    return helix_data / "dxc" / "dxc.exe"


def python_present(helix_data: Path) -> bool:
    return python_exe(helix_data).is_file()


def numpy_present(helix_data: Path) -> bool:
    return (helix_data / "python" / "numpy").is_dir()


def dxc_present(helix_data: Path) -> bool:
    return dxc_exe(helix_data).is_file()


def _unpack(archive: Path, dest: Path, keep: Callable[[str], str | None] = lambda name: name) -> int:
    """The members of a zip whose keep(name) is not None, to dest/keep(name); returns how many. Refuses a member
    that would land outside *dest*."""
    count = 0
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            name = keep(member.filename.replace("\\", "/"))
            if name is None or name.endswith("/") or member.is_dir():
                continue
            target = (dest / name).resolve()
            if root not in target.parents:
                raise HelixError("unsafe path in {0}: {1}".format(archive.name, member.filename))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(member))
            count += 1
    return count


def unpack_python(archive: Path, helix_data: Path) -> None:
    """python.org's embeddable package into <data>\\python, as the script's Expand-Archive does."""
    _unpack(archive, helix_data / "python")
    if not python_present(helix_data):
        raise HelixError("the Python package did not bring python.exe")


def unpack_numpy(archive: Path, helix_data: Path) -> None:
    """numpy's wheel (a zip) into <data>\\python, beside the embeddable Python, as the script does: the package's
    ._pth file puts its own folder on the path."""
    _unpack(archive, helix_data / "python")
    if not numpy_present(helix_data):
        raise HelixError("the numpy package did not bring the numpy folder")


def unpack_dxc(archive: Path, helix_data: Path) -> None:
    """bin\\x64\\* of Microsoft's zip to <data>\\dxc, as the script does."""
    count = _unpack(archive, helix_data / "dxc",
                    lambda name: name[len("bin/x64/"):] if name.startswith("bin/x64/") else None)
    if not count:
        raise HelixError("the shader compiler archive has no bin\\x64 folder")


def needed_pins(pins: dict[str, Pin], helix_data: Path, dlss_file: Path | None) -> list[Pin]:
    """Which of the pinned downloads the setup would still fetch on this PC."""
    needed = []
    if "dlss" in pins and dlss_file is None:
        needed.append(pins["dlss"])
    if not (python_present(helix_data) and numpy_present(helix_data)):
        needed += [pins[key] for key in ("python", "numpy") if key in pins]
    if "dxc" in pins and not dxc_present(helix_data):
        needed.append(pins["dxc"])
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


def pinned_dlss_sha(release_dir: Path | None) -> str:
    """The DLSS checksum from an extracted release, or the one HelixSR pins since 1.2.0 when none is at hand."""
    if release_dir is not None:
        pin = parse_pins(release_dir).get("dlss")
        if pin:
            return pin.sha256
    return "be6e434a94ca32499515eb62ca0e6c274526055d568d0426e4c652dcdfb6ee6e"


def latest_work_release(work_dir: Path) -> Path | None:
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


# ------------------------------------------------------------------------------------ the whole run
@dataclass
class SetupRequest:
    work_dir: Path
    helix_data: Path
    release: ReleaseInfo | None = None          # None: look up the latest (or the fallback)
    dlss_file: Path | None = None               # a local nvngx_dlss.dll instead of the download
    fallback: bool = False                      # with release None: the fallback release instead of the latest
    python: str = ""                            # the Python that runs the builder ("": the one in helix_data)


@dataclass
class SetupOutcome:
    ok: bool
    release_dir: Path | None
    version: str
    message: str
    seconds: float


Say = Callable[[str], None]


class Setup:
    """The whole acquisition, run off the window's thread (Setup.run()): what it says arrives through *say* (a line
    of output), *stage* (what it does now) and *progress* (a download's bytes); cancel() from the window's thread
    stops it."""

    def __init__(self, request: SetupRequest, say: Say, stage: Say, progress: Progress | None = None):
        self.request = request
        self.say, self.stage, self.progress = say, stage, progress
        self._cancel = False
        self._process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancel = True
        process = self._process
        if process is not None and process.poll() is None:
            _end_tree(process)

    def _cancelled(self) -> bool:
        return self._cancel

    def run(self) -> SetupOutcome:
        started = time.monotonic()
        try:
            release_dir, version = self._run()
        except Aborted:
            return SetupOutcome(False, None, "", "Canceled.", time.monotonic() - started)
        except (HelixError, OSError) as exc:
            return SetupOutcome(False, None, "", str(exc), time.monotonic() - started)
        return SetupOutcome(True, release_dir, version, "HelixSR {0} is built.".format(version),
                            time.monotonic() - started)

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
                raise HelixError(("Only {free} MB free: the setup needs about {need:.1f} GB while it runs. Free some "
                                  "space and start again.").format(free=free, need=REQUIRED_DISK_MB / 1000))
        req.work_dir.mkdir(parents=True, exist_ok=True)

        self.stage("Downloading HelixSR {0}".format(release.version))
        archive = req.work_dir / release.asset_name
        if archive.is_file() and (not release.asset_size or archive.stat().st_size == release.asset_size) and \
                (not release.asset_sha256 or file_digest(archive) == release.asset_sha256):
            self.say("Using the already downloaded {0}".format(archive.name))
        else:
            self.say("Downloading {0}".format(release.asset_url))
            download(release.asset_url, archive, release.asset_sha256, progress=self.progress,
                     cancelled=self._cancelled, name=release.asset_name)
        extracted = req.work_dir / f"HelixSR-{release.version}"
        if extracted.exists():
            shutil.rmtree(extracted)
        self.stage("Unpacking HelixSR {0}".format(release.version))
        release_dir = extract_zip(archive, extracted)
        self.say("Extracted to {0}".format(release_dir))
        payload = payload_folder(release_dir)
        if not payload_status(payload).dll:
            raise HelixError("The release has no HelixSR DLL.")

        pins = parse_pins(release_dir)
        needed = needed_pins(pins, req.helix_data, req.dlss_file)
        have_python = bool(req.python) or python_present(req.helix_data) and numpy_present(req.helix_data)
        unread = [k for k in PREREQUISITES if k not in pins
                  and not (dxc_present(req.helix_data) if k == "dxc" else have_python)]
        if unread:
            raise HelixError("Could not read the pinned download of {0} from the release's {1}.".format(
                ", ".join(unread), SETUP_SCRIPT))
        if "dlss" not in pins and req.dlss_file is None:
            self.say("Could not read the pinned NVIDIA DLL from the release; the builder downloads it itself.")
        downloads: dict[str, Path] = {}
        if needed:
            self.stage("Downloading {0} at the same time".format(", ".join(p.label for p in needed)))
            for pin in needed:
                self.say(f"{pin.label}: {pin.url}")
            with ThreadPoolExecutor(max_workers=len(needed)) as pool:
                futures = {pin.key: pool.submit(download, pin.url, req.work_dir / pin.filename, pin.sha256,
                                                self.progress, self._cancelled, pin.label) for pin in needed}
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
            if "python" in downloads:
                unpack_python(downloads.pop("python"), req.helix_data)
                (req.work_dir / pins["python"].filename).unlink(missing_ok=True)
                self.say("Python unpacked")
            if "numpy" in downloads:
                unpack_numpy(downloads.pop("numpy"), req.helix_data)
                (req.work_dir / pins["numpy"].filename).unlink(missing_ok=True)
                self.say("numpy unpacked")
            if "dxc" in downloads:
                unpack_dxc(downloads.pop("dxc"), req.helix_data)
                (req.work_dir / pins["dxc"].filename).unlink(missing_ok=True)
                self.say("Shader compiler unpacked")
        if self._cancelled():
            raise Aborted("cancelled")

        dlss = req.dlss_file or downloads.get("dlss")
        try:
            code = self._build(release_dir, release.version, dlss)
        finally:
            if "dlss" in downloads:
                downloads["dlss"].unlink(missing_ok=True)     # NVIDIA's DLL is used once and deleted
                self.say("Deleted the downloaded {0}".format(DLSS_DLL))
        for name in UNUSED_OUTPUT:
            if (release_dir / name).is_dir():
                shutil.rmtree(release_dir / name, ignore_errors=True)
        if self._cancelled():
            raise Aborted("cancelled")
        if code != 0:
            raise HelixError("HelixSR's builder exited with code {0}; the log has its output.".format(code))
        # HelixSR 1.8+ builds the network into its DLL; older releases leave the two files next to it.
        missing = payload_status(payload).missing()
        if missing:
            raise HelixError("The setup finished but did not produce {0}".format(", ".join(missing)))
        return release_dir, release.version

    def _stream(self, command: list[str], cwd: Path) -> int:
        """Runs *command* without a console window, its output said line by line."""
        self.say("> " + subprocess.list2cmdline(command))
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
        env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")    # its lines as they come, in UTF-8
        try:
            with outside_bundle():                      # not the app's own DLLs or Qt's variables
                self._process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                                 errors="replace", bufsize=1, env=env, creationflags=NO_WINDOW)
        except OSError as exc:
            raise HelixError("Could not start HelixSR's builder: {0}".format(exc)) from exc
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.rstrip("\n")
            for part in line.split("\r"):              # a progress bar redraws its line
                if part.strip():
                    self.say(part)
        code = self._process.wait()
        self._process = None
        return code

    def _build(self, release_dir: Path, version: str, dlss: Path | None) -> int:
        """HelixSR's builder on the folder of its DLL (HelixSR-fsrfg from 2.0 on), with the shader compiler and
        NVIDIA's DLL the app fetched, without frame generation (--no-fg, from 1.9 on) and without the games."""
        req = self.request
        python = req.python or str(python_exe(req.helix_data))
        if not req.python and not (python_present(req.helix_data) and numpy_present(req.helix_data)):
            raise HelixError("Python with numpy is missing for HelixSR's builder.")
        if not dxc_present(req.helix_data):
            raise HelixError("The shader compiler is missing.")
        builder = release_dir / BUILDER
        out = payload_folder(release_dir)
        command = [python, str(builder), str(out), "--dxc", str(dxc_exe(req.helix_data)), "--yes"]
        if version_tuple(version) >= NO_FG_FROM:
            command.append("--no-fg")
        if dlss is not None:
            command += ["--dlss", str(dlss)]
        self.stage("Building the network (a few minutes)")
        code = self._stream(command, release_dir)
        if code != 0 or self._cancelled() or version_tuple(version) < STATUS_FROM:
            return code
        try:
            with outside_bundle():
                status = subprocess.run([python, str(builder), str(out), "--status"], capture_output=True, text=True,
                                        errors="replace", timeout=60, creationflags=NO_WINDOW).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            status = str(exc)
        self.say("{0}: {1}".format(out.name, status))
        if "network=1" not in status.split():
            raise HelixError("The build finished but HelixSR's DLL does not carry the network ({0}).".format(status))
        return 0


def _end_tree(process: subprocess.Popen) -> None:
    """The builder and the shader compilers it started, ended (Cancel)."""
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=20,
                           creationflags=NO_WINDOW)
            return
        except (OSError, subprocess.SubprocessError):
            pass
    process.terminate()
