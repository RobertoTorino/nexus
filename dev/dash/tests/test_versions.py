# SPDX-License-Identifier: GPL-3.0-or-later
"""Dev app versions: the dialog lists the dev apps with the version their CHANGELOG asks for, and Set version writes
it with the checkout's tools/dev_versions.py; a click on the tile opens it."""

from __future__ import annotations

import shutil

from PyQt6.QtCore import Qt

from nexus_dashboard import CHECKOUT, main_window, versions
from nexus_dashboard.main_window import MainWindow


def checkout(tmp_path):
    """A checkout with the tools the dialog runs and one dev app with a fix since 0.1.0."""
    (tmp_path / "tools").mkdir()
    for name in ("dev_versions.py", "check_versions.py", "suites.py"):
        shutil.copy(CHECKOUT / "tools" / name, tmp_path / "tools" / name)
    app = tmp_path / "dev" / "sounds"
    (app / "sound_lab").mkdir(parents=True)
    (app / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (app / "sound_lab" / "__init__.py").write_text('APP_NAME = "Nexus Sound Lab"\n__version__ = "0.1.0"\n',
                                                   encoding="utf-8")
    (app / "CHANGELOG").write_text("Changelog: 02-11-2026 10:00:00\n\nAdded. Sliders.\n", encoding="utf-8")
    return tmp_path


def test_the_dialog_offers_the_version_and_sets_it(qapp, tmp_path):
    root = checkout(tmp_path)
    said = []
    dialog = versions.VersionsDialog(root, report=said.append)

    assert dialog.list.count() == 1 and "Nexus Sound Lab  0.1.0" in dialog.list.item(0).text()
    assert "offers 0.2.0 (minor: 1 Added)" in dialog.list.item(0).text()
    assert [dialog.version.itemText(i) for i in range(dialog.version.count())] == ["0.2.0", "0.1.1", "1.0.0"]
    assert dialog.set_button.isEnabled()

    dialog.notes.setText("The first.")
    dialog.set_version()

    app = root / "dev" / "sounds"
    assert (app / "VERSION").read_text() == "0.2.0\n"
    assert '__version__ = "0.2.0"' in (app / "sound_lab" / "__init__.py").read_text()
    assert "Version 0.2.0. The first." in (app / "CHANGELOG").read_text()
    assert said and said[0].startswith("Nexus Sound Lab is now 0.2.0: dev/sounds/VERSION")
    assert "set, not pushed yet" in dialog.list.item(0).text()     # can be set again
    dialog.version.setEditText("0.2")
    dialog.set_version()
    assert "no version" in dialog.state.text() and (app / "VERSION").read_text() == "0.2.0\n"
    dialog.close()


def test_the_tile_opens_the_dialog(qapp, monkeypatch):
    opened = []
    monkeypatch.setattr(main_window, "VersionsDialog",
                        lambda root, parent, report: type("D", (), {"exec": lambda self: opened.append(root)})())
    window = MainWindow(settings=None, suite="bc250-bazzite")
    tiles = {window.tiles.item(i).text(): window.tiles.item(i) for i in range(window.tiles.count())}

    window.click(tiles["Dev app versions"].data(Qt.ItemDataRole.UserRole))

    assert opened == [CHECKOUT]
    window.close()
