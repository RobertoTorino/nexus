#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Upstream check: are the apps that pin an upstream release still in step with it?

    python3 tools/check_upstream.py [--report FILE] [decky] [shadps4] [helixsr] [ppsspp] [pcsx2] [rpcs3]
                                    [directmesh] [vita3k] [xenia] [wdriver] [mesa] [ffmpeg] [hdcam] [speedtest]
                                    # all when none is named

Decky Loader Manager pins one Decky release (apps/decky/decky_manager/loader.py: VERSION, TAG, SHA256)
and writes Decky's release unit itself (loader.unit_text()). This compares them with Decky's GitHub repository:
 * the latest stable release: newer than the pin means a new version of the app, tried on the board first;
 * the pinned release's PluginLoader: the SHA-256 GitHub publishes for it must still be the pinned one;
 * dist/plugin_loader-release.service at the pinned tag and on main: Decky's own updater installs main's, so a change
   there reaches boards that update Decky from its settings, without a new Decky release.

The shadPS4 Manager pins one shadPS4 release (apps/shadps4/shadps4_manager/emulator.py: VERSION, TAG,
ASSET, SHA256), read here without importing the app:
 * the latest stable release: newer than the pin means a new version of the app; the report gives the new release's
   Linux zip and the SHA-256 GitHub publishes for it, for the pin;
 * the pinned release's zip: the SHA-256 GitHub publishes for it must still be the pinned one.

The BC-250 Upscaler Manager gets the latest HelixSR release of one major version, or the fallback its developer names
(apps/upscaler/upscaler/acquire.py: SUPPORTED_MAJOR, KNOWN_VERSION, FALLBACK_VERSION), read here without
importing the app:
 * the latest stable release: newer than KNOWN_VERSION means the app gets it without having been checked against it;
   what changed (setup options, the files in the zip, helixsr.ini) needs a look, and a try on the board. A later major
   than SUPPORTED_MAJOR the app does not offer: moving the app to it is the work to do;
 * the fallback the latest release's notes name ("If 1.9.0 does not work for you, use HelixSR 1.8.1") must be
   FALLBACK_VERSION, and that release must still have its zip.

The PPSSPP, PCSX2 and RPCS3 Managers and Mesh Shaders pin one release each (VERSION in the emulator.py of
PPSSPP and PCSX2's stable channel, RPCS3's LANDMARK, DIRECTMESH in bc250-mesh-shaders.sh), read here without
importing the app:
 * the latest stable release (DirectMesh: the newest directmesh-v<version> tag; a tag with more after the version is a
   development candidate and skipped): newer than the pin means a new version of the app, tried on the board first. Their checksums are checked by the apps themselves when they download.
The governor's version is whatever COPR built, nothing in the repository pins it: the GPU Governor Manager says when
filippor's release is newer than the installed package.

The Vita3K and Xenia Managers bring one build each (BUILD, SHA256 in their emulator.py; Xenia's PUBLISHED), read here
without importing the app (owner, 04-11-2026: they come in, though both publish a build almost daily):
 * the newest build: a later one (Vita3K: a higher build number; Xenia: published later) means a new version of the
   app could bring it, after it is tried on the board; the app itself already tells its users that a newer one is out;
 * the pinned build: its AppImage must still be on GitHub, published with the pinned SHA-256 (or without one, which
   older uploads lack: the app checks the download itself).

BC-250 USB Wi-Fi builds its driver from one pinned commit per branch of shenmintao/aic8800d80 (PINS in
apps/wdriver/usb_wifidriver/builder.py, loaded on its own: it needs only the standard library):
 * each branch's head: commits after the pin mean a new version of the app could move the pin, after it is built and
   tried on the board with the stick;
 * the suite owner's mirror, which the app fetches first, must be there and have each pinned commit.

Mesa (Bazzite/Windows 2, 05-11-2026): BC-250 Mesh Shaders builds RADV from one Mesa release (MESA_VER in
apps/mesh/bc250-mesh-shaders.sh, with DirectMesh's patch and the suite's for it), BC-250 ACE Queues from the system's
Mesa with one patch (apps/ace/mesa/gfx1013-ace-queue.patch). Against Mesa's newest release (its tags on GitLab; a
release candidate is none):
 * newer than MESA_VER means a new version of Mesh Shaders, with the patches moved to it, tried on the board;
 * the ACE patch must apply to it (patch -p1 --dry-run on the files it touches, fetched at that release), as Bazzite
   moves to it and the app then builds for it.

Console Link builds FFmpeg from one release and takes libva's headers from one (FFMPEG_VERSION, LIBVA_VERSION in
apps/consoles/native/ffmpeg/build.sh). Against FFmpeg's release tags (n<version> on its GitHub mirror) and libva's
latest release: a newer FFmpeg on the pinned branch (its fixes), a newer branch (a bigger move), a newer libva.

USB HD Cam downloads each camera's firmware from one commit of a GitHub repository (PINNED in
apps/hdcam/usb_hdcam/firmware.py): the file there must still be the pinned one (SHA-256), and the file on the
repository's default branch the same; changed or gone there means a new version of the app could follow it.

BC-250 Bazzite Test's development tool installs one release of Ookla's speedtest CLI (SPEEDTEST_VERSION in
apps/check/development/tools/install-requirements.sh); Ookla's Homebrew formula names the current one.

Exit code 0: all in step; 1: an upstream moved (the report says what); 2: one could not be checked (network, GitHub's
rate limit).
--report FILE writes what moved as Markdown, for the "Upstream review" issue (empty when all are in step).
The weekly workflow .github/workflows/upstream.yml runs it; with GITHUB_TOKEN set it asks GitHub's API as that token.
Nothing is changed or published."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

SUITE = Path(__file__).resolve().parent.parent
LOADER = SUITE / "apps" / "decky" / "decky_manager" / "loader.py"
EMULATOR = SUITE / "apps" / "shadps4" / "shadps4_manager" / "emulator.py"
ACQUIRE = SUITE / "apps" / "upscaler" / "upscaler" / "acquire.py"
PPSSPP = SUITE / "apps" / "ppsspp" / "ppsspp_manager" / "emulator.py"
PCSX2 = SUITE / "apps" / "pcsx2" / "pcsx2_manager" / "emulator.py"
RPCS3 = SUITE / "apps" / "rpcs3" / "rpcs3_manager" / "emulator.py"
MESH = SUITE / "apps" / "mesh" / "bc250-mesh-shaders.sh"
VITA3K = SUITE / "apps" / "vita3k" / "vita3k_manager" / "emulator.py"
XENIA = SUITE / "apps" / "xenia" / "xenia_manager" / "emulator.py"
BUILDER = SUITE / "apps" / "wdriver" / "usb_wifidriver" / "builder.py"
ACE_PATCH = SUITE / "apps" / "ace" / "mesa" / "gfx1013-ace-queue.patch"
FFMPEG_BUILD = SUITE / "apps" / "consoles" / "native" / "ffmpeg" / "build.sh"
HDCAM_FIRMWARE = SUITE / "apps" / "hdcam" / "usb_hdcam" / "firmware.py"
SPEEDTEST_TOOL = SUITE / "apps" / "check" / "development" / "tools" / "install-requirements.sh"
MESA_TAGS = ("https://gitlab.freedesktop.org/api/v4/projects/mesa%2Fmesa/repository/tags"
             "?search=%5Emesa-&order_by=version&per_page=100")
MESA_RAW = "https://gitlab.freedesktop.org/mesa/mesa/-/raw/{tag}/{path}"
MESA_RELEASE = re.compile(r"mesa-(\d+\.\d+\.\d+)")         # a release; "mesa-26.3.0-rc3" is a candidate
FFMPEG_REPO = "FFmpeg/FFmpeg"                 # its GitHub mirror: a release is tagged n<version> there too
FFMPEG_TAG = re.compile(r"refs/tags/n(\d+(?:\.\d+)+)")
LIBVA_REPO = "intel/libva"
FIRMWARE_RAW = re.compile(r"https://raw\.githubusercontent\.com/([^/]+/[^/]+)/([0-9a-f]{40})/(.+)")
SPEEDTEST_FORMULA = "https://raw.githubusercontent.com/teamookla/homebrew-speedtest/master/speedtest.rb"
DIRECTMESH_REPO = "lonewolf0622/bc250meshtaskwork"
DIRECTMESH_PREFIX = "directmesh-"
RELEASE_TAG = re.compile(r"v?\d+(\.\d+)+")      # after the prefix: a release's version, nothing more
HELIXSR_REPO = "lonewolf0622/HelixSR"
# How the release notes name the fallback: "use [HelixSR 1.8.1](...)", earlier "use HelixSR 1.4.3".
FALLBACK_RE = re.compile(r"use \[?HelixSR v?(\d+\.\d+\.\d+)")
API = "https://api.github.com/repos/{repo}"
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/dist/plugin_loader-release.service"
TEMPLATE = Path("${HOMEBREW_FOLDER}")       # unit_text() with this folder gives Decky's file as it is in its repository
TIMEOUT = 30

Fetch = Callable[[str], bytes]


class CheckError(Exception):
    pass


def fetch(url: str) -> bytes:
    headers = {"User-Agent": "bc250-check-upstream"}
    github = "github" in url.split("/")[2]      # GitHub's API and raw files; Mesa's GitLab and FFmpeg's site as they are
    if github:
        headers["Accept"] = "application/vnd.github+json"
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise CheckError(f"{url}: {'GitHub' if github else 'the server'} answered {error.code}") from error
    except (urllib.error.URLError, OSError) as error:
        raise CheckError(f"{url}: {getattr(error, 'reason', error)}") from error


def load_loader(path: Path = LOADER, name: str = "decky_loader_pin") -> ModuleType:
    """loader.py on its own: it needs only the standard library (it runs as root that way). builder.py too."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module             # its dataclasses look their module up there
    spec.loader.exec_module(module)
    return module


@dataclass
class Pin:
    """shadPS4's pin: the constants of emulator.py, as plain strings."""
    REPO: str
    VERSION: str
    TAG: str
    ASSET: str
    SHA256: str


def _string_constants(path: Path, kinds: type | tuple[type, ...] = str) -> dict[str, str]:
    """A module's top-level string constants (or of *kinds*), without importing it (the apps import PyQt6 and core)."""
    values = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, kinds)):
            values[node.targets[0].id] = node.value.value
    return values


def load_shadps4_pin(path: Path = EMULATOR) -> Pin:
    """emulator.py's pin: its top-level string constants."""
    values = _string_constants(path)
    return Pin(**{name: values[name] for name in ("REPO", "VERSION", "TAG", "ASSET", "SHA256")})


@dataclass
class HelixPin:
    """What the BC-250 Upscaler Manager knows of HelixSR: the constants of acquire.py."""
    KNOWN_VERSION: str
    FALLBACK_VERSION: str
    SUPPORTED_MAJOR: int


def load_helixsr_pin(path: Path = ACQUIRE) -> HelixPin:
    values = _string_constants(path, (str, int))
    return HelixPin(values["KNOWN_VERSION"], values["FALLBACK_VERSION"], values["SUPPORTED_MAJOR"])


def _version(tag: str) -> tuple[int, ...]:
    parts = tag.lstrip("v.").split("-")[0].split(".")
    return tuple(int(p) for p in parts if p.isdigit())


@dataclass
class Report:
    pinned: str
    name: str = "Decky Loader"
    short: str = "Decky"
    held: str = "pinned"                        # HelixSR: "known", the newest release the app was checked against
    newest: str = "latest stable"               # what *latest* is: the daily builds' "newest build", the branch heads
    latest: str = ""
    drift: list[str] = field(default_factory=list)
    fine: list[str] = field(default_factory=list)

    def text(self) -> str:
        head = (f"{self.name}: {self.held} {self.pinned}, {self.newest} {self.latest or 'unknown'}. "
                + ("In step." if not self.drift else f"{self.short} moved:"))
        return "\n".join([head] + [f"  - {line}" for line in self.drift] + [f"  ok {line}" for line in self.fine])


def check(loader: ModuleType, get: Fetch = fetch) -> Report:
    repo, tag = loader.REPO, loader.TAG
    report = Report(tag)
    api = API.format(repo=repo)

    latest = json.loads(get(f"{api}/releases/latest"))
    report.latest = str(latest.get("tag_name", ""))
    if _version(report.latest) > _version(tag):
        report.drift.append(f"{report.latest} is out ({str(latest.get('published_at', ''))[:10]}): a new version of "
                            f"Decky Loader Manager pins it, after it is tried on the board. "
                            f"{latest.get('html_url', '')}")
    else:
        report.fine.append(f"no stable release newer than {tag}")

    pinned = json.loads(get(f"{api}/releases/tags/{tag}"))
    assets = {a.get("name"): a for a in pinned.get("assets", [])}
    digest = str(assets.get(loader.ASSET, {}).get("digest") or "")
    if loader.ASSET not in assets:
        report.drift.append(f"{tag} has no {loader.ASSET} any more.")
    elif digest != f"sha256:{loader.SHA256}":
        report.drift.append(f"{tag}'s {loader.ASSET} is published with {digest or 'no SHA-256'}, not the pinned "
                            f"sha256:{loader.SHA256}: the asset was replaced.")
    else:
        report.fine.append(f"{tag}'s {loader.ASSET} is still the pinned file")

    ours = loader.unit_text(TEMPLATE)
    for ref, why in ((tag, "the pinned release's"), ("main", "main's (Decky's updater installs it)")):
        theirs = get(RAW.format(repo=repo, ref=ref)).decode("utf-8", "replace")
        if theirs.strip() != ours.strip():
            report.drift.append(f"{why} plugin_loader-release.service differs from loader.unit_text(): "
                                f"{RAW.format(repo=repo, ref=ref)}")
        else:
            report.fine.append(f"{why} service unit matches loader.unit_text()")
    return report


def check_shadps4(pin: Pin, get: Fetch = fetch) -> Report:
    report = Report(pin.TAG, name="shadPS4", short="shadPS4")
    api = API.format(repo=pin.REPO)

    latest = json.loads(get(f"{api}/releases/latest"))
    report.latest = str(latest.get("tag_name", ""))
    if _version(report.latest) > _version(pin.TAG):
        version = report.latest.lstrip("v.")
        asset = pin.ASSET.replace(pin.VERSION, version)
        found = {a.get("name"): a for a in latest.get("assets", [])}.get(asset)
        if found is None:
            zip_line = f"it has no {asset}: look at its assets before pinning it."
        else:
            digest = str(found.get("digest") or "")
            zip_line = (f"for the pin: {asset}, {digest}" if digest.startswith("sha256:")
                        else f"{asset} is published without a SHA-256: check it before pinning it.")
        report.drift.append(f"{report.latest} is out ({str(latest.get('published_at', ''))[:10]}): a new version of "
                            f"the shadPS4 Manager pins it, after it is tried on the board; {zip_line} "
                            f"{latest.get('html_url', '')}")
    else:
        report.fine.append(f"no stable release newer than {pin.TAG}")

    pinned = json.loads(get(f"{api}/releases/tags/{pin.TAG}"))
    assets = {a.get("name"): a for a in pinned.get("assets", [])}
    digest = str(assets.get(pin.ASSET, {}).get("digest") or "")
    if pin.ASSET not in assets:
        report.drift.append(f"{pin.TAG} has no {pin.ASSET} any more.")
    elif digest != f"sha256:{pin.SHA256}":
        report.drift.append(f"{pin.TAG}'s {pin.ASSET} is published with {digest or 'no SHA-256'}, not the pinned "
                            f"sha256:{pin.SHA256}: the asset was replaced.")
    else:
        report.fine.append(f"{pin.TAG}'s {pin.ASSET} is still the pinned file")
    return report


def check_helixsr(pin: HelixPin, get: Fetch = fetch) -> Report:
    report = Report(f"v{pin.KNOWN_VERSION}", name="HelixSR", short="HelixSR", held="known")
    api = API.format(repo=HELIXSR_REPO)

    latest = json.loads(get(f"{api}/releases/latest"))
    report.latest = str(latest.get("tag_name", ""))
    version = report.latest.lstrip("v")
    if _version(report.latest)[:1] > (pin.SUPPORTED_MAJOR,):
        report.drift.append(f"{report.latest} is out ({str(latest.get('published_at', ''))[:10]}), a new major "
                            f"version: the BC-250 Upscaler Manager stays on {pin.SUPPORTED_MAJOR}.x (SUPPORTED_MAJOR) and does "
                            f"not offer it. Look at what changed (setup options, the files in the zip, helixsr.ini), "
                            f"move the app to it and try it on the board. {latest.get('html_url', '')}")
    elif _version(report.latest) > _version(pin.KNOWN_VERSION):
        zips = [str(a.get("name")) for a in latest.get("assets", []) if str(a.get("name", "")).endswith(".zip")]
        zip_line = (f"its HelixSR-{version}.zip is there" if f"HelixSR-{version}.zip" in zips
                    else f"it has no HelixSR-{version}.zip (zips: {', '.join(zips) or 'none'}): the app needs one")
        report.drift.append(f"{report.latest} is out ({str(latest.get('published_at', ''))[:10]}): the HelixSR "
                            f"Manager already offers it; {zip_line}. Look at what changed (setup options, the files "
                            f"in the zip, helixsr.ini), try it on the board, then set KNOWN_VERSION to {version}. "
                            f"{latest.get('html_url', '')}")
    else:
        report.fine.append(f"no stable release newer than {pin.KNOWN_VERSION}")

    named = FALLBACK_RE.search(str(latest.get("body") or ""))
    if named is None:
        report.fine.append(f"{report.latest}'s notes name no fallback")
    elif named.group(1) != pin.FALLBACK_VERSION:
        report.drift.append(f"{report.latest}'s notes name HelixSR {named.group(1)} as the fallback, the app offers "
                            f"{pin.FALLBACK_VERSION} (FALLBACK_VERSION).")
    else:
        report.fine.append(f"{report.latest}'s notes name the app's fallback, {pin.FALLBACK_VERSION}")

    try:
        fallback = json.loads(get(f"{api}/releases/tags/v{pin.FALLBACK_VERSION}"))
    except CheckError as error:
        if ": GitHub answered 404" not in str(error):
            raise
        report.drift.append(f"the fallback v{pin.FALLBACK_VERSION} is gone from GitHub.")
    else:
        if not any(str(a.get("name", "")).endswith(".zip") for a in fallback.get("assets", [])):
            report.drift.append(f"the fallback v{pin.FALLBACK_VERSION} has no zip any more.")
        else:
            report.fine.append(f"the fallback v{pin.FALLBACK_VERSION} still has its zip")
    return report


@dataclass
class Release:
    """A pinned release that only a newer one can move: what an app brings, read from its files."""
    name: str                                   # "PPSSPP"
    app: str                                    # "the PPSSPP Manager"
    repo: str                                   # where its releases are
    pinned: str                                 # "1.20.4", "v1.3.1"
    where: str                                  # the constant to move: "VERSION in apps/ppsspp/.../emulator.py"
    prefix: str = ""                            # DirectMesh: only the tags that start with it, newest by number


def load_release(name: str) -> Release:
    if name == "directmesh":
        found = re.search(r"^DIRECTMESH=(\S+)$", MESH.read_text(encoding="utf-8"), re.MULTILINE)
        if found is None:
            raise ValueError(f"no DIRECTMESH= line in {MESH.relative_to(SUITE)}")
        return Release("DirectMesh", "Mesh Shaders", DIRECTMESH_REPO, found.group(1),
                       f"DIRECTMESH in {MESH.relative_to(SUITE)}", DIRECTMESH_PREFIX)
    path, constant, app = {"ppsspp": (PPSSPP, "VERSION", "the PPSSPP Manager"),
                           "pcsx2": (PCSX2, "VERSION", "the PCSX2 Manager (its stable channel)"),
                           "rpcs3": (RPCS3, "LANDMARK", "the RPCS3 Manager")}[name]
    values = _string_constants(path)
    title = {"ppsspp": "PPSSPP", "pcsx2": "PCSX2", "rpcs3": "RPCS3"}[name]
    return Release(title, app, values["REPO"], values[constant], f"{constant} in {path.relative_to(SUITE)}")


def check_release(pin: Release, get: Fetch = fetch) -> Report:
    report = Report(pin.pinned, name=pin.name, short=pin.name)
    api = API.format(repo=pin.repo)
    if pin.prefix:
        releases = json.loads(get(f"{api}/releases?per_page=100"))
        # Only a version after the prefix ("directmesh-v1.3.1"), as the app's updates.py reads it: a tag with more
        # after it is a development candidate ("directmesh-v131-auto-rdna1-975ec91", DirectMesh v1.3.1 plus work in
        # progress, 24-10-2026; owner, 05-11-2026: the app stays on the release), never a newer release.
        candidates = [r for r in releases if not r.get("draft") and not r.get("prerelease")
                      and str(r.get("tag_name", "")).startswith(pin.prefix)
                      and RELEASE_TAG.fullmatch(str(r["tag_name"])[len(pin.prefix):])]
        latest = max(candidates, key=lambda r: _version(str(r["tag_name"])[len(pin.prefix):]), default={})
        tag = str(latest.get("tag_name", ""))[len(pin.prefix):]
    else:
        latest = json.loads(get(f"{api}/releases/latest"))
        tag = str(latest.get("tag_name", ""))
    report.latest = tag
    if tag and _version(tag) > _version(pin.pinned):
        report.drift.append(f"{tag} is out ({str(latest.get('published_at', ''))[:10]}): a new version of {pin.app} "
                            f"brings it, after it is tried on the board ({pin.where}). {latest.get('html_url', '')}")
    else:
        report.fine.append(f"no stable release newer than {pin.pinned}")
    return report


@dataclass
class Build:
    """The build a daily-built emulator's manager brings (Vita3K, Xenia), read from its emulator.py."""
    name: str                                   # "Vita3K"
    app: str                                    # "the Vita3K Manager"
    repo: str                                   # where its builds are released
    build: str                                  # the tag: "4186", "e6cd2e4"
    asset: str
    sha256: str
    published: str = ""                         # Xenia: tags are commits, so a later build is one published later
    where: str = ""


def load_build(name: str) -> Build:
    path = {"vita3k": VITA3K, "xenia": XENIA}[name]
    values = _string_constants(path, (str, int))
    where = f"BUILD, SHA256 in {path.relative_to(SUITE)}"
    if name == "vita3k":
        return Build("Vita3K", "the Vita3K Manager", values["BUILDS"], str(values["BUILD"]), values["ASSET"],
                     values["SHA256"], where=where)
    return Build("Xenia", "the Xenia Manager", values["REPO"], values["BUILD"], values["ASSET"], values["SHA256"],
                 values["PUBLISHED"], where + " (and PUBLISHED)")


def _newer_build(pin: Build, tag: str, published: str) -> bool:
    if pin.published:
        return bool(tag) and tag != pin.build and published > pin.published     # ISO 8601 in UTC: compared as text
    return tag.isdigit() and int(tag) > int(pin.build)


def check_build(pin: Build, get: Fetch = fetch) -> Report:
    report = Report(pin.build, name=pin.name, short=pin.name, held="brings build", newest="newest build")
    api = API.format(repo=pin.repo)

    latest = json.loads(get(f"{api}/releases/latest"))
    tag, published = str(latest.get("tag_name", "")), str(latest.get("published_at", ""))
    report.latest = tag
    if _newer_build(pin, tag, published):
        behind = f", {int(tag) - int(pin.build)} builds later" if not pin.published else ""
        report.drift.append(f"build {tag} is out ({published[:10]}{behind}): a new version of {pin.app} could bring "
                            f"it, after it is tried on the board ({pin.where}); the app already tells its users. "
                            f"{latest.get('html_url', '')}")
    else:
        report.fine.append(f"no build newer than {pin.build}")

    try:
        pinned = json.loads(get(f"{api}/releases/tags/{pin.build}"))
    except CheckError as error:
        if ": GitHub answered 404" not in str(error):
            raise
        report.drift.append(f"build {pin.build} is gone from GitHub: {pin.app} cannot download it any more.")
        return report
    assets = {a.get("name"): a for a in pinned.get("assets", [])}
    digest = str(assets.get(pin.asset, {}).get("digest") or "")
    if pin.asset not in assets:
        report.drift.append(f"build {pin.build} has no {pin.asset} any more: {pin.app} cannot download it.")
    elif not digest:
        report.fine.append(f"build {pin.build}'s {pin.asset} is there, published without a SHA-256 (the app checks "
                           f"its own)")
    elif digest != f"sha256:{pin.sha256}":
        report.drift.append(f"build {pin.build}'s {pin.asset} is published with {digest}, not the pinned "
                            f"sha256:{pin.sha256}: the asset was replaced.")
    else:
        report.fine.append(f"build {pin.build}'s {pin.asset} is still the pinned file")
    return report


def _repo(url: str) -> str:
    """owner/name of a github.com URL."""
    return url.rstrip("/").removeprefix("https://github.com/")


def check_wdriver(builder: ModuleType, get: Fetch = fetch) -> Report:
    pins = builder.PINS
    report = Report(", ".join(f"{b} {p.commit[:7]}" for b, p in pins.items()), name="USB Wi-Fi driver (aic8800d80)",
                    short="The driver", newest="branch heads")
    upstream, mirror = API.format(repo=_repo(builder.UPSTREAM)), API.format(repo=_repo(builder.MIRROR))
    heads = []
    for branch, pin in pins.items():
        compare = json.loads(get(f"{upstream}/compare/{pin.commit}...{branch}"))
        ahead = int(compare.get("ahead_by") or 0)
        commits = compare.get("commits") or [{}]
        head = str(commits[-1].get("sha", pin.commit))[:7] if ahead else pin.commit[:7]
        date = str(commits[-1].get("commit", {}).get("committer", {}).get("date", ""))[:10] if ahead else ""
        heads.append(f"{branch} {head}")
        if ahead:
            report.drift.append(f"{branch} is {ahead} commit{'s' if ahead != 1 else ''} past the pin {pin.commit[:7]} "
                                f"(newest {head}, {date}): a new version of BC-250 USB Wi-Fi could move PINS in "
                                f"apps/wdriver/usb_wifidriver/builder.py, after the driver is built and tried on the "
                                f"board with the stick. {compare.get('html_url', '')}")
        else:
            report.fine.append(f"{branch} has no commit after the pin {pin.commit[:7]}")
    report.latest = ", ".join(heads)
    try:
        get(mirror)
    except CheckError as error:
        if ": GitHub answered 404" not in str(error):
            raise
        report.drift.append(f"the mirror {builder.MIRROR} is not on GitHub (missing, or private): the app fetches the "
                            f"sources from the upstream alone, so a vanished upstream stops a fresh install.")
        return report
    for branch, pin in pins.items():
        try:
            get(f"{mirror}/commits/{pin.commit}")
        except CheckError as error:
            if not re.search(r": GitHub answered (404|422)", str(error)):
                raise
            report.drift.append(f"the mirror {builder.MIRROR} lacks {branch}'s pinned commit {pin.commit[:7]}: a fresh "
                                f"install of it depends on the upstream alone. Push the branch to the mirror.")
        else:
            report.fine.append(f"the mirror has {branch}'s pinned commit")
    return report


def shell_value(path: Path, name: str) -> str:
    """A shell script's NAME=value, or the default of NAME="${NAME:-value}"."""
    text = path.read_text(encoding="utf-8")
    found = re.search(rf'^{name}="?(?:\$\{{{name}:-)?([^"\s}}]+)', text, re.MULTILINE)
    if not found:
        raise ValueError(f"{path.relative_to(SUITE)} sets no {name}")
    return found.group(1)


Applies = Callable[[str, dict[str, bytes]], bool]


def patch_applies(patch: str, files: dict[str, bytes]) -> bool:
    """Whether *patch* applies with patch -p1 to *files* (path in the tree: its content), as the app's build checks it
    first; only the files the patch touches are needed."""
    with tempfile.TemporaryDirectory(prefix="bc250-check-upstream-") as tree:
        for path, content in files.items():
            target = Path(tree, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        try:
            result = subprocess.run(["patch", "-p1", "--dry-run", "--batch"], input=patch, text=True, cwd=tree,
                                    capture_output=True)
        except OSError as error:
            raise CheckError(f"patch could not run: {error}") from error
    return result.returncode == 0


def check_mesa(mesh: str, ace_patch: str, get: Fetch = fetch, applies: Applies = patch_applies) -> Report:
    """BC-250 Mesh Shaders builds RADV from one Mesa release (MESA_VER), with DirectMesh's patch and the suite's for
    it; BC-250 ACE Queues builds it from the system's Mesa with one patch. The newest Mesa release: newer than
    Mesh Shaders' means a new version of it; ACE Queues' patch must apply to it, as the system moves to it."""
    report = Report(mesh, name="Mesa (BC-250 Mesh Shaders, BC-250 ACE Queues)", short="Mesa",
                    held="Mesh Shaders builds", newest="newest release")
    tags = json.loads(get(MESA_TAGS))
    releases = [m.group(1) for m in (MESA_RELEASE.fullmatch(str(t.get("name", ""))) for t in tags) if m]
    latest = max(releases, key=_version, default="")
    report.latest = latest
    if not latest:
        raise CheckError("Mesa's tags name no release")
    if _version(latest) > _version(mesh):
        report.drift.append(f"Mesa {latest} is out: a new version of BC-250 Mesh Shaders could build it, with "
                            f"DirectMesh's patch for {latest} and the suite's patch moved to it (MESA_VER in "
                            f"apps/mesh/bc250-mesh-shaders.sh, the patches in apps/mesh/mesa/), after it is tried on "
                            f"the board. https://docs.mesa3d.org/relnotes/{latest}.html")
    else:
        report.fine.append(f"no Mesa release newer than {mesh}")
    paths = re.findall(r"^\+\+\+ b/(\S+)", ace_patch, re.MULTILINE)
    files = {path: get(MESA_RAW.format(tag=f"mesa-{latest}", path=path)) for path in paths}
    if applies(ace_patch, files):
        report.fine.append(f"BC-250 ACE Queues' patch applies to Mesa {latest}")
    else:
        report.drift.append(f"BC-250 ACE Queues' patch (apps/ace/mesa/gfx1013-ace-queue.patch) does not apply to Mesa "
                            f"{latest}: once Bazzite ships it, the app cannot build for it. A new version of the app "
                            f"moves the patch to it.")
    return report


def check_ffmpeg(ffmpeg: str, libva: str, get: Fetch = fetch) -> Report:
    """Console Link builds FFmpeg from one release (FFMPEG_VERSION, its tarball's SHA-256 and signature checked) and
    takes libva's headers from one release where the system has none (LIBVA_VERSION). A newer FFmpeg on the pinned
    branch (7.1.x) is its fixes, a newer branch a bigger move; a newer libva only its headers."""
    report = Report(f"FFmpeg {ffmpeg}, libva {libva}", name="FFmpeg and libva (Console Link)", short="FFmpeg or libva",
                    held="builds", newest="newest")
    refs = json.loads(get(f"{API.format(repo=FFMPEG_REPO)}/git/matching-refs/tags/n"))
    versions = {m.group(1) for m in (FFMPEG_TAG.fullmatch(str(r.get("ref", ""))) for r in refs) if m}
    if not versions:
        raise CheckError(f"{FFMPEG_REPO} has no release tag")
    branch = ffmpeg.split(".")[:2]
    newest = max(versions, key=_version)
    on_branch = max((v for v in versions if v.split(".")[:2] == branch), key=_version, default=ffmpeg)
    latest_libva = str(json.loads(get(f"{API.format(repo=LIBVA_REPO)}/releases/latest")).get("tag_name", ""))
    report.latest = f"FFmpeg {newest} ({'.'.join(branch)}.x: {on_branch}), libva {latest_libva or 'unknown'}"
    where = "apps/consoles/native/ffmpeg/build.sh"
    if _version(on_branch) > _version(ffmpeg):
        report.drift.append(f"FFmpeg {on_branch} is out, on the pinned {'.'.join(branch)} branch: a new version of "
                            f"Console Link could build it (FFMPEG_VERSION, FFMPEG_SHA256 in {where}), after the "
                            f"stream is tried on the board. https://ffmpeg.org/download.html")
    if _version(newest)[:2] > _version(ffmpeg)[:2]:
        report.drift.append(f"FFmpeg {newest} is a newer branch than {'.'.join(branch)}: moving Console Link to it "
                            f"needs a look at the decoder calls its native core makes, and a try on the board.")
    if not report.drift:
        report.fine.append(f"no FFmpeg release newer than {ffmpeg}")
    if latest_libva and _version(latest_libva) > _version(libva):
        report.drift.append(f"libva {latest_libva} is out: Console Link takes its headers from libva's sources where "
                            f"the system has none (LIBVA_VERSION, LIBVA_SHA256 in {where}); the libraries stay the "
                            f"system's. https://github.com/{LIBVA_REPO}/releases/tag/{latest_libva}")
    else:
        report.fine.append(f"no libva release newer than {libva}")
    return report


@dataclass
class Firmware:
    """One firmware file USB HD Cam downloads, pinned at a commit of a GitHub repository (firmware.PINNED)."""
    model: str
    repo: str
    commit: str
    path: str
    sha256: str


def load_firmware(path: Path = HDCAM_FIRMWARE) -> list[Firmware]:
    """firmware.py's PINNED, read without importing the app: each Pinned(url=..., sha256=...)."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Dict) and all(isinstance(v, ast.Call) for v in node.values)):
            continue
        for key, call in zip(node.keys, node.values):
            values = {k.arg: k.value.value for k in call.keywords if isinstance(k.value, ast.Constant)}
            where = FIRMWARE_RAW.fullmatch(str(values.get("url", "")))
            if isinstance(key, ast.Constant) and where and "sha256" in values:
                found.append(Firmware(str(key.value), where.group(1), where.group(2), where.group(3),
                                      str(values["sha256"])))
    if not found:
        raise ValueError(f"{path.relative_to(SUITE)} pins no firmware")
    return found


def check_hdcam(pins: list[Firmware], get: Fetch = fetch) -> Report:
    """Each pinned firmware file: still there at the pinned commit with its SHA-256, and the same on the repository's
    default branch (a changed or removed file there means a new version of the app could follow it)."""
    report = Report(", ".join(f"{p.model} {p.commit[:7]}" for p in pins), name="USB HD Cam's firmware",
                    short="The firmware", newest="default branch")
    moved = []
    for pin in pins:
        raw = f"https://raw.githubusercontent.com/{pin.repo}/{{ref}}/{pin.path}"
        try:
            pinned = hashlib.sha256(get(raw.format(ref=pin.commit))).hexdigest()
        except CheckError as error:
            if ": GitHub answered 404" not in str(error):
                raise
            report.drift.append(f"{pin.model}'s {pin.path} is gone from {pin.repo} at {pin.commit[:7]}: USB HD Cam "
                                f"cannot download it any more.")
            continue
        if pinned != pin.sha256:
            report.drift.append(f"{pin.model}'s {pin.path} at {pin.commit[:7]} is not the pinned file (SHA-256 "
                                f"{pinned[:12]}…): every download of it fails the check.")
        else:
            report.fine.append(f"{pin.model}'s file at {pin.commit[:7]} is the pinned one")
        try:
            head = hashlib.sha256(get(raw.format(ref="HEAD"))).hexdigest()
        except CheckError as error:
            if ": GitHub answered 404" not in str(error):
                raise
            moved.append(pin.model)
            report.drift.append(f"{pin.model}'s {pin.path} is gone from {pin.repo}'s default branch (the app still "
                                f"downloads it at {pin.commit[:7]}): see what replaced it. https://github.com/{pin.repo}")
            continue
        if head != pin.sha256:
            moved.append(pin.model)
            report.drift.append(f"{pin.model}'s {pin.path} changed on {pin.repo}'s default branch: a new version of USB "
                                f"HD Cam could pin it (PINNED in apps/hdcam/usb_hdcam/firmware.py), after it is tried "
                                f"with the camera. https://github.com/{pin.repo}/commits/HEAD/{pin.path}")
        else:
            report.fine.append(f"{pin.model}'s file is the same on the default branch")
    report.latest = f"changed for {', '.join(moved)}" if moved else "the same files"
    return report


def check_speedtest(version: str, get: Fetch = fetch) -> Report:
    """BC-250 Bazzite Test's development tool installs one release of Ookla's speedtest CLI (SPEEDTEST_VERSION); the
    test itself runs whichever is installed. Ookla publishes no API: its Homebrew formula names the current one."""
    report = Report(version, name="Ookla's speedtest CLI (BC-250 Bazzite Test)", short="speedtest", held="installs",
                    newest="current")
    formula = get(SPEEDTEST_FORMULA).decode("utf-8", "replace")
    found = re.search(r'^\s*version "([^"]+)"', formula, re.MULTILINE)
    if not found:
        raise CheckError(f"{SPEEDTEST_FORMULA} names no version")
    report.latest = found.group(1)
    if _version(report.latest) > _version(version):
        report.drift.append(f"speedtest {report.latest} is out: the development tool could install it "
                            f"(SPEEDTEST_VERSION in apps/check/development/tools/install-requirements.sh), after test "
                            f"44 is run with it on the board. https://www.speedtest.net/apps/cli")
    else:
        report.fine.append(f"no release newer than {version}")
    return report


CHECKS = {"decky": ("Decky Loader", lambda: check(load_loader())),
          "shadps4": ("shadPS4", lambda: check_shadps4(load_shadps4_pin())),
          "helixsr": ("HelixSR", lambda: check_helixsr(load_helixsr_pin())),
          "ppsspp": ("PPSSPP", lambda: check_release(load_release("ppsspp"))),
          "pcsx2": ("PCSX2", lambda: check_release(load_release("pcsx2"))),
          "rpcs3": ("RPCS3", lambda: check_release(load_release("rpcs3"))),
          "directmesh": ("DirectMesh", lambda: check_release(load_release("directmesh"))),
          "vita3k": ("Vita3K", lambda: check_build(load_build("vita3k"))),
          "xenia": ("Xenia", lambda: check_build(load_build("xenia"))),
          "wdriver": ("USB Wi-Fi driver", lambda: check_wdriver(load_loader(BUILDER, "wdriver_builder_pin"))),
          "mesa": ("Mesa", lambda: check_mesa(shell_value(MESH, "MESA_VER"),
                                              ACE_PATCH.read_text(encoding="utf-8"))),
          "ffmpeg": ("FFmpeg and libva", lambda: check_ffmpeg(shell_value(FFMPEG_BUILD, "FFMPEG_VERSION"),
                                                             shell_value(FFMPEG_BUILD, "LIBVA_VERSION"))),
          "hdcam": ("USB HD Cam's firmware", lambda: check_hdcam(load_firmware())),
          "speedtest": ("speedtest CLI", lambda: check_speedtest(shell_value(SPEEDTEST_TOOL, "SPEEDTEST_VERSION")))}


def markdown(reports: list[Report], failed: list[str]) -> str:
    """The issue's body: each upstream that moved with what to do, and those that could not be checked."""
    parts = []
    for report in reports:
        if report.drift:
            parts.append(f"### {report.name}\n\n{report.held.capitalize()} {report.pinned}, {report.newest} "
                         f"{report.latest or 'unknown'}.\n\n" + "\n".join(f"- {line}" for line in report.drift))
    if parts and failed:
        parts.append("Not checked this week: " + "; ".join(failed))
    if parts:
        parts.insert(0, "The weekly upstream check (tools/check_upstream.py) found upstreams that moved since the "
                        "repository last followed them. Close this issue once they are handled; next week opens a "
                        "new one when something moved again.")
    return "\n\n".join(parts) + ("\n" if parts else "")


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    report_file = None
    if "--report" in argv:
        at = argv.index("--report")
        if at + 1 >= len(argv):
            print("--report needs a file", file=sys.stderr)
            return 2
        report_file = Path(argv[at + 1])
        del argv[at:at + 2]
    names = argv or list(CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"Unknown: {', '.join(unknown)}; known: {', '.join(CHECKS)}", file=sys.stderr)
        return 2
    code = 0
    reports, failed = [], []
    for name in names:
        title, run = CHECKS[name]
        try:
            report = run()
        except (CheckError, ValueError) as error:
            print(f"{title} could not be checked: {error}", file=sys.stderr)
            failed.append(f"{title} ({error})")
            code = 2
            continue
        reports.append(report)
        text = report.text()
        print(text)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as out:
                out.write("```\n" + text + "\n```\n")
        if report.drift and code == 0:
            code = 1
    if report_file is not None:
        report_file.write_text(markdown(reports, failed), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
