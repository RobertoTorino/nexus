#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the release assets of one tag:

    python3 tools/build_release.py [--suite NAME] <app>-v<x.y.z> <out-dir> [--bundle DIR]

The tag names its suite (tools/suites.py: a suite's TAG_PREFIX, none for bc250-bazzite); --suite overrides it. A
Windows suite's tags are refused: their release format (no install.sh) is not built here yet.

<out-dir> gets <tag>.tar.gz (unpacks into <tag>/), SHA256SUMS, notes.md and title.txt (the release's title). The
tag's version must equal the app's VERSION. An app in NATIVE_WHEELS needs the wheel of its native core in that folder
first, built by release.yml; it goes into the tarball, so the portal's checksum covers it. Bazzite Test (check) gets
its engine checksum recorded (development/tools/build_info.py), which makes it a release build that refuses a changed
engine. A portal tag needs --bundle: a folder with the pinned check release (<tag>.tar.gz and SHA256SUMS, as
published); it is verified against apps.toml and unpacked into bundled/.

The tar inside is reproducible and the same on Linux and Windows: sorted entries, root:root, the commit time (or
SOURCE_DATE_EPOCH) as mtime, and modes set here (755 for folders and scripts, 644 for the rest), not taken from the
file system, which on Windows has no exec bit. The .tar.gz is only byte for byte the same with the same zlib: its
compressed bytes differ between zlib builds (Fedora's zlib-ng, Ubuntu's zlib). Bazzite Test also records its build
time in bazzite_check/_build_info.py."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# release.yml marks only portal releases as GitHub's "Latest", so this always opens the newest portal.
LATEST_PORTAL_URL = "https://github.com/RobertoTorino/nexus/releases/latest"
_TAG = re.compile(r"^(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")
# The app's folder for the wheel of its native core (Rust with FFmpeg inside), which release.yml builds before this
# runs: users install it with pip and need no compiler. Its version is the app's.
NATIVE_WHEELS = {"consoles": Path("native/wheel")}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


suites = _load("nexus_suites", ROOT / "tools" / "suites.py")
stage_app = _load("bc250_stage_app", ROOT / "tools" / "stage_app.py")
SUITE = stage_app.SUITE                     # the default suite; main() takes the tag's (tools/suites.py)
MANIFEST = SUITE / "portal" / "apps.toml"
manifest = _load("bc250_manifest", SUITE / "portal" / "bc250_portal" / "manifest.py")


def select(suite: Path) -> None:
    """Work on *suite* (its manifest and portal) instead of the default one."""
    global SUITE, MANIFEST, manifest
    SUITE, MANIFEST = suite, suite / "portal" / "apps.toml"
    manifest = _load("bc250_manifest", suite / "portal" / "bc250_portal" / "manifest.py")


def portal_stage() -> tuple[str, str]:
    """The portal's STAGE and STAGE_NOTE (portal/bc250_portal/__init__.py), read without importing the portal."""
    text = (SUITE / "portal" / "bc250_portal" / "__init__.py").read_text(encoding="utf-8")
    found = [re.search(rf'^{name} = "(.*)"$', text, re.M) for name in ("STAGE", "STAGE_NOTE")]
    return found[0][1] if found[0] else "", found[1][1] if found[1] else ""


def release_title(app: str, version: str) -> str:
    """The GitHub release's title: the suite's name (the portal's APP_NAME), then the app's name in apps.toml, so a
    release names what it is among every suite's releases ("BC250 Bazzite Suite: Xenia Manager 0.11.0")."""
    text = (SUITE / "portal" / "bc250_portal" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^APP_NAME = "(.*)"$', text, re.M)
    suite_name = found[1] if found else SUITE.name
    name = "Portal" if app == "portal" else next((e.name for e in manifest.load(MANIFEST) if e.key == app), app)
    return f"{suite_name}: {name} {version}"


def source_epoch() -> int:
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        return int(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def _executable(path: Path) -> bool:
    if path.suffix == ".sh":
        return True
    with path.open("rb") as fh:
        return fh.read(2) == b"#!"


def write_tarball(root: Path, top: str, dest: Path, mtime: int) -> None:
    """root/ packed as top/, deterministically."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        paths = [root, *sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix())]
        for path in paths:
            rel = path.relative_to(root).as_posix()
            info = tarfile.TarInfo(top if rel == "." else f"{top}/{rel}")
            info.mtime, info.uid, info.gid, info.uname, info.gname = mtime, 0, 0, "root", "root"
            if path.is_symlink():
                raise SystemExit(f"{path}: symlinks are not shipped")
            if path.is_dir():
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            else:
                data = path.read_bytes()
                info.size, info.mode = len(data), 0o755 if _executable(path) else 0o644
                tar.addfile(info, io.BytesIO(data))
    with dest.open("wb") as out, gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=mtime) as gz:
        gz.write(raw.getvalue())


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_changes(changelog: Path) -> str:
    """The newest entry of a CHANGELOG: up to the second "Changelog:" line or "## " heading."""
    if not changelog.is_file():
        return ""
    lines = changelog.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(("Changelog:", "## "))]
    if not starts:
        return "\n".join(lines).strip()
    end = starts[1] if len(starts) > 1 else len(lines)
    return "\n".join(lines[starts[0]:end]).strip()


def bundle_bazzite_test(stage_dir: Path, bundle: Path) -> str:
    """Verify the pinned check release in *bundle* and unpack it into stage_dir/bundled/. Returns its tag."""
    entry = next(e for e in manifest.load(MANIFEST) if e.key == "check")
    archive = bundle / entry.asset
    if not archive.is_file():
        raise SystemExit(f"--bundle {bundle} has no {entry.asset} (the tag apps.toml pins)")
    want = entry.sha256
    if not want:
        sums = (bundle / "SHA256SUMS").read_text(encoding="utf-8") if (bundle / "SHA256SUMS").is_file() else ""
        want = next((p[0].lower() for p in (line.split() for line in sums.splitlines())
                     if len(p) == 2 and p[1].lstrip("*") == entry.asset), "")
    if not want or sha256_of(archive) != want:
        raise SystemExit(f"{entry.asset} does not match the checksum pinned in apps.toml or its SHA256SUMS")
    target = stage_dir / "bundled"
    target.mkdir()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
                raise SystemExit(f"{entry.asset}: unexpected entry {member.name}")
        tar.extractall(target, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
    if not (target / entry.tag / "install.sh").is_file():
        raise SystemExit(f"{entry.asset} has no {entry.tag}/install.sh")
    return entry.tag


def native_wheel(app: str, src: Path, version: str) -> str | None:
    """The name of the app's native wheel, None for an app without one; refuses a missing or stale wheel."""
    if app not in NATIVE_WHEELS:
        return None
    folder = src / NATIVE_WHEELS[app]
    wheels = sorted(folder.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"{app} ships the wheel of its native core: {folder} must hold exactly one .whl, built by "
                         "release.yml (native/ffmpeg/build.sh, then maturin build with the feature decoder)")
    if wheels[0].name.split("-")[1] != version:
        raise SystemExit(f"{wheels[0].name} is not version {version}; build the wheel again")
    return wheels[0].name


def build(tag: str, out: Path, bundle: Path | None = None) -> Path:
    match = _TAG.match(tag.removeprefix(suites.tag_prefix(SUITE)))
    if not match:
        raise SystemExit(f"{tag} is not <app>-v<x.y.z>")
    app, version = match["app"], match["version"]
    src = stage_app.source_dir(app, SUITE)
    if (src / ".checkout-only").is_file():
        raise SystemExit(f"{tag}: {src.relative_to(SUITE)} runs from the checkout and has no releases")
    current = (src / "VERSION").read_text(encoding="utf-8").strip()
    if current != version:
        raise SystemExit(f"{tag}: {src.relative_to(SUITE)}/VERSION is {current}; bump it before tagging")
    wheel = native_wheel(app, src, version)
    out.mkdir(parents=True, exist_ok=True)
    notes = [f"## {tag}", ""]
    stage, stage_note = portal_stage()
    if app == "portal" and stage:
        notes += [f"> **{stage}:** {stage_note}", ""]
    if app != "portal":
        notes += [f"> **To install the suite, use the portal, not this file:** the [latest portal release]"
                  f"({LATEST_PORTAL_URL}) installs, updates and removes {app} for you and checks every download. "
                  "This tarball is what the portal downloads; install it by hand only without the portal.", ""]
    with tempfile.TemporaryDirectory() as tmp:
        stage_dir = stage_app.stage(app, Path(tmp) / tag, SUITE)
        epoch = source_epoch()
        if app == "check":                   # its build date is the commit time too: the same tag, the same bytes
            subprocess.run([sys.executable, str(stage_dir / "development" / "tools" / "build_info.py")], check=True,
                           stdout=subprocess.DEVNULL, env=dict(os.environ, SOURCE_DATE_EPOCH=str(epoch)))
        if app == "portal":
            if bundle is None:
                raise SystemExit("a portal release needs --bundle with the pinned check release")
            bundled = bundle_bazzite_test(stage_dir, bundle)
            pins = "\n".join(f"- `{e.tag}`" for e in manifest.load(MANIFEST))
            notes += ["This portal release installs and pins these app releases:", "", pins, "",
                      f"`{bundled}` is included and installed with the portal.", ""]
        if wheel is not None:
            notes += [f"Includes its native core as `{wheel}`, built for Linux x86-64 with FFmpeg linked in "
                      "(LGPL, from its own sources).", ""]
        if (stage_dir / "bc250_core").is_dir():
            core = (ROOT / "core" / "VERSION").read_text(encoding="utf-8").strip()
            notes += [f"Bundles the suite core `bc250_core` {core}.", ""]
        archive = out / f"{tag}.tar.gz"
        write_tarball(stage_dir, tag, archive, epoch)
    digest = sha256_of(archive)
    (out / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    changes = latest_changes(src / "CHANGELOG")
    notes += ["### Install", "", "```bash", "sha256sum --check SHA256SUMS", f"tar xzf {archive.name}",
              f"cd {tag} && ./install.sh", "```", "", f"SHA-256 of `{archive.name}`: `{digest}`", ""]
    if changes:
        notes += ["### Changes", "", changes, ""]
    (out / "notes.md").write_text("\n".join(notes), encoding="utf-8")
    (out / "title.txt").write_text(release_title(app, version) + "\n", encoding="utf-8")
    return archive


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag")
    parser.add_argument("out", type=Path)
    parser.add_argument("--bundle", type=Path, help="folder with the pinned check release (portal tags)")
    suites.add_argument(parser)
    args = parser.parse_args(argv)
    try:
        suite = suites.suite(args.suite) if args.suite else suites.of_tag(args.tag)[0]
    except LookupError as exc:
        raise SystemExit(str(exc)) from None
    if suites.system(suite) == "windows":
        raise SystemExit(f"{args.tag}: {suite.name} is a Windows suite; its releases are not built here yet")
    if suite != SUITE:
        select(suite)
    archive = build(args.tag, args.out, args.bundle)
    print(f"{archive} {sha256_of(archive)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
