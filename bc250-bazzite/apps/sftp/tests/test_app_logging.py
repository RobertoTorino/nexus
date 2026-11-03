# SPDX-License-Identifier: GPL-3.0-or-later

from sftp_tools import app_logging


def test_logs_to_file(tmp_path):
    log = tmp_path / "logs" / "app.log"
    app_logging.setup_logging(log)
    app_logging.get_logger().error("boom")
    for h in app_logging.get_logger().handlers:
        h.flush()
    assert "boom" in log.read_text()


def test_the_log_writes_the_users_folders_as_home(tmp_path, monkeypatch):
    """No user name in the log (owner, 03-11-2026: the privacy rule): the home folder as ~ in every line."""
    import logging
    from sftp_tools import app_logging
    monkeypatch.setenv("HOME", str(tmp_path))
    logger = app_logging.get_logger()
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    app_logging.setup_logging(tmp_path / "log" / "app.log")
    logger.error("Cannot read local folder %s: %s", tmp_path / "Pictures", "permission denied")
    for handler in list(logger.handlers):
        handler.flush()
        logger.removeHandler(handler)
        handler.close()
    text = (tmp_path / "log" / "app.log").read_text()
    assert "Cannot read local folder ~/Pictures: permission denied" in text and str(tmp_path) not in text
