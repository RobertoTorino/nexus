# SPDX-License-Identifier: GPL-3.0-or-later
"""The optional systemd --user unit that resumes an --auto run after a reboot."""

from __future__ import annotations

import pytest

from cu_bisect import service


def test_unit_resumes_the_run_with_its_settings(home):
    text = service._unit_contents("/opt/x/bc250-cu-bisect.sh", 240, 4)
    assert "ExecStart=/usr/bin/env bash /opt/x/bc250-cu-bisect.sh --auto -t 240 -r 4" in text
    assert "StandardOutput=append:%h/.local/share/bc250-cu-bisect/auto.log" in text
    assert "WantedBy=default.target" in text
    assert service.unit_path() == home / ".config" / "systemd" / "user" / "bc250-cu-bisect-auto.service"


def test_install_writes_and_enables_the_unit(monkeypatch):
    calls = []
    monkeypatch.setattr(service.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(service.subprocess, "run", lambda args, check: calls.append(args))
    assert not service.is_installed()
    service.install("/opt/x/bc250-cu-bisect.sh", 180, 3)
    assert service.is_installed()
    assert calls == [["systemctl", "--user", "daemon-reload"],
                     ["systemctl", "--user", "enable", "--now", "bc250-cu-bisect-auto.service"]]


def test_without_systemctl_the_unit_is_written_and_the_error_says_so(monkeypatch):
    monkeypatch.setattr(service.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="install the unit manually"):
        service.install("/opt/x/bc250-cu-bisect.sh", 180, 3)
    assert service.is_installed()
