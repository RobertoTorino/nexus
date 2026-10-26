# SPDX-License-Identifier: GPL-3.0-or-later

from sftp_tools import app_logging


def test_logs_to_file(tmp_path):
    log = tmp_path / "logs" / "app.log"
    app_logging.setup_logging(log)
    app_logging.get_logger().error("boom")
    for h in app_logging.get_logger().handlers:
        h.flush()
    assert "boom" in log.read_text()
