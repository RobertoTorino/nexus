# SPDX-License-Identifier: GPL-3.0-or-later
"""An app's log file (applog.py): where it is, what a line looks like, an uncaught error in it, the tail, and a
folder that cannot be made."""

from __future__ import annotations

import logging
import sys

from bc250_core import applog


def test_the_file_and_its_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert applog.log_file("bc250-x") == tmp_path / "data" / "bc250-x" / "bc250-x.log"
    path = applog.setup("bc250-test-app", tmp_path / "logs" / "app.log")
    assert path == tmp_path / "logs" / "app.log"
    assert applog.setup("bc250-test-app", tmp_path / "other.log") == tmp_path / "other.log"     # second: no change
    log = applog.logger("bc250-test-app")
    log.info("PCSX2 2.8.2 is installed.")
    log.error("Steam was not changed: no Steam")
    lines = path.read_text().splitlines()
    assert len(lines) == 2 and len(log.handlers) == 1
    assert lines[0].endswith(" INFO PCSX2 2.8.2 is installed.") and lines[1].split()[2] == "ERROR"
    assert lines[0][2] == "-" and lines[0][10] == " "                           # DD-MM-YYYY HH:MM:SS
    assert applog.tail(path) == "\n".join(lines) and applog.tail(path, 1) == lines[1]
    assert applog.tail(tmp_path / "none.log") == ""
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)


def test_a_suites_app_logs_in_the_suites_folder(tmp_path, monkeypatch):
    """The Windows Portable Suite's apps name their suite: %LOCALAPPDATA%\\windows-portable-suite\\<app id>; an app
    that names none (the BC250 suite's) keeps ~/.local/share/<app id>, on Windows too."""
    from bc250_core import platform
    monkeypatch.setattr(platform, "WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert applog.log_file("windows-portable-test", "windows-portable-suite") == \
        tmp_path / "Local" / "windows-portable-suite" / "windows-portable-test" / "windows-portable-test.log"
    assert applog.log_file("bc250-sftp-tools") == tmp_path / "data" / "bc250-sftp-tools" / "bc250-sftp-tools.log"
    path = applog.setup("windows-portable-test-log", suite="windows-portable-suite")
    assert path.parent == tmp_path / "Local" / "windows-portable-suite" / "windows-portable-test-log"
    log = applog.logger("windows-portable-test-log")
    log.info("Started.")
    assert path.read_text().endswith(" INFO Started.\n")
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)


def test_an_uncaught_error_is_logged(tmp_path, monkeypatch):
    reported = []
    monkeypatch.setattr(sys, "excepthook", lambda *args: reported.append(args[1]))
    path = applog.setup("bc250-test-crash", tmp_path / "crash.log")
    try:
        raise ValueError("boom")
    except ValueError as error:
        sys.excepthook(type(error), error, error.__traceback__)
    text = path.read_text()
    assert "CRITICAL Uncaught error" in text and "ValueError: boom" in text
    assert [str(e) for e in reported] == ["boom"]                                 # Python's own report still comes
    log = applog.logger("bc250-test-crash")
    for handler in list(log.handlers):
        handler.close()
        log.removeHandler(handler)


def test_without_a_folder_the_log_goes_to_stderr(tmp_path, capsys):
    blocker = tmp_path / "file"
    blocker.write_text("")
    path = applog.setup("bc250-test-noroom", blocker / "app.log")              # a file where the folder would be
    log = applog.logger("bc250-test-noroom")
    assert isinstance(log.handlers[0], logging.StreamHandler) and not isinstance(log.handlers[0],
                                                                                 logging.FileHandler)
    log.info("still said")
    assert "still said" in capsys.readouterr().err and path == blocker / "app.log"
    log.handlers.clear()
