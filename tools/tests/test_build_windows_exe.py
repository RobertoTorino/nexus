# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/build_windows_exe.py: what it hands PyInstaller, and that the release workflow builds every app it lists.
PyInstaller itself is not run here: it only builds for the system it runs on, and the release job does that."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parent.parent.parent
spec = importlib.util.spec_from_file_location("build_windows_exe", SUITE / "tools" / "build_windows_exe.py")
bwe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bwe)


def test_every_windows_app_has_its_package_and_a_core_to_bundle():
    for app, (package, exe_name) in bwe.WINDOWS_APPS.items():
        src = SUITE / "bc250-bazzite" / "apps" / app
        assert (src / package / "__main__.py").is_file()
        assert bwe.stage_app.uses_core(src)
        assert exe_name and (src / "images" / f"{bwe.app_id(src, package)}.webp").is_file()


def test_asset_names_follow_app_id_and_version():
    src = SUITE / "bc250-bazzite" / "apps" / "sftp"
    version = (src / "VERSION").read_text(encoding="utf-8").strip()
    assert bwe.app_id(src, "sftp_tools") == "bc250-bazzite-sftp-tools"
    assert bwe.asset_name("bc250-bazzite-sftp-tools", version) == f"bc250-bazzite-sftp-tools-{version}-windows.zip"


def test_launcher_calls_the_packages_main():
    source = bwe.launcher_source("sftp_tools")
    assert "from sftp_tools.__main__ import main" in source
    assert source.rstrip().endswith("sys.exit(main())")
    compile(source, "launcher.py", "exec")


def test_pyinstaller_gets_one_windowed_exe_with_the_logo_and_core_fonts(tmp_path):
    args = bwe.pyinstaller_args(tmp_path / "stage", tmp_path / "run.py", "sftp_tools", "BC250-SFTP-Tools",
                                tmp_path / "stage" / "images" / "logo.png", tmp_path / "work", tmp_path / "dist", sep=";")
    assert args[0] == str(tmp_path / "run.py")
    assert {"--onefile", "--windowed"} <= set(args)
    assert args[args.index("--name") + 1] == "BC250-SFTP-Tools"
    assert args[args.index("--paths") + 1] == str(tmp_path / "stage")
    add_data = [args[i + 1] for i, a in enumerate(args) if a == "--add-data"]
    assert add_data == [f"{tmp_path / 'stage' / 'images'};images", f"{tmp_path / 'stage' / 'bc250_core' / 'fonts'};bc250_core/fonts"]
    collected = [args[i + 1] for i, a in enumerate(args) if a in ("--collect-submodules", "--collect-all")]
    assert collected == ["sftp_tools", "bc250_core", "paramiko"]


def test_an_app_without_a_windows_build_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="no Windows build"):
        bwe.build("gpu", tmp_path)


def test_release_workflow_builds_and_uploads_each_windows_app():
    workflow = (SUITE / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in workflow
    for app in bwe.WINDOWS_APPS:
        assert re.search(rf"startsWith\(github\.ref_name, '{re.escape(app)}-v'\)", workflow), app
    assert "tools/build_windows_exe.py" in workflow
    assert "gh release upload" in workflow


def _names(dists):
    return {bwe._key(d.metadata["Name"]) for d in dists}


def test_bundled_distributions_follow_the_requirements_as_installed(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("# SPDX-License-Identifier: GPL-3.0-or-later\npytest>=8   # a comment\n"
                            'no-such-package-here\npyyaml; python_version < "3"\n', encoding="utf-8")
    names = _names(bwe.bundled_distributions(requirements))
    assert {"pytest", "pluggy", "iniconfig", "packaging"} <= names       # pytest and what it requires
    assert "no-such-package-here" not in names                          # not installed here: not bundled
    assert "pyyaml" not in names                                        # its marker is false
    assert "hypothesis" not in names                                    # pytest's extra "dev" only


def test_notices_hold_the_others_then_each_package_with_its_license(tmp_path):
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("pytest\n", encoding="utf-8")
    font = tmp_path / "Inter-LICENSE.txt"
    font.write_text("SIL Open Font License 1.1\n", encoding="utf-8")
    dists = bwe.bundled_distributions(requirements)
    text = bwe.notices_text("BC250-Test", dists, [("Font: Inter", font)])
    assert text.startswith("BC250-Test carries the third-party software below.")
    assert text.index("Font: Inter") < text.index("SIL Open Font License 1.1") < text.index("pytest ")
    pytest_dist = next(d for d in dists if bwe._key(d.metadata["Name"]) == "pytest")
    assert f"pytest {pytest_dist.version} (MIT)" in text
    assert "Permission is hereby granted, free of charge" in text      # pytest's MIT license text


def test_python_license_is_found_or_the_build_stops():
    try:
        path = bwe.python_license()
    except SystemExit as error:
        assert "LICENSE.txt" in str(error)
    else:
        assert "PYTHON SOFTWARE FOUNDATION" in path.read_text(encoding="utf-8", errors="replace").upper()
