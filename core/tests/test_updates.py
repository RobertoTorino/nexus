# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import threading
import urllib.error

import pytest
from PyQt6.QtCore import QEventLoop, QTimer

from bc250_core.updates import ReleaseInfo, UpdateChecker, UpdateStatus, latest_release, repo_slug, version_tuple

REPO = "RobertoTorino/nexus"


def _rel(tag, *, draft=False, pre=False, date="2026-10-01", assets=()):
    return {"tag_name": tag, "draft": draft, "prerelease": pre, "published_at": f"{date}T04:00:00Z",
            "html_url": f"https://github.com/{REPO}/releases/tag/{tag}", "assets": list(assets)}


def test_repo_slug():
    assert repo_slug("https://github.com/RobertoTorino/nexus/") == REPO
    assert repo_slug("https://github.com/a/b.git") == "a/b"


def test_version_tuple():
    assert version_tuple("governor-v0.10.2") == (0, 10, 2)
    assert version_tuple("nothing") == ()


def test_latest_without_prefix_uses_latest_endpoint():
    urls = []

    def fetch(url):
        urls.append(url)
        return _rel("v1.2.0", assets=[{"name": "HelixSR-1.2.0.zip", "browser_download_url": "u", "size": 5}])

    info = latest_release("lonewolf0622/HelixSR", fetch=fetch)
    assert urls == ["https://api.github.com/repos/lonewolf0622/HelixSR/releases/latest"]
    assert (info.version, info.published, info.asset_name, info.asset_size) == \
        ("1.2.0", "2026-10-01", "HelixSR-1.2.0.zip", 5)


def test_prefix_picks_this_apps_newest_release():
    # The suite's newest release overall belongs to another app; 0.10.0 must beat 0.9.0 numerically.
    releases = [_rel("portal-v0.3.0"), _rel("governor-v0.9.0"), _rel("governor-v0.10.0", date="2026-09-01"),
                _rel("governor-v0.11.0", pre=True), _rel("governor-v0.12.0", draft=True),
                _rel("bazzite-test-v2.0.0")]
    info = latest_release(REPO, "governor-v", fetch=lambda url: releases)
    assert (info.version, info.tag, info.error) == ("0.10.0", "governor-v0.10.0", "")


def test_prefix_without_match():
    info = latest_release(REPO, "cu-bisect-v", fetch=lambda url: [_rel("portal-v0.1.0")])
    assert info.version == "" and "cu-bisect-v*" in info.error


@pytest.mark.parametrize("exc, word", [
    (urllib.error.HTTPError("u", 403, "rate limited", None, None), "403"),
    (urllib.error.URLError("Name or service not known: x"), "no connection"),
])
def test_errors_never_raise(exc, word):
    def fetch(url):
        raise exc
    info = latest_release(REPO, "governor-v", fetch=fetch)
    assert word in info.error and info.url.endswith("/releases")


def test_unexpected_tag():
    assert "unexpected tag" in latest_release("a/b", fetch=lambda url: _rel("nightly")).error


@pytest.mark.parametrize("installed, latest, kind, available", [
    ("0.1.0", ReleaseInfo("0.2.0", published="2026-10-01"), "warn", True),
    ("0.2.0", ReleaseInfo("0.2.0", published="2026-10-01"), "ok", False),
    ("", ReleaseInfo("0.2.0", published="2026-10-01"), "info", False),
    ("0.1.0", ReleaseInfo(error="no connection (x)"), "neutral", False),
])
def test_status(installed, latest, kind, available):
    status = UpdateStatus("Governor", installed, latest)
    assert (status.kind, status.update_available) == (kind, available)
    assert status.summary


def test_checker_runs_job_off_thread(qapp):
    main = threading.get_ident()
    checker = UpdateChecker()
    got = []
    loop = QEventLoop()
    checker.finished.connect(lambda r: (got.append(r), loop.quit()))
    assert checker.start(threading.get_ident)
    assert checker.running
    assert not checker.start(lambda: 0)                 # one at a time
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert got and got[0] != main
    assert not checker.running
