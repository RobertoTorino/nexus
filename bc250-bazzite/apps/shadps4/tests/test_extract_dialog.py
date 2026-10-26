# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract PKG against the synthetic PKG: the preview, a package given when it opens or later, an extraction into a
game folder, the empty-folder guardrail, preview-only, salvage mode and the rename to CONTENT_ID; the output offered
from the game folders, the standalone app's folders adopted, no closing during an extraction; and the main window's
Extract PKG…, a dropped package and the games found after an extraction. The worker runs in its QThread as in the
app; the tests pump the event loop."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from PyQt6.QtCore import QElapsedTimer, QEvent, QEventLoop, QMimeData, QPointF, QSettings, Qt, QThread, QUrl
from PyQt6.QtGui import QColor, QContextMenuEvent, QDesktopServices, QDropEvent, QImage, QMouseEvent
from PyQt6.QtWidgets import QDialog, QFileDialog, QMenu, QMessageBox

from shadps4_manager import INFO, extract_dialog
from shadps4_manager.extract_dialog import OUTPUT_FOLDER_KEY, PKG_FOLDER_KEY, ExtractDialog
from shadps4_manager.main_window import MainWindow, ShadSettings


def pump(app, done, deadline_ms: int = 30000) -> None:
    timer = QElapsedTimer()
    timer.start()
    while not done() and timer.elapsed() < deadline_ms:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        QThread.msleep(5)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_dialog, "app_data_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()
    return tmp_path / "state"


@pytest.fixture
def window(qapp, state, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"unexpected warning: {a[1:3]}"))
    win = ExtractDialog(ShadSettings(INFO), [])
    win.show()
    yield win
    win.close()


def test_preview_shows_sfo_and_icon(window, built_pkg):
    window.pkg_input.setText(str(built_pkg.path))
    window.update_sfo_preview(str(built_pkg.path))
    preview = window.sfo_preview.toPlainText()
    assert "CATEGORY: gd" in preview
    assert "TITLE: Synthetic Test Title" in preview
    assert f"CONTENT_ID: {built_pkg.content_id}" in preview
    assert f"TITLE_ID: {built_pkg.title_id}" in preview
    assert window.icon_preview.pixmap() is not None and not window.icon_preview.pixmap().isNull()
    assert window.icon_preview.pkg_loaded
    assert "Preview: icon0.png loaded" in window.log_output.toPlainText()


def test_package_given_when_it_opens_or_later(qapp, window, built_pkg, tmp_path, monkeypatch):
    window.open_pkg(str(built_pkg.path))                       # what a later launch with a package does
    assert window.pkg_input.text() == str(built_pkg.path)
    assert f"TITLE_ID: {built_pkg.title_id}" in window.sfo_preview.toPlainText()

    monkeypatch.setattr(extract_dialog, "app_data_dir", lambda: tmp_path / "state2")   # the first window's crash
    (tmp_path / "state2").mkdir()                                                    # marker is not this one's
    started = ExtractDialog(ShadSettings(INFO), [], initial_pkg=str(built_pkg.path))
    pump(qapp, lambda: "TITLE_ID" in started.sfo_preview.toPlainText(), 5000)
    assert started.pkg_input.text() == str(built_pkg.path)
    assert f"TITLE_ID: {built_pkg.title_id}" in started.sfo_preview.toPlainText()
    started.close()


def test_extract_guardrail_and_preview_only(qapp, window, built_pkg, tmp_path, state, monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    window.pkg_input.setText(str(built_pkg.path))
    window.output_input.setText(str(out_dir))

    window.on_extract()
    assert not window.extract_btn.isEnabled()
    pump(qapp, lambda: window._thread is None)
    log = window.log_output.toPlainText()
    assert "=== Extraction complete! ===" in log, log
    assert window.extract_btn.isEnabled() and window.extracted
    assert window.progress_bar.value() == window.progress_bar.maximum()

    target = out_dir / built_pkg.title_id
    assert (target / "eboot.bin").read_bytes() == built_pkg.expected_files["eboot.bin"]
    assert (target / "data" / "big.bin").read_bytes() == built_pkg.expected_files["data/big.bin"]
    assert (target / "sce_sys" / "param.sfo").read_bytes() == built_pkg.sce_sys_plain["param.sfo"]
    assert (target / "filelist.txt").is_file()
    assert [Path(p) for p in opened] == [target]
    assert not (state / "pkgxtractor.progress").exists()
    assert "=== Extraction complete! ===" in (state / "pkgxtractor.log").read_text(encoding="utf-8")

    # The same folder again trips the guardrail: nothing is overwritten.
    window.on_extract()
    pump(qapp, lambda: window._thread is None)
    assert "Guardrail: target output folder is not empty." in window.log_output.toPlainText()

    # Preview-only into a fresh folder writes sce_sys and the file list, not the payload.
    preview_dir = tmp_path / "preview"
    preview_dir.mkdir()
    window.output_input.setText(str(preview_dir))
    window.on_preview_only()
    pump(qapp, lambda: window._thread is None)
    assert "=== Preview complete (metadata extracted) ===" in window.log_output.toPlainText()
    assert (preview_dir / built_pkg.title_id / "filelist.txt").is_file()
    assert (preview_dir / built_pkg.title_id / "sce_sys" / "icon0.png").is_file()
    assert not (preview_dir / built_pkg.title_id / "eboot.bin").exists()


def test_an_update_goes_beside_its_game(qapp, window, built_pkg, tmp_path, monkeypatch):
    # An update (CATEGORY gp) goes into TITLE_ID-UPDATE beside the game, which shadPS4 lays over the game; the game's
    # folder stays as it was. A second update replaces the first only when the user says so and it extracted.
    from pkg_builder import build_pkg, default_tree
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)
    asked: list[str] = []
    answer = [QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(QMessageBox, "question", lambda _p, _t, text, *a: asked.append(text) or answer[0])
    out = tmp_path / "games"
    out.mkdir()
    game, update = out / built_pkg.title_id, out / f"{built_pkg.title_id}-UPDATE"
    window.output_input.setText(str(out))

    def extract(pkg_path):
        window.pkg_input.setText(str(pkg_path))
        window.on_extract()
        pump(qapp, lambda: window._thread is None)
        return window.log_output.toPlainText()

    # Without its game a gp package goes into TITLE_ID, as a game with its update in it does.
    first = build_pkg(tmp_path / "update1.pkg", default_tree(), category="gp", app_ver="01.01")
    assert "=== Extraction complete! ===" in extract(first.path)
    assert (game / "eboot.bin").read_bytes() == first.expected_files["eboot.bin"]
    shutil.rmtree(game)

    assert "=== Extraction complete! ===" in extract(built_pkg.path)
    log = extract(first.path)
    assert "=== Extraction complete! ===" in log and "lays over the game" in log, log
    assert (game / "eboot.bin").read_bytes() == built_pkg.expected_files["eboot.bin"]
    assert (update / "eboot.bin").read_bytes() == first.expected_files["eboot.bin"]
    assert not asked

    # A newer update: the user says no, nothing changes; yes, it takes the old one's place.
    second = build_pkg(tmp_path / "update2.pkg", default_tree(), category="gp", app_ver="01.02")
    answer[0] = QMessageBox.StandardButton.No
    extract(second.path)
    assert len(asked) == 1 and str(update) in asked[0]
    assert (update / "eboot.bin").read_bytes() == first.expected_files["eboot.bin"]
    answer[0] = QMessageBox.StandardButton.Yes
    log = extract(second.path)
    assert "The new update replaced the old one" in log, log
    assert (update / "eboot.bin").read_bytes() == second.expected_files["eboot.bin"]
    assert sorted(p.name for p in out.iterdir()) == [game.name, update.name]

    # One that fails to extract leaves the old update as it was.
    third = build_pkg(tmp_path / "update3.pkg", default_tree(), category="gp", app_ver="01.03")
    monkeypatch.setattr(extract_dialog.PKG, "extract_files", lambda self, index: (_ for _ in ()).throw(OSError("bad")))
    log = extract(third.path)
    assert "stays as it was" in log, log
    assert (update / "eboot.bin").read_bytes() == second.expected_files["eboot.bin"]
    assert sorted(p.name for p in out.iterdir()) == [game.name, update.name]


def test_preview_only_is_no_extraction(qapp, window, built_pkg, tmp_path):
    window.pkg_input.setText(str(built_pkg.path))
    window.output_input.setText(str(tmp_path))
    window.on_preview_only()
    pump(qapp, lambda: window._thread is None)
    assert not window.extracted                     # nothing for the game list


def test_salvage_mode_is_passed_to_the_worker(qapp, window, built_pkg, tmp_path, monkeypatch):
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    window.pkg_input.setText(str(built_pkg.path))
    window.output_input.setText(str(out_dir))
    window.salvage_check.setChecked(True)
    window.on_extract()
    pump(qapp, lambda: window._thread is None)
    log = window.log_output.toPlainText()
    assert "Recovery Summary: skipped entries = 0" in log
    assert window.salvage_check.isEnabled()


def test_rename_to_content_id(window, built_pkg, tmp_path):
    copy = tmp_path / "some download.pkg"
    shutil.copyfile(built_pkg.path, copy)
    window.pkg_input.setText(str(copy))
    window.on_rename_pkg_to_content_id()
    renamed = tmp_path / f"{built_pkg.content_id}-0100.pkg"   # a game: CONTENT_ID-APP_VER
    assert renamed.is_file()
    assert not copy.exists()
    assert window.pkg_input.text() == str(renamed)
    assert "Renamed PKG to CONTENT_ID-APP_VER" in window.log_output.toPlainText()


def test_right_click_on_the_icon_offers_the_menu(qapp, window, tmp_path, monkeypatch):
    # A right click opened the picture full screen; on Linux, where Qt shows the context menu on the press, the
    # menu never came. Now only a left click opens it, and a right click offers the menu.
    picture = tmp_path / "pic0.png"
    image = QImage(64, 36, QImage.Format.Format_RGB32)
    image.fill(QColor("#0000ff"))
    assert image.save(str(picture))
    label = window.icon_preview
    label.pkg_loaded, label.preview_image_path = True, str(picture)
    centre = QPointF(label.width() / 2, label.height() / 2)

    def press(button):
        label.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, centre, label.mapToGlobal(centre),
                                          button, button, Qt.KeyboardModifier.NoModifier))

    press(Qt.MouseButton.RightButton)
    assert label._viewer is None

    offered = []
    monkeypatch.setattr(QMenu, "exec", lambda menu, *a: offered.extend(a.text() for a in menu.actions()))
    label.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, centre.toPoint(),
                                             label.mapToGlobal(centre).toPoint()))
    assert offered == ["show full screen", "save as wallpaper"]

    saved = tmp_path / "saved.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(saved), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    label._save_as_wallpaper()
    assert QImage(str(saved)).pixelColor(1, 1).name() == "#0000ff"

    press(Qt.MouseButton.LeftButton)
    assert label._viewer is not None and label._viewer.isVisible()
    label._viewer.close()


def test_empty_inputs_warn_instead_of_starting(qapp, window, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *a: warnings.append(text))
    window.output_input.clear()
    window.on_extract()
    assert warnings == ["Please select a PKG file first."]
    window.pkg_input.setText("whatever.pkg")
    window.on_extract()
    assert warnings[-1] == "Please select a destination folder."
    assert window._thread is None


def test_the_output_is_a_game_folder(qapp, state, tmp_path):
    """No folder used before: the first game folder; the note says whether the game will show up."""
    games, other = tmp_path / "games", tmp_path / "other"
    games.mkdir()
    other.mkdir()
    dialog = ExtractDialog(ShadSettings(INFO), [games])
    assert dialog.output_input.text() == str(games)
    assert "shows up in the list" in dialog.output_note.text()
    dialog.output_input.setText(str(other))
    assert "Not one of shadPS4's game folders" in dialog.output_note.text() and str(games) in dialog.output_note.text()
    dialog.reject()
    alone = ExtractDialog(ShadSettings(INFO), [])
    alone.output_input.setText(str(other))
    assert "no game folder yet" in alone.output_note.text()
    alone.reject()


def test_the_last_output_folder_comes_first(qapp, state, tmp_path):
    games, last = tmp_path / "games", tmp_path / "last"
    games.mkdir()
    last.mkdir()
    settings = ShadSettings(INFO)
    settings.qsettings.setValue(OUTPUT_FOLDER_KEY, str(last))
    dialog = ExtractDialog(settings, [games])
    assert dialog.output_input.text() == str(last)
    dialog.reject()
    shutil.rmtree(last)                                         # gone: the game folder again
    dialog = ExtractDialog(settings, [games])
    assert dialog.output_input.text() == str(games)
    dialog.reject()


def test_the_standalone_apps_folders_are_adopted_once(qapp, state, tmp_path):
    old = QSettings(str(tmp_path / "config" / "bazzite-pkgxtractor" / "bazzite-pkgxtractor.ini"),
                    QSettings.Format.IniFormat)
    (tmp_path / "out").mkdir()
    old.setValue("paths/lastPkgDir", str(tmp_path / "downloads"))
    old.setValue("paths/lastOutputDir", str(tmp_path / "out"))
    old.sync()
    settings = ShadSettings(INFO)
    dialog = ExtractDialog(settings, [])
    assert dialog._last_pkg_dir == str(tmp_path / "downloads")
    assert dialog.output_input.text() == str(tmp_path / "out")
    dialog.reject()
    assert settings.qsettings.value(PKG_FOLDER_KEY) == str(tmp_path / "downloads")
    old.setValue("paths/lastPkgDir", str(tmp_path / "elsewhere"))     # changed there later: this app's own stays
    old.sync()
    dialog = ExtractDialog(settings, [])
    assert dialog._last_pkg_dir == str(tmp_path / "downloads")
    dialog.reject()


def test_no_closing_while_it_extracts(qapp, window, built_pkg, tmp_path, monkeypatch):
    """Its thread would be destroyed under it: Esc does nothing, closing says to wait."""
    told: list[str] = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text, *a: told.append(text))
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)
    window.pkg_input.setText(str(built_pkg.path))
    window.output_input.setText(str(tmp_path))
    window.on_extract()
    assert window.is_busy()
    window.reject()
    window.close()
    assert window.isVisible() and told and "An extraction is running" in told[0]
    pump(qapp, lambda: window._thread is None)
    window.reject()
    assert not window.isVisible()


def test_the_crash_marker_lives_while_it_is_open(qapp, state, monkeypatch):
    dialog = ExtractDialog(ShadSettings(INFO), [])
    assert (state / "pkgxtractor.state").is_file()
    dialog.reject()
    assert not (state / "pkgxtractor.state").exists()
    (state / "pkgxtractor.state").write_text("running\n")       # a run that did not end
    (state / "pkgxtractor.progress").write_text("current=3\ntotal=9\n")
    warned: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text, *a: warned.append(text))
    ExtractDialog(ShadSettings(INFO), []).reject()
    assert warned and "Extract PKG appears to have crashed" in warned[0] and "current=3" in warned[0]


# --- The main window ---------------------------------------------------------------------------------------------

@pytest.fixture
def manager(qapp, tmp_path, state):
    games = tmp_path / "games"
    games.mkdir()
    shad = tmp_path / "shadPS4"
    shad.mkdir()
    (shad / "config.json").write_text(json.dumps({"General": {"install_dirs": [{"enabled": True,
                                                                                 "path": str(games)}]}}))
    win = MainWindow(home=tmp_path / "emulator", shad_home=shad, steam_dir=tmp_path / "Steam",
                     run=tmp_path / "bin" / "bc250-shadps4-run", newer_release=lambda: None,
                     devices=tmp_path / "no-devices", sound_state=tmp_path / "no-sound")
    win.release_check.stop()
    yield win, games
    win.close()


def test_extract_pkg_is_games_install(manager):
    win, games = manager
    assert (win.package_pill.value.text(), win.package_pill.caption.text()) == ("Games", "Install")
    assert win.package_pill.isEnabled()                                         # needs no shadPS4


def test_an_extracted_game_shows_up(qapp, manager, built_pkg, monkeypatch):
    """Extract PKG on the game folders: the extraction into the first one, and the games found again after."""
    win, games = manager
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: None)
    seen: list[ExtractDialog] = []

    def run(dialog):
        seen.append(dialog)
        pump(qapp, lambda: dialog.pkg_input.text() != "", 5000)     # the package loads when its loop runs
        assert dialog.output_input.text() == str(games) and dialog.pkg_input.text() == str(built_pkg.path)
        dialog.on_extract()
        pump(qapp, lambda: dialog._thread is None)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(ExtractDialog, "exec", run)
    assert win.games == []
    win.open_extract(str(built_pkg.path))
    assert seen and win.extract_dialog is None
    assert [g.title_id for g in win.games] == [built_pkg.title_id]


def test_a_later_package_goes_into_the_open_window(manager, built_pkg, monkeypatch):
    win, _games = manager
    loaded: list[str] = []

    def run(dialog):
        monkeypatch.setattr(dialog, "open_pkg", loaded.append)
        win.open_extract("/second/launch.pkg")                   # a launch with a package while it is open
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(ExtractDialog, "exec", run)
    win.open_extract()
    assert loaded == ["/second/launch.pkg"]


def test_a_package_dropped_on_the_window(qapp, manager, monkeypatch):
    win, _games = manager
    opened: list[str | None] = []
    monkeypatch.setattr(win, "open_extract", opened.append)
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile("/downloads/readme.txt"), QUrl.fromLocalFile("/downloads/Game.PKG")])
    event = QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, data, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    win.dropEvent(event)
    pump(qapp, lambda: bool(opened), 2000)
    assert opened == ["/downloads/Game.PKG"]


def test_without_cryptography_it_says_what_to_do(manager, monkeypatch):
    import builtins
    win, _games = manager
    real = builtins.__import__

    def no_crypto(name, *args, **kwargs):
        if name.endswith("extract_dialog") or (args and args[2] and "extract_dialog" in args[2]):
            raise ImportError("No module named 'cryptography'")
        return real(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_crypto)
    win.open_extract()
    assert "needs the cryptography package" in win.output.toPlainText()
