# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

from hdmi_cec import service
from hdmi_cec.runner import Result


class Systemctl:
    def __init__(self):
        self.calls, self.on = [], False

    def __call__(self, argv):
        self.calls.append(argv)
        if "is-enabled" in argv:
            return Result(0, "enabled\n") if self.on else Result(1, "disabled\n")
        if "enable" in argv:
            self.on = True
        if "disable" in argv:
            self.on = False                                 # "restart" leaves it as it is
        return Result(0, "")


def test_unit():
    text = service.unit_text("/venv/bin/python", Path("/app"), [service.RESTART, service.PAUSE])
    assert "WorkingDirectory=/app" in text
    assert "ExecStart=/venv/bin/python -m hdmi_cec.watcher --restart-picture --pause-media" in text
    assert "WantedBy=graphical-session.target" in text and "PartOf=graphical-session.target" in text


def test_enable_and_disable(tmp_path):
    run = Systemctl()
    assert not service.enabled(run, tmp_path)
    run.calls.clear()
    service.set_jobs(run, tmp_path, "/venv/bin/python", Path("/app"), {service.PAUSE})
    assert service.unit_path(tmp_path).is_file() and service.jobs(run, tmp_path) == {service.PAUSE}
    assert run.calls[:3] == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", service.UNIT],
                             ["systemctl", "--user", "restart", service.UNIT]]
    service.set_jobs(run, tmp_path, "/venv/bin/python", Path("/app"), {service.PAUSE, service.RESTART})
    assert service.jobs(run, tmp_path) == {service.PAUSE, service.RESTART}
    service.set_jobs(run, tmp_path, "/venv/bin/python", Path("/app"), set())
    service.disable(run, tmp_path)
    assert not service.unit_path(tmp_path).exists() and not service.enabled(run, tmp_path)
    run.calls.clear()
    service.disable(run, tmp_path)                       # nothing installed: nothing to do
    assert run.calls == []
