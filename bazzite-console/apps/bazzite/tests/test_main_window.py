# SPDX-License-Identifier: GPL-3.0-or-later
"""The window opens offscreen with the suite's header; the version and the icons are where the checks expect them."""

from __future__ import annotations

from bazzite_test import APP_ID, APP_NAME, INFO, LOGO_PATH, ROOT, __version__
from bazzite_test.main_window import MainWindow


def test_version_is_the_single_source():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__ == INFO.version


def test_icons_are_beside_the_package():
    assert LOGO_PATH.is_file() and LOGO_PATH.name == f"{APP_ID}.webp"
    assert (ROOT / "images" / f"{APP_ID}-128.png").is_file()


def test_window_opens_with_the_suites_header(qapp):
    window = MainWindow()
    window.show()
    assert window.windowTitle() == APP_NAME
    assert window.state.text() == "Ready" and window.state.kind == "ok"
    assert window.os_box.caption.text() == "Operating system"
    assert window.kernel_box.caption.text() == "Kernel"
    window.refresh()
    window.close()
