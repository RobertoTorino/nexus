# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/nexus_index.py: the text of GitHub's Latest release, one section per suite with its newest portal."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("nexus_index", TOOLS / "nexus_index.py")
ni = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ni
spec.loader.exec_module(ni)

DOWNLOAD = "https://github.com/RobertoTorino/nexus/releases/download"
NOTES = """## portal-v12.0.0

### Install

```bash
sha256sum --check SHA256SUMS
tar xzf portal-v12.0.0.tar.gz
cd portal-v12.0.0 && ./install.sh
```

SHA-256 of `portal-v12.0.0.tar.gz`: `abc`

### Changes

Release 12.0.0.
"""


def release(tag: str, *, draft: bool = False, prerelease: bool = False, body: str = "",
            assets: tuple[str, ...] = ()) -> dict:
    return {"tag_name": tag, "html_url": f"https://github.com/RobertoTorino/nexus/releases/tag/{tag}", "draft": draft,
            "prerelease": prerelease, "body": body,
            "assets": [{"name": name, "browser_download_url": f"{DOWNLOAD}/{tag}/{name}"} for name in assets]}


def make_suite(root: Path, folder: str, name: str, *, prefix: str = "", system: str = "bazzite",
               apps: dict[str, str] | None = None, mkdocs: str = "") -> None:
    suite = root / folder
    (suite / "portal" / "pkg").mkdir(parents=True)
    (suite / "portal" / "pkg" / "__init__.py").write_text(f'APP_NAME = "{name}"\n', encoding="utf-8")
    (suite / "portal" / "apps.toml").write_text("".join(f'[apps.{key}]\nname = "{app}"\n'
                                                        for key, app in (apps or {}).items()), encoding="utf-8")
    (suite / "SYSTEM").write_text(f"{system}\n", encoding="utf-8")
    if prefix:
        (suite / "TAG_PREFIX").write_text(f"{prefix}\n", encoding="utf-8")
    if mkdocs:
        (suite / "mkdocs.yml").write_text(mkdocs, encoding="utf-8")


def test_newest_skips_drafts_pre_releases_and_other_prefixes():
    releases = [release("portal-v9.10.0"), release("portal-v12.0.0"), release("portal-v13.0.0", draft=True),
                release("portal-v14.0.0", prerelease=True), release("wp-portal-v99.0.0"), release("nexus")]
    version, found = ni.newest(releases, "portal-")
    assert version == "12.0.0" and found["tag_name"] == "portal-v12.0.0"
    assert ni.newest(releases, "wp-portal-")[0] == "99.0.0"
    assert ni.newest(releases, "xenia-") is None


def test_install_steps_are_the_code_block_of_the_install_section():
    assert ni.install_steps(NOTES) == ("```bash\nsha256sum --check SHA256SUMS\ntar xzf portal-v12.0.0.tar.gz\n"
                                       "cd portal-v12.0.0 && ./install.sh\n```")
    assert ni.install_steps("## x\n\n### Changes\n\n```\nnot this\n```\n") == ""


def test_a_section_per_suite_with_its_portal_or_its_apps(tmp_path: Path):
    make_suite(tmp_path, "bc250-bazzite", "BC250 Bazzite Suite", apps={"check": "BC-250 Bazzite Test"},
               mkdocs="site_name: X\nsite_description: Tools for the AMD BC-250 running Bazzite\n"
                      "site_url: https://robertotorino.github.io/nexus/bc250-bazzite-suite/\n")
    make_suite(tmp_path, "windows-portable", "Windows Portable Suite", prefix="wp-", system="windows",
               apps={"test": "Windows Portable Test", "pcsx2": "Windows Portable PCSX2"})
    releases = [release("portal-v12.0.0", body=NOTES, assets=("portal-v12.0.0.tar.gz", "SHA256SUMS")),
                release("portal-v11.0.0"), release("check-v0.18.0"), release("wp-test-v0.1.0"),
                release("wp-test-v0.1.1"), release("nexus")]
    text = ni.body(releases, tmp_path)
    assert text.index("## BC250 Bazzite Suite") < text.index("## Windows Portable Suite")
    bc250 = text[text.index("## BC250"):text.index("## Windows")]
    assert "Tools for the AMD BC-250 running Bazzite. [Wiki](https://robertotorino.github.io/nexus/" in bc250
    assert "**[Portal 12.0.0](https://github.com/RobertoTorino/nexus/releases/tag/portal-v12.0.0)**" in bc250
    assert f"[`portal-v12.0.0.tar.gz`]({DOWNLOAD}/portal-v12.0.0/portal-v12.0.0.tar.gz)" in bc250
    assert f"[`SHA256SUMS`]({DOWNLOAD}/portal-v12.0.0/SHA256SUMS)" in bc250
    assert "cd portal-v12.0.0 && ./install.sh\n```" in bc250 and "check-v0.18.0" not in bc250
    windows = text[text.index("## Windows"):]
    assert "For Windows running on portable gaming devices." in windows and "No portal release yet." in windows
    test = "- [Windows Portable Test 0.1.1](https://github.com/RobertoTorino/nexus/releases/tag/wp-test-v0.1.1)"
    assert test in windows
    assert "PCSX2" not in windows, "an app without a release is not listed"
    assert text.endswith("[Releases](https://github.com/RobertoTorino/nexus/releases).\n")


def test_a_portal_without_its_assets_has_no_download_line(tmp_path: Path):
    make_suite(tmp_path, "s", "Suite")
    text = ni.body([release("portal-v1.0.0", body=NOTES)], tmp_path)
    assert "**[Portal 1.0.0]" in text and "download [" not in text and "./install.sh" not in text
    assert "No release yet." in ni.body([], tmp_path)


def test_the_repository_has_a_section_per_suite():
    text = ni.body([])
    for folder in ni.suites.suites():
        assert f"## {ni.suite_name(folder)}" in text


def test_main_reads_a_saved_release_list(tmp_path: Path, capsys):
    saved = tmp_path / "releases.json"
    saved.write_text("\n".join(json.dumps(r) for r in [release("portal-v1.2.3")]), encoding="utf-8")
    assert ni.main(["--releases", str(saved)]) == 0
    assert "Portal 1.2.3" in capsys.readouterr().out
