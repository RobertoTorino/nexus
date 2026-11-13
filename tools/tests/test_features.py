# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/features.py: the Nexus page's Apps and features chapter from nexus/features.toml, with every suite's apps
in a family, no family naming an app that is not there, and the chapter in the repository current."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import features  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

SUITES = """\
[suites.one]
name = "One Suite"
short = "One"
wiki = "https://example.org/one/"

[suites.two]
name = "Two Suite"
short = "Two"
wiki = "https://example.org/two/"
"""

FAMILIES = """
[[family]]
name = "Portal"
apps = { one = "portal", two = "portal" }
features = [{ text = "Settings: set a time zone" }]

[[family]]
name = "Game Manager"
apps = { one = "game", two = "games" }
features = [
  { text = "Install: a tested release" },
  { text = "Play: start a game", in = ["two"] },
]

[[family]]
name = "Fan Control"
apps = { one = "fan" }
features = [{ text = "Guard: shut down when too hot" }]
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def checkout(tmp_path: Path, families: str = FAMILIES) -> Path:
    write(tmp_path / "one" / "portal" / "apps.toml",
          '[apps.game]\nname = "Game Manager"\ncategory = "gaming"\n\n'
          '[apps.fan]\nname = "BC-250 Fan Control"\ncategory = "sustainable"\n')
    write(tmp_path / "two" / "portal" / "apps.toml", '[apps.games]\nname = "Games"\ncategory = "gaming"\n')
    write(tmp_path / features.DATA, SUITES + families)
    return tmp_path


def test_writes_the_chapter_and_checks_it(tmp_path):
    root = checkout(tmp_path)
    assert features.main(["--check", "--root", str(root)]) == 1          # no chapter yet
    assert features.main(["--root", str(root)]) == 0
    assert features.main(["--check", "--root", str(root)]) == 0
    page = (root / features.PAGE).read_text(encoding="utf-8")
    assert "| App | One | Two |" in page
    # The portal first, then the categories in the portals' order: Fan Control (sustainable) before the game.
    assert page.index("[Portal](#portal)") < page.index("**Sustainable**") < page.index("[Fan Control](#fan-control)") \
        < page.index("**Gaming**") < page.index("[Game Manager](#game-manager)")
    # Each suite's own name for the app, linked to its wiki chapter; a suite without it has an empty cell.
    assert ("| [Game Manager](#game-manager) | [Game Manager](https://example.org/one/apps/game/) | "
            "[Games](https://example.org/two/apps/games/) |") in page
    assert "| [Fan Control](#fan-control) | [BC-250 Fan Control](https://example.org/one/apps/fan/) |  |" in page
    # A feature without `in` is every suite's of its family; with it, only those suites'.
    assert "| Settings: set a time zone | ✓ | ✓ |" in page
    assert "| Install: a tested release | ✓ | ✓ |" in page
    assert "| Play: start a game |  | ✓ |" in page
    assert "| Guard: shut down when too hot | ✓ |  |" in page


def test_a_changed_file_makes_the_chapter_stale(tmp_path):
    root = checkout(tmp_path)
    features.main(["--root", str(root)])
    data = root / features.DATA
    data.write_text(data.read_text(encoding="utf-8").replace("set a time zone", "pick a time zone"), encoding="utf-8")
    assert features.main(["--check", "--root", str(root)]) == 1


def test_an_app_in_no_family_is_an_error(tmp_path):
    root = checkout(tmp_path, FAMILIES.replace('apps = { one = "fan" }', 'apps = { one = "game2" }'))
    errors = features.load(root)[2]
    assert any("one's fan (BC-250 Fan Control) is in no family" in e for e in errors)
    assert any("Fan Control: one has no app game2" in e for e in errors)


def test_the_other_mistakes_are_errors(tmp_path):
    root = checkout(tmp_path, FAMILIES.replace('in = ["two"]', 'in = ["three"]')
                    .replace('apps = { one = "fan" }', 'apps = { one = "fan", two = "games" }'))
    (root / "three" / "portal").mkdir(parents=True)
    (root / "three" / "portal" / "apps.toml").write_text("", encoding="utf-8")
    errors = features.load(root)[2]
    assert any("'Play: start a game' is marked for three" in e for e in errors)
    assert any("two's games is listed under Game Manager already" in e for e in errors)
    assert any("the suite three/ has no [suites.three]" in e for e in errors)


def test_the_repositorys_chapter_is_current(capsys):
    """Every app of every suite is in nexus/features.toml, and nexus/docs/features.md was written from it: after a
    change, python3 tools/features.py."""
    assert features.main(["--check"]) == 0, capsys.readouterr().err
    if features.absent():                   # a checkout of Nexus alone: nothing was checked, and it says so
        assert "is not checked here" in capsys.readouterr().out
