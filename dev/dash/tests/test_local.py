# SPDX-License-Identifier: GPL-3.0-or-later
"""Test local apps: the suite's portal and apps from the checkout, the wikis served with mkdocs serve, and what a
click on one of them does (moved from Nexus Release Tool's Test on this board, owner 04-11-2026)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest
from PyQt6.QtGui import QColor

from nexus_dashboard import CHECKOUT, local, main_window
from nexus_dashboard.main_window import MainWindow


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def card(key: str, changes_board: bool = False) -> str:
    return (f'[apps.{key}]\nname = "{key}"\nsummary = "s"\ntag = "{key}-v0.1.0"\nsha256 = ""\nrequired = false\n'
            f'changes_board = {"true" if changes_board else "false"}\n\n')


@pytest.fixture
def nexus(tmp_path) -> Path:
    """A checkout laid out as Nexus: the suite bc with alpha (a window), beta (a window, changes the board), a
    standalone app whose package is a level deeper, a checkout-only app and a release-only one; the suite wp
    (Windows); the wikis of both and the Nexus page."""
    root = tmp_path / "nexus"
    write(root / "tools/suites.py", (CHECKOUT / "tools/suites.py").read_text(encoding="utf-8"))
    (root / "dev").mkdir()
    bc = root / "bc"
    write(bc / "portal/VERSION", "3.0.0\n")
    write(bc / "portal/apps.toml", card("alpha") + card("beta", changes_board=True))
    for key in ("alpha", "beta"):
        write(bc / f"apps/{key}/VERSION", "0.1.0\n")
        write(bc / f"apps/{key}/{key}/__main__.py", "print('hi')\n")
    write(bc / "apps/alpha/alpha/__init__.py",
          'APP_NAME = "Alpha App"\nAPP_ID = "alpha-app"\nLOGO = ROOT / "images" / "alpha-logo.png"\n')
    for name in ("01-screenshot.png", "alpha-app.png", "alpha-logo.png"):
        write(bc / f"apps/alpha/images/{name}", "png")
    write(bc / "apps/alpha/tests/fake/__main__.py", "")                           # tests are never listed
    write(bc / "apps/standalone/VERSION", "0.1.0\n")
    write(bc / "apps/standalone/tool-dir/tool/__main__.py", "")
    write(bc / "apps/releases/VERSION", "0.1.0\n")
    write(bc / "apps/releases/.checkout-only", "No releases.\n")
    write(bc / "apps/releases/rel/__main__.py", "")
    wp = root / "wp"
    write(wp / "SYSTEM", "windows\n")
    write(wp / "TAG_PREFIX", "wp-\n")
    write(wp / "portal/VERSION", "0.1.0\n")
    write(wp / "portal/apps.toml", '[apps.test]\nname = "T"\nsummary = "s"\ntag = "wp-test-v0.1.0"\n')
    for folder, name in (("bc", "BC"), ("nexus", "Nexus"), ("wp", "WP")):
        write(root / folder / "mkdocs.yml", f"site_name: {name}\n")
    write(root / "bc/mkdocs.yml", "site_name: BC\nsite_url: https://example.invalid/bc/\n")
    return root


class FakeProcess:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def test_launch_targets(nexus):
    targets = {t.module: t for t in local.launch_targets(nexus, "bc")}
    assert sorted(targets) == ["alpha", "beta", "tool"]                        # not the checkout-only app, not tests
    alpha, beta, tool = targets["alpha"], targets["beta"], targets["tool"]
    assert (alpha.name, alpha.label, alpha.folder) == ("Alpha App", "Alpha App 0.1.0", nexus / "bc/apps/alpha")
    assert alpha.icon == nexus / "bc/apps/alpha/images/alpha-logo.png"        # the one its __init__ names
    assert beta.changes_board and not alpha.changes_board and beta.name == "beta" and beta.icon is None
    assert tool.key == "standalone" and tool.folder == nexus / "bc/apps/standalone/tool-dir"
    assert local.launch_targets(nexus, "wp") == []                            # no apps/ yet
    command, env = local.launch_command(nexus, alpha, python="/venv/python")
    assert command == ["/venv/python", "-m", "alpha"]
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(nexus / "core")


def test_changes_board_follows_the_manifest(nexus):
    assert local.changes_board(nexus, "bc") == {"alpha": False, "beta": True}
    assert local.changes_board(nexus, "wp") == {"test": False}                # no changes_board: False
    write(nexus / "bc/portal/apps.toml", "not [toml")
    assert local.changes_board(nexus, "bc") == {}


def test_portal_target(nexus):
    assert local.portal_target(nexus, "bc") is None                           # no portal window
    write(nexus / "bc/portal/bc250_portal/__main__.py", "print('portal')\n")
    write(nexus / "bc/portal/bc250_portal/__init__.py", 'APP_NAME = "Suite Portal"\nAPP_ID = "suite-portal"\n')
    write(nexus / "bc/portal/images/bc-suite.webp", "webp")                  # named after the suite's folder
    portal = local.portal_target(nexus, "bc")
    assert (portal.key, portal.module, portal.folder, portal.label, portal.app_id) == (
        "portal", "bc250_portal", nexus / "bc/portal", "Suite Portal 3.0.0", "suite-portal")
    assert portal.icon == nexus / "bc/portal/images/bc-suite.webp" and not portal.changes_board
    command, env = local.launch_command(nexus, portal, python="/venv/python")
    assert command == ["/venv/python", "-m", "bc250_portal"]                  # --source auto: from the checkout
    assert local.portal_target(nexus, "wp") is None


def test_this_checkouts_portals():
    assert local.portal_target(CHECKOUT, "bc250-bazzite").module == "bc250_portal"
    assert local.portal_target(CHECKOUT, "windows-portable").module == "portable_portal"


def test_docs_targets(nexus):
    docs = local.docs_targets(nexus, suite="bc")
    assert [t.label for t in docs] == ["BC wiki (local)", "Nexus wiki (local)"]   # never the other suite's
    bc, page = docs
    assert (bc.module, bc.folder) == ("mkdocs", nexus)
    assert bc.url == f"http://127.0.0.1:{local.DOCS_PORT}/bc/?design"         # site_url's path, the design panel
    command, _ = local.launch_command(nexus, bc, python="/venv/python")
    assert command == ["/venv/python", "-m", "mkdocs", "serve", "-f", "bc/mkdocs.yml",
                       "--dev-addr", f"127.0.0.1:{local.DOCS_PORT}"]
    assert page.url == f"http://127.0.0.1:{local.DOCS_PORT + 1}/?design" and bc.log_name != page.log_name
    assert not bc.note
    everything = {t.label: t.args[-1] for t in local.docs_targets(nexus)}
    assert list(everything) == ["BC wiki (local)", "Nexus wiki (local)", "WP wiki (local)"]
    shown = local.docs_targets(nexus, suite="wp")
    assert [t.label for t in shown] == ["Nexus wiki (local)", "WP wiki (local)"]
    assert all(everything[t.label] == t.args[-1] for t in shown)              # a wiki keeps its port


def test_docs_targets_on_the_network(nexus):
    bc = local.docs_targets(nexus, network=True, addresses=["192.0.2.7"], suite="bc")[0]
    port = local.NETWORK_PORT                                                 # not the local one: both can run
    assert bc.label == "BC wiki (network)" and bc.args[-1] == f"0.0.0.0:{port}"
    assert bc.url == f"http://127.0.0.1:{port}/bc/?design"                    # this computer's browser
    assert bc.note == f"On the other devices: http://192.0.2.7:{port}/bc/"
    assert bc.log_name != local.docs_targets(nexus, suite="bc")[0].log_name
    assert "no network address" in local.docs_targets(nexus, network=True, addresses=[], suite="bc")[0].note


def test_network_addresses_leave_out_loopback():
    assert all(not a.startswith("127.") for a in local.network_addresses())


def window_on(root: Path, suite: str = "bc", **kwargs) -> MainWindow:
    return MainWindow(root, settings=None, suite=suite, **kwargs)


def items(window: MainWindow) -> dict:
    return {window.local_apps.item(i).text(): window.local_apps.item(i) for i in range(window.local_apps.count())}


def test_the_portal_is_the_first_icon_then_the_apps_then_the_wikis(qapp, nexus):
    write(nexus / "bc/portal/bc250_portal/__main__.py", "print('portal')\n")
    write(nexus / "bc/portal/bc250_portal/__init__.py", '__version__ = "3.0.0"\n')
    window = window_on(nexus)
    labels = [window.local_apps.item(i).text() for i in range(window.local_apps.count())]
    assert labels == ["bc250_portal 3.0.0", "Alpha App 0.1.0", "beta 0.1.0", "tool 0.1.0", "BC wiki (local)",
                      "Nexus wiki (local)"]
    window.suite_box.setCurrentIndex(1)                                       # another suite: its own icons
    assert [window.local_apps.item(i).text() for i in range(window.local_apps.count())] == [
        "Nexus wiki (local)", "WP wiki (local)"]
    window.close()


def test_a_click_runs_an_app_from_the_checkout(qapp, nexus, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    monkeypatch.setattr(main_window, "LOCAL_LOG_DIR", tmp_path / "logs")
    started = []
    window = window_on(nexus, start_local=lambda command, env, cwd, log: started.append((command, cwd, log))
                       or FakeProcess())
    found = items(window)
    alpha, beta = found["Alpha App 0.1.0"], found["beta 0.1.0"]
    assert "Changes how the board runs" in beta.toolTip() and "Changes how the board runs" not in alpha.toolTip()
    assert "\n" not in beta.text()                                            # the warning is on the icon

    def corner(item) -> str:                                                  # the badge's orange, low right
        image = item.icon().pixmap(main_window.ICON_PX, main_window.ICON_PX).toImage()
        edge = main_window.ICON_PX - main_window.BADGE_PX // 2
        return QColor(image.pixel(edge - 6, edge)).name()

    assert corner(beta) == QColor(main_window.ORANGE).name() != corner(alpha)
    window.local_apps.itemClicked.emit(alpha)
    assert started == [([sys.executable, "-m", "alpha"], nexus / "bc/apps/alpha", tmp_path / "logs/alpha.log")]
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as asked:
        window.local_apps.itemClicked.emit(beta)                              # a board app asks first
    assert asked.called and len(started) == 1
    with mock.patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        window.local_apps.itemClicked.emit(beta)
    assert len(started) == 2 and window.timer.isActive()
    # alpha stops with an error: the end of its log shows; beta closes normally
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/alpha.log").write_text("Traceback (most recent call last):\nImportError: no module x\n")
    window.running[0][1].code, window.running[1][1].code = 1, 0
    window.poll()
    out = window.output.toPlainText()
    assert "Alpha App 0.1.0 stopped with exit code 1" in out and "ImportError: no module x" in out
    assert "beta 0.1.0 closed." in out and not window.running and not window.timer.isActive()

    def refuse(*args):
        raise OSError("no python")
    window.start_local = refuse
    window.local_apps.itemClicked.emit(alpha)
    assert "could not start (no python)" in window.output.toPlainText()
    window.close()


def test_an_open_portal_is_warned_about_and_not_started_again(qapp, nexus, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    write(nexus / "bc/portal/bc250_portal/__main__.py", "print('portal')\n")
    write(nexus / "bc/portal/bc250_portal/__init__.py", 'APP_NAME = "Suite Portal"\nAPP_ID = "suite-portal"\n')
    monkeypatch.setattr(main_window, "LOCAL_LOG_DIR", tmp_path / "logs")
    started, asked, seen = [], [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: asked.append(args[2]))
    monkeypatch.setattr(main_window, "instance_running", lambda app_id: seen.append(app_id) or True)
    window = window_on(nexus, start_local=lambda command, env, cwd, log: started.append(command) or FakeProcess())
    portal = window.local_apps.item(0)
    window.local_apps.itemClicked.emit(portal)
    assert seen == ["suite-portal"] and started == []                          # open: warned, not started
    assert len(asked) == 1 and "already open" in asked[0] and "Close Suite Portal first" in asked[0]
    monkeypatch.setattr(main_window, "instance_running", lambda app_id: False)
    window.local_apps.itemClicked.emit(portal)
    assert len(started) == 1 and len(asked) == 1
    window.close()


def test_a_wiki_is_served_and_opens_once_it_is_up(qapp, nexus, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window, "LOCAL_LOG_DIR", tmp_path / "logs")
    started, opened, up = [], [], [False]
    monkeypatch.setattr(main_window, "answers", lambda url: up[0])
    monkeypatch.setattr(main_window, "open_url", opened.append)
    window = window_on(nexus, start_local=lambda command, env, cwd, log: started.append((command, cwd))
                       or FakeProcess())
    docs = items(window)["BC wiki (local)"]
    window.local_apps.itemClicked.emit(docs)
    assert started == [([sys.executable, "-m", "mkdocs", "serve", "-f", "bc/mkdocs.yml",
                         "--dev-addr", f"127.0.0.1:{local.DOCS_PORT}"], nexus)]
    window.poll()
    assert opened == []                                                       # not up yet
    up[0] = True
    window.poll()
    window.poll()
    assert opened == [f"http://127.0.0.1:{local.DOCS_PORT}/bc/?design"]       # once
    window.local_apps.itemClicked.emit(docs)                                  # already up: only the page again
    assert len(started) == 1 and len(opened) == 2
    window.close()


def test_the_wikis_on_the_network(qapp, nexus, tmp_path, monkeypatch):
    monkeypatch.setattr(main_window, "LOCAL_LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(local, "network_addresses", lambda: ["192.0.2.7"])
    monkeypatch.setattr(main_window, "answers", lambda url: False)
    started = []
    window = window_on(nexus, start_local=lambda command, env, cwd, log: started.append((command, log))
                       or FakeProcess())
    window.network_box.setChecked(True)                                       # the icons follow
    docs = items(window)["BC wiki (network)"]
    window.local_apps.itemClicked.emit(docs)
    assert started[0][0][-1] == f"0.0.0.0:{local.NETWORK_PORT}"
    assert started[0][1].name == "mkdocs-bc-network.log"
    assert f"http://192.0.2.7:{local.NETWORK_PORT}/bc/" in window.output.toPlainText()
    window.close()


def test_start_local_keeps_the_output_in_a_log(tmp_path):
    log = tmp_path / "logs" / "x.log"
    process = main_window.start_local([sys.executable, "-c", "print('hello'); raise SystemExit(3)"],
                                      dict(os.environ), tmp_path, log)
    assert process.wait(30) == 3
    assert main_window.log_tail(log) == "hello"


def test_instance_running_sees_a_listening_app_and_does_not_disturb_it(qapp):
    from PyQt6.QtNetwork import QLocalServer
    from bc250_core.instance import server_name
    name = server_name("nexus-dashboard-test-instance")
    QLocalServer.removeServer(name)
    assert not main_window.instance_running("nexus-dashboard-test-instance")
    server = QLocalServer()
    assert server.listen(name)
    try:
        assert main_window.instance_running("nexus-dashboard-test-instance")
    finally:
        server.close()
    assert not main_window.instance_running("nexus-dashboard-test-instance")


def test_this_checkouts_suite_has_its_apps_and_wikis(qapp):
    window = MainWindow(settings=None, suite="bc250-bazzite")
    labels = list(items(window))
    assert labels[0].startswith("BC250 Bazzite Suite ")                        # the portal first
    assert labels[-2:] == ["BC250 Bazzite Suite wiki (local)", "Nexus wiki (local)"]
    window.close()
