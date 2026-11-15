#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the Windows executable of an app that ships one, from the suite checkout:

    python tools/build_windows_exe.py <app> <out-dir>

Run it on Windows (PyInstaller builds for the system it runs on) with the app's requirements, pyinstaller and pillow
installed. <out-dir> gets <app-id>-<version>-windows.zip (the one-file .exe, LICENSE, THIRD-PARTY-NOTICES.txt and
MANUAL.md) and <app-id>-<version>-windows.zip.sha256. The release workflow uploads both to the app's release beside
the portal's <tag>.tar.gz; the portal never installs from them. The app is staged first, like a release, so the exe
runs on the bc250_core the app was tested with.

The exe carries Python, Qt and the app's Python packages; their licenses (PSF, LGPL, BSD, Apache, ...) ask for their
notices to go with it. THIRD-PARTY-NOTICES.txt holds them: Python's license, every package the app's requirements.txt
pulls in as installed where the build runs (with their license files from the package metadata), and the license of
the fonts core registers."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import sysconfig
import tempfile
import zipfile
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_app  # noqa: E402

SUITE = stage_app.SUITE

# app key -> (package, name of the .exe) of the default suite's apps that ship one. None since the BC250 Bazzite Suite,
# whose SFTP Tools did, has its own repository (14-11-2026); the Windows Portable Suite builds its programs with its
# own tools/build_release.py on the functions here.
WINDOWS_APPS: dict[str, tuple[str, str]] = {}


def app_id(src: Path, package: str) -> str:
    text = (src / package / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_ID\s*=\s*"([^"]+)"', text, re.M)
    if match is None:
        raise SystemExit(f"{package}/__init__.py has no APP_ID")
    return match.group(1)


def asset_name(app_id_: str, version: str) -> str:
    return f"{app_id_}-{version}-windows.zip"


def launcher_source(package: str) -> str:
    """PyInstaller wants a script; the package's __main__ uses relative imports, so a script calls its main()."""
    return f"import sys\n\nfrom {package}.__main__ import main\n\nsys.exit(main())\n"


def pyinstaller_args(stage: Path, launcher: Path, package: str, exe_name: str, icon: Path, work: Path, dist: Path,
                     sep: str = os.pathsep) -> list[str]:
    return [
        str(launcher),
        "--onefile", "--windowed", "--noconfirm", "--clean", "--noupx",
        "--name", exe_name,
        "--distpath", str(dist), "--workpath", str(work), "--specpath", str(work),
        "--paths", str(stage),
        "--icon", str(icon),
        "--collect-submodules", package,
        "--collect-submodules", "bc250_core",
        "--collect-all", "paramiko",
        # Read from next to the package, as in an install: the logo, and the fonts core registers.
        "--add-data", f"{stage / 'images'}{sep}images",
        "--add-data", f"{stage / 'bc250_core' / 'fonts'}{sep}bc250_core/fonts",
    ]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- Third-party notices -----------------------------------------------------------------------------------------

NOTICES = "THIRD-PARTY-NOTICES.txt"
LICENSE_FILE = re.compile(r"^(LICEN[CS]E|COPYING|NOTICE|AUTHORS)", re.I)


def _key(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def bundled_distributions(requirements: Path) -> list[metadata.Distribution]:
    """The packages the exe carries: the app's requirements and what they require in turn, as installed where the
    build runs. A requirement that is not installed there (another platform's, an extra's) is not bundled either."""
    from packaging.requirements import Requirement     # PyInstaller depends on it
    lines = (line.split("#")[0].strip() for line in requirements.read_text(encoding="utf-8").splitlines())
    todo = [Requirement(line) for line in lines if line]
    found: dict[str, metadata.Distribution] = {}
    while todo:
        req = todo.pop()
        if req.marker is not None and not req.marker.evaluate({"extra": ""}):
            continue
        if _key(req.name) in found:
            continue
        try:
            dist = metadata.distribution(req.name)
        except metadata.PackageNotFoundError:
            continue
        found[_key(req.name)] = dist
        todo += [Requirement(r) for r in dist.requires or []]
    return sorted(found.values(), key=lambda d: _key(d.metadata["Name"]))


def license_label(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    label = meta.get("License-Expression") or meta.get("License") or ""
    if not label or "\n" in label or len(label) > 80:      # some packages put the whole text in License
        classifiers = [c.rsplit("::", 1)[-1].strip() for c in meta.get_all("Classifier") or []
                       if c.startswith("License ::")]
        label = ", ".join(classifiers) or "see below"
    return label


def license_texts(dist: metadata.Distribution) -> list[tuple[str, str]]:
    """(file name, text) of each license file in the package's metadata."""
    texts = []
    for file in dist.files or []:
        if ".dist-info" in str(file) and LICENSE_FILE.search(file.name):
            text = Path(file.locate()).read_text(encoding="utf-8", errors="replace")
            if text:
                texts.append((file.name, text.strip()))
    return texts


def python_license() -> Path:
    for folder in (Path(sys.base_prefix), Path(sysconfig.get_path("stdlib"))):
        if (folder / "LICENSE.txt").is_file():
            return folder / "LICENSE.txt"
    raise SystemExit("Python's LICENSE.txt was not found: the exe carries Python, so its notice must go with it")


def notices_text(exe_name: str, dists: list[metadata.Distribution], others: list[tuple[str, Path]]) -> str:
    """THIRD-PARTY-NOTICES.txt: *others* (name, license file) first, then each package with its license files."""
    rule = "=" * 78
    parts = [f"{exe_name} carries the third-party software below. Each part keeps its own license; their texts "
             "follow.\nThe app's own license is in LICENSE.\n"]
    parts += [f"{rule}\n{name}\n{rule}\n\n{path.read_text(encoding='utf-8', errors='replace').strip()}\n"
              for name, path in others]
    for dist in dists:
        head = f"{dist.metadata['Name']} {dist.version} ({license_label(dist)})"
        texts = license_texts(dist) or [("", "No license file in the package; see its project page.")]
        parts.append(f"{rule}\n{head}\n{rule}\n\n" + "\n\n".join(
            (f"--- {name} ---\n\n" if name and len(texts) > 1 else "") + text for name, text in texts) + "\n")
    return "\n".join(parts)


def build(app: str, out: Path) -> tuple[Path, Path]:
    if app not in WINDOWS_APPS:
        raise SystemExit(f"{app} has no Windows build (known: {', '.join(sorted(WINDOWS_APPS)) or 'none'})")
    package, exe_name = WINDOWS_APPS[app]
    src = stage_app.source_dir(app)
    version = (src / "VERSION").read_text(encoding="utf-8").strip()
    name = app_id(src, package)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        stage = stage_app.stage(app, work / "stage")
        launcher = work / f"{exe_name}.py"
        launcher.write_text(launcher_source(package), encoding="utf-8")
        import PyInstaller.__main__ as pyinstaller      # only the build needs it
        pyinstaller.run(pyinstaller_args(stage, launcher, package, exe_name, stage / "images" / f"{name}.webp",
                                         work / "build", work / "dist"))
        exe = next((work / "dist").glob(f"{exe_name}*"), None)
        if exe is None:
            raise SystemExit("PyInstaller made no executable")
        fonts = sorted((stage / "bc250_core" / "fonts").glob("*LICENSE*"))
        notices = notices_text(exe_name, bundled_distributions(stage / "requirements.txt"),
                               [(f"Python {sys.version.split()[0]}", python_license())]
                               + [(f"Font: {font.name.split('-')[0]}", font) for font in fonts])
        archive = out / asset_name(name, version)
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(exe, exe.name)
            zf.writestr(NOTICES, notices)
            for extra in ("LICENSE", "MANUAL.md"):
                if (stage / extra).is_file():
                    zf.write(stage / extra, extra)
    checksum = out / f"{archive.name}.sha256"
    checksum.write_text(f"{sha256_of(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, checksum


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    archive, checksum = build(argv[0], Path(argv[1]))
    print(f"{archive}\n{checksum}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
