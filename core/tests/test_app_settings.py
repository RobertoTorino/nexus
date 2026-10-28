# SPDX-License-Identifier: GPL-3.0-or-later
"""create_app(): on Windows an app with .ini settings keeps a bare QSettings() out of the registry (owner, 29-10-2026:
the portal's and PCSX2 Manager's settings were under HKCU\\Software\\windows-portable-suite, %APPDATA% was empty)."""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from bc250_core import app as app_module
from bc250_core.appinfo import AppInfo


def test_a_bare_qsettings_is_an_ini_file_on_windows(qapp, monkeypatch, tmp_path):
    before = QSettings.defaultFormat()
    try:
        QSettings.setDefaultFormat(QSettings.Format.NativeFormat)
        monkeypatch.setattr(app_module, "WINDOWS", False)
        app_module.create_app(AppInfo(app_id="x-test", name="X", version="0.1.0", settings_org="x-suite",
                                      settings_ini=True))
        assert QSettings.defaultFormat() == QSettings.Format.NativeFormat      # Linux: as released
        monkeypatch.setattr(app_module, "WINDOWS", True)
        app_module.create_app(AppInfo(app_id="x-test", name="X", version="0.1.0", settings_org="x-suite"))
        assert QSettings.defaultFormat() == QSettings.Format.NativeFormat      # no .ini declared: unchanged
        app_module.create_app(AppInfo(app_id="x-test", name="X", version="0.1.0", settings_org="x-suite",
                                      settings_ini=True))
        assert QSettings.defaultFormat() == QSettings.Format.IniFormat
        assert QSettings().format() == QSettings.Format.IniFormat
    finally:
        QSettings.setDefaultFormat(before)
