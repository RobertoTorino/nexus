# SPDX-License-Identifier: GPL-3.0-or-later
"""check on bc250_core: the app starts, its settings stay in the same .ini file, and its widgets are core's.

No test runs: the window is built with the fake engine (development/tools/fake-test-bazzite.sh) and closed."""

from __future__ import annotations

from pathlib import Path

from bc250_core import theme
from bc250_core import widgets as core_widgets

ENGINE = Path(__file__).resolve().parents[1] / "development" / "tools" / "fake-test-bazzite.sh"


def test_constants_come_from_core():
    from bazzite_check import INFO, __version__, dashboard, widgets
    assert (INFO.app_id, INFO.version, INFO.tag_prefix) == ("bc250-bazzite-test", __version__, "check-v")
    assert dashboard.ACCENT == theme.ACCENT and dashboard.header_font is theme.header_font
    assert widgets.RoundedToolTip is core_widgets.RoundedToolTip and widgets.ClickableLogo is core_widgets.ClickableLogo


def test_settings_file_unchanged(sandbox):
    from bazzite_check.settings import AppSettings
    settings = AppSettings()
    assert Path(settings.qsettings.fileName()).name == "bc250-bazzite-test.ini"
    assert settings.get("run/stress_duration") == 120
    settings.set("run/stress_duration", 300)
    assert AppSettings().get("run/stress_duration") == 300


def test_main_window_builds(sandbox, qapp):
    import gc

    from PyQt6.QtCore import QCoreApplication, QEvent

    from bc250_core.app import create_app
    from bazzite_check import INFO
    from bazzite_check.main_window import MainWindow
    from bazzite_check.runner import TestRunner
    create_app(INFO)
    window = MainWindow(TestRunner(str(ENGINE), use_sudo=False))
    window.show()
    qapp.processEvents()                        # runs the deferred history load
    assert window.windowTitle() == INFO.display_name
    from bazzite_check.readme import ReadmeView
    rows = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert "Help" in rows and "Manual" not in rows                     # the chapter of the manual, as Help
    assert isinstance(window.stack.widget(rows.index("Help")), ReadmeView)
    assert "Help" not in window.settings_overlay.SECTIONS               # no second help in Settings
    assert window.settings_overlay.pages.count() == len(window.settings_overlay.SECTIONS)
    window.shutdown()
    window.close()
    # Dispose of the window here, while the event loop is alive, instead of leaving it to whenever Python's garbage
    # collector gets to it (the app itself keeps its window until it quits). A crash then shows up in this test.
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    del window
    gc.collect()


def test_manual_is_the_chapter(tmp_path):
    from bazzite_check import readme
    assert readme.manual_path() == readme.DOCS_DIR.parents[1] / "docs" / "apps" / "check.md"   # checkout
    (tmp_path / "MANUAL.md").write_text("# shipped\n")                                               # release
    assert readme.manual_path(tmp_path) == tmp_path / "MANUAL.md"


def test_manual_markdown_for_qt(tmp_path):
    from bazzite_check import readme
    text = readme.manual_markdown("![logo](../assets/check/x.png){ .app-logo }\n", tmp_path)
    assert text == f"![logo]({(tmp_path / 'images').as_posix()}/x.png)\n"


def test_other_chapters_open_online():
    from bazzite_check import readme
    base = readme.SUITE_MANUAL_URL
    assert readme.online_url("cu-bisect.md") == base + "apps/cu-bisect/"
    assert readme.online_url("../SECURITY.md#verifying-a-download") == base + "SECURITY/#verifying-a-download"
    assert readme.online_url("../development/index.md") == base + "development/"
    assert readme.online_url("../index.md") == base


def test_manual_view_shows_the_chapter(qapp):
    from bazzite_check.readme import ReadmeView
    view = ReadmeView()
    assert "Read-only diagnostics" in view.browser.toPlainText() and "{ .app-logo }" not in view.browser.toPlainText()
    view.close()


def test_results_preview_shows_image_and_emits_open_paths(qapp, tmp_path):
    from PyQt6.QtGui import QPixmap

    from bazzite_check.dashboard import ResultsPreview

    image_path = tmp_path / "results.png"
    pixmap = QPixmap(24, 16)
    pixmap.fill()
    assert pixmap.save(str(image_path), "PNG")

    preview = ResultsPreview()
    opened_images = []
    opened_folders = []
    preview.image_requested.connect(opened_images.append)
    preview.folder_requested.connect(opened_folders.append)

    assert preview.set_image(str(image_path))
    assert not preview.isHidden()
    assert preview.folder.text() == f"Folder: {tmp_path}"
    preview.image.click()
    preview.open_folder.click()
    assert opened_images == [str(image_path)]
    assert opened_folders == [str(tmp_path)]


def test_print_results_opens_saved_png_and_shows_preview(sandbox, qapp, tmp_path, monkeypatch):
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import QFileDialog

    from bc250_core.app import create_app
    from bazzite_check import INFO
    from bazzite_check.main_window import MainWindow
    from bazzite_check.runner import TestRunner

    create_app(INFO)
    window = MainWindow(TestRunner(str(ENGINE), use_sudo=False))
    image_path = tmp_path / "shared results.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(image_path), "PNG image (*.png)"))
    opened_urls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened_urls.append(url) or True)
    from bazzite_check.results_dialog import ResultsCardDialog
    monkeypatch.setattr(ResultsCardDialog, "exec", lambda self: self.save_button.click())   # Save… in the preview

    window._print_results()

    assert image_path.is_file()
    assert not window.results_preview.isHidden()
    assert not window.results_preview.image.icon().isNull()
    assert window.results_preview.folder.text() == f"Folder: {tmp_path}"
    assert len(opened_urls) == 1
    assert opened_urls[0].toLocalFile() == str(image_path)
    window.shutdown()
    window.close()
    window.deleteLater()
    qapp.processEvents()


def test_the_results_card_preview_copies_and_shares(qapp, tmp_path, monkeypatch):
    """Print results shows the card first (owner, 04-11-2026), with Save…, Copy and Share; Share is a menu (owner,
    05-11-2026): each phone KDE Connect reaches, Email… and Show in file manager, the card written to the results
    folder first."""
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from bazzite_check import results_dialog as rd

    card = QPixmap(1200, 900)
    card.fill()
    saved, calls = [], []

    def fake_run(argv):
        calls.append(argv)
        if argv[:2] == ["kdeconnect-cli", "--list-available"]:
            return 0, "a1b2c3 Pixel 9\n"
        return 0, ""
    monkeypatch.setattr(rd.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    folder = tmp_path / "Desktop" / "bc250-bazzite-test"
    dialog = rd.ResultsCardDialog(card, saved.append, folder, run_=fake_run)
    said = []
    dialog.shared.connect(said.append)
    shown = dialog.picture.pixmap()
    assert shown.width() <= rd.PREVIEW.width() and shown.height() <= rd.PREVIEW.height()   # scaled to fit
    dialog.save_button.click()
    assert saved == [card]
    dialog.copy_button.click()
    assert QApplication.clipboard().pixmap().size() == card.size() and said[-1].startswith("Results card copied")
    dialog.fill_share_menu()
    entries = [(a.text(), a.isEnabled()) for a in dialog.share_menu.actions() if not a.isSeparator()]
    assert entries == [("Send to Pixel 9 (KDE Connect)", True), ("Email…", True), ("Show in file manager", True)]
    card_file = folder / rd.SHARE_NAME
    assert dialog.share("phone", "a1b2c3", "Pixel 9") == "Results card sent to Pixel 9."
    assert calls[-1] == ["kdeconnect-cli", "--share", str(card_file), "-d", "a1b2c3"] and card_file.is_file()
    dialog.share("email")
    assert calls[-1] == ["xdg-email", "--subject", rd.EMAIL_SUBJECT, "--attach", str(card_file)]
    monkeypatch.setattr(dialog, "show_in_files", lambda path: path == card_file)
    assert dialog.share("files").startswith("The file manager shows the card")
    # No phone in reach, and a mail app that does not open: said, not silent.
    dialog.run = lambda argv: (1, "") if argv[0] == "kdeconnect-cli" else (3, "no mail app")
    dialog.fill_share_menu()
    assert [a.isEnabled() for a in dialog.share_menu.actions() if not a.isSeparator()][0] is False
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a[2]))
    dialog.share("email")
    assert "No mail app opened: no mail app" in warned[0] and str(card_file) in warned[0]
