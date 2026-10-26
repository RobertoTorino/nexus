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
