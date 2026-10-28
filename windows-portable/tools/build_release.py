#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the release assets of one tag of the Windows Portable Suite, on Windows:

    python windows-portable/tools/build_release.py wp-<app>-v<x.y.z> <out-dir> [--bundle <dir>]

<out-dir> gets <tag>.zip, SHA256SUMS, notes.md and title.txt (the release's title). The zip unpacks into <tag>/
with program/ (PyInstaller's one-folder build: the .exe, named by the package's EXE_NAME, beside _internal/, which
starts faster than a one-file exe and is flagged less often by virus scanners), install.ps1, LICENSE,
THIRD-PARTY-NOTICES.txt and MANUAL.md when the suite has the app's chapter. The tag's version must equal the app's
VERSION. The app is staged first, as a release of any suite is (tools/stage_app.py), so the exe runs on the
bc250_core the app was tested with.

A portal release (wp-portal-v<x.y.z>, owner 28-10-2026) is built the same way from portal/ (Windows-Portable-Suite.exe
with apps.toml and the tiles' icons inside) and bundles the release of Windows Portable Test that apps.toml pins:
--bundle names a folder with that release's <tag>.zip and SHA256SUMS (the release workflow downloads them from
GitHub), checked against the pin; the zip gets them in bundle/, and the portal's install.ps1 installs the test app
from there. Every pinned tag must exist (check_manifest.py --require-tags, in the release workflow).

This is the suite's own tool (owner, 27-10-2026: a change to one suite never touches another's release): the
BC250 Bazzite Suite's releases are built by tools/build_release.py. It uses the Nexus tools' staging and the
third-party notices of tools/build_windows_exe.py, without changing them."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zipfile
from pathlib import Path

SUITE = Path(__file__).resolve().parent.parent          # windows-portable/
ROOT = SUITE.parent                                     # the repository: core/ and the Nexus tools
_TAG = re.compile(r"^wp-(?P<app>[a-z0-9-]+)-v(?P<version>\d+\.\d+\.\d+)$")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


stage_app = _load("nexus_stage_app", ROOT / "tools" / "stage_app.py")
windows_exe = _load("nexus_build_windows_exe", ROOT / "tools" / "build_windows_exe.py")


def source_epoch() -> int:
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct"], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.strip()
        return int(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0


def release_title(app: str, version: str) -> str:
    """The GitHub release's title: the suite's name (the portal's APP_NAME), then the app's name in apps.toml, so a
    release names what it is among every suite's releases ("Windows Portable Suite: Windows Portable Test 0.1.1")."""
    text = (SUITE / "portal" / "portable_portal" / "__init__.py").read_text(encoding="utf-8")
    found = re.search(r'^APP_NAME = "(.*)"$', text, re.M)
    suite_name = found[1] if found else SUITE.name
    apps = tomllib.loads((SUITE / "portal" / "apps.toml").read_text(encoding="utf-8")).get("apps", {})
    name = "Portal" if app == "portal" else apps.get(app, {}).get("name", app)
    return f"{suite_name}: {name} {version}"


def pinned_test() -> tuple[str, str]:
    """The tag and sha256 of the Windows Portable Test release apps.toml pins: what a portal release bundles."""
    apps = tomllib.loads((SUITE / "portal" / "apps.toml").read_text(encoding="utf-8")).get("apps", {})
    test = apps.get("test", {})
    return str(test.get("tag", "")), str(test.get("sha256", "")).lower()


def bundled_test(bundle: Path | None) -> tuple[Path, str]:
    """The pinned test release's zip in *bundle*, checked against the pin's sha256 (or the folder's SHA256SUMS
    while none is pinned): the zip and its digest. A portal release needs it."""
    tag, want = pinned_test()
    if bundle is None:
        raise SystemExit(f"a portal release bundles {tag}.zip: --bundle <folder with it and its SHA256SUMS>")
    archive = bundle / f"{tag}.zip"
    if not archive.is_file():
        raise SystemExit(f"{bundle} has no {tag}.zip, the test release apps.toml pins")
    if not want:
        sums = bundle / "SHA256SUMS"
        if not sums.is_file():
            raise SystemExit(f"{tag} is pinned without a sha256 and {bundle} has no SHA256SUMS to check it with")
        for line in sums.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == archive.name:
                want = parts[0].lower()
        if not want:
            raise SystemExit(f"{sums} does not list {archive.name}")
    got = sha256_of(archive)
    if got != want:
        raise SystemExit(f"{archive.name} does not match its checksum (got {got[:16]}..., expected {want[:16]}...)")
    return archive, got


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest_changes(changelog: Path) -> str:
    """The newest entry of a CHANGELOG: up to the second "Changelog:" line."""
    if not changelog.is_file():
        return ""
    lines = changelog.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("Changelog:")]
    if not starts:
        return "\n".join(lines).strip()
    end = starts[1] if len(starts) > 1 else len(lines)
    return "\n".join(lines[starts[0]:end]).strip()


def suite_package(src: Path) -> str:
    """The app's package: the one folder in *src* with a __main__.py."""
    found = sorted(p.parent.name for p in src.glob("*/__main__.py"))
    if len(found) != 1:
        raise SystemExit(f"{src}: expected one package with a __main__.py, found {found or 'none'}")
    return found[0]


def exe_name_of(src: Path, package: str) -> str:
    """The .exe's name, without .exe: the app's EXE_NAME (Windows Portable Test: Windows-PT)."""
    text = (src / package / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^EXE_NAME\s*=\s*"([A-Za-z0-9-]+)"', text, re.M)
    if match is None:
        raise SystemExit(f"{package}/__init__.py has no EXE_NAME (letters, digits and dashes): the .exe's name")
    return match.group(1)


def pyinstaller_args(stage: Path, launcher: Path, package: str, exe_name: str, icon: Path, work: Path, dist: Path,
                     sep: str = os.pathsep) -> list[str]:
    # The portal reads apps.toml from next to its package too (portable_portal.MANIFEST).
    manifest = [("--add-data", f"{stage / 'apps.toml'}{sep}.")] if (stage / "apps.toml").is_file() else []
    # And its intro's sound from sounds/ (portable_portal.INTRO_SOUND).
    sounds = [("--add-data", f"{stage / 'sounds'}{sep}sounds")] if (stage / "sounds").is_dir() else []
    return [
        str(launcher),
        "--onedir", "--windowed", "--noconfirm", "--clean", "--noupx",
        "--name", exe_name,
        "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
        "--paths", str(stage),
        "--icon", str(icon),
        "--collect-submodules", package,
        "--collect-submodules", "bc250_core",
        # Read from next to the package, as in an install: the logo, and the fonts core registers.
        "--add-data", f"{stage / 'images'}{sep}images",
        "--add-data", f"{stage / 'bc250_core' / 'fonts'}{sep}bc250_core/fonts",
        *(part for pair in manifest + sounds for part in pair),
    ]


def notices(stage: Path, exe_name: str) -> str:
    """THIRD-PARTY-NOTICES.txt: Python, the fonts core registers and the packages requirements.txt pulls in."""
    fonts = sorted((stage / "bc250_core" / "fonts").glob("*LICENSE*"))
    return windows_exe.notices_text(exe_name, windows_exe.bundled_distributions(stage / "requirements.txt"),
                                    [(f"Python {sys.version.split()[0]}", windows_exe.python_license())]
                                    + [(f"Font: {font.name.split('-')[0]}", font) for font in fonts])


def write_zip(root: Path, top: str, dest: Path, epoch: int) -> None:
    """root/ packed as top/: sorted entries, each with the commit time (not before 1980, zip's first year)."""
    when = time.gmtime(max(epoch, 315532800))[:6]
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
            if path.is_file():
                info = zipfile.ZipInfo(f"{top}/{path.relative_to(root).as_posix()}", date_time=when)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, path.read_bytes())


def build_zip(app: str, tag: str, out: Path, epoch: int, bundle: Path | None = None) -> Path:
    """out/<tag>.zip of app *app*: <tag>/program/ (PyInstaller's one-folder build), install.ps1, LICENSE,
    THIRD-PARTY-NOTICES.txt and MANUAL.md when there is one; the portal's with bundle/ (the pinned test release
    and its SHA256SUMS line)."""
    src = stage_app.source_dir(app, SUITE)
    if not (src / "install.ps1").is_file():
        raise SystemExit(f"{src.relative_to(ROOT)} has no install.ps1")
    package = suite_package(src)
    exe_name = exe_name_of(src, package)
    bundled = bundled_test(bundle) if app == "portal" else None
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        stage = stage_app.stage(app, work / "stage", SUITE)
        launcher = work / f"{exe_name}.py"
        launcher.write_text(windows_exe.launcher_source(package), encoding="utf-8")
        import PyInstaller.__main__ as pyinstaller      # only the build needs it
        pyinstaller.run(pyinstaller_args(stage, launcher, package, exe_name,
                                         stage / "images" / f"{windows_exe.app_id(src, package)}.webp",
                                         work / "build", work / "dist"))
        program = work / "dist" / exe_name
        if not (program / f"{exe_name}.exe").is_file():
            raise SystemExit(f"PyInstaller made no {exe_name}.exe")
        release = work / tag
        release.mkdir()
        shutil.move(str(program), release / "program")
        for extra in ("install.ps1", "LICENSE", "MANUAL.md"):
            if (stage / extra).is_file():
                shutil.copyfile(stage / extra, release / extra)
        (release / windows_exe.NOTICES).write_text(notices(stage, exe_name), encoding="utf-8")
        if bundled is not None:
            test_zip, digest = bundled
            (release / "bundle").mkdir()
            shutil.copyfile(test_zip, release / "bundle" / test_zip.name)
            (release / "bundle" / "SHA256SUMS").write_text(f"{digest}  {test_zip.name}\n", encoding="utf-8",
                                                           newline="\n")
        archive = out / f"{tag}.zip"
        write_zip(release, tag, archive, epoch)
    return archive


def build(tag: str, out: Path, bundle: Path | None = None) -> Path:
    """<tag>.zip, SHA256SUMS, notes.md and title.txt of an app of the suite, or of the portal (with *bundle*)."""
    match = _TAG.match(tag)
    if not match:
        raise SystemExit(f"{tag} is not wp-<app>-v<x.y.z>")
    app, version = match["app"], match["version"]
    src = stage_app.source_dir(app, SUITE)
    current = (src / "VERSION").read_text(encoding="utf-8").strip()
    if current != version:
        raise SystemExit(f"{tag}: {src.relative_to(SUITE)}/VERSION is {current}; bump it before tagging")
    archive = build_zip(app, tag, out, source_epoch(), bundle)
    digest = sha256_of(archive)
    # LF, as sha256sum -c on Linux reads it: Windows' text mode wrote CRLF
    (out / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n", encoding="utf-8", newline="\n")
    core = (ROOT / "core" / "VERSION").read_text(encoding="utf-8").strip()
    what = ["The portal of the Windows Portable Suite: it installs, updates, opens and removes the suite's apps, "
            f"with Windows Portable Test {pinned_test()[0].rsplit('-v', 1)[1]} bundled and installed with it.", ""] \
        if app == "portal" else []
    notes = [f"## {tag}", "", *what,
             f"Built for Windows (x64) with Python, Qt and the suite core `bc250_core` {core} inside; nothing else to "
             "install. The program is not signed, so Windows may ask once whether to run it.", "",
             "### Install", "", "In PowerShell, in the folder you downloaded it to:", "", "```powershell",
             f"(Get-FileHash {archive.name}).Hash -eq (-split (Get-Content SHA256SUMS))[0]"
             "   # True: the download is intact",
             f"Expand-Archive {archive.name} . -Force",
             f"powershell -ExecutionPolicy Bypass -File {tag}\\install.ps1", "```", "",
             "Once it is installed, the installer asks whether to remove the download (the zip, its SHA256SUMS and "
             "the unpacked folder).", "",
             f"SHA-256 of `{archive.name}`: `{digest}`", ""]
    changes = latest_changes(src / "CHANGELOG")
    if changes:
        notes += ["### Changes", "", changes, ""]
    (out / "notes.md").write_text("\n".join(notes), encoding="utf-8")
    (out / "title.txt").write_text(release_title(app, version) + "\n", encoding="utf-8")
    return archive


def main(argv: list[str]) -> int:
    bundle = None
    if len(argv) == 4 and argv[2] == "--bundle":
        bundle, argv = Path(argv[3]), argv[:2]
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    if sys.platform != "win32":
        print(f"{argv[0]}: the Windows Portable Suite's releases are built on Windows (PyInstaller builds for the "
              "system it runs on)", file=sys.stderr)
        return 1
    archive = build(argv[0], Path(argv[1]), bundle)
    print(f"{archive} {sha256_of(archive)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
