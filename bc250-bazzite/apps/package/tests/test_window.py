# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QLabel

from package_checker import CATALOG
from package_checker.bazzite import BazziteState, Deployment
from package_checker.dependencies import (
    CheckResult, DependencyStatus, EnvironmentVersion, ToolStatus, Vulnerability, load_apps, load_catalog,
    load_tools,
)
from package_checker.main_window import DependencyWindow, about_text, tool_advice

SHARED = "/home/test/.local/share/bc250-bazzite-suite/venv"
DEMO = "/home/test/.local/share/media-tool/venv"


def _wait_for(predicate, ms=3000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(10)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


def _window(result: CheckResult, bazzite=None) -> DependencyWindow:
    """The window on *result*; Bazzite's state from *bazzite*, else none (the board's own is never read here)."""
    window = DependencyWindow(load_catalog(CATALOG), load_tools(CATALOG), load_apps(CATALOG), check=lambda: result,
                              bazzite=bazzite or (lambda: BazziteState(error="Not read in a test.")))
    assert _wait_for(lambda: window.check_button.isEnabled())
    return window


def _catalog():
    return ({d.name: d for d in load_catalog(CATALOG)}, {t.name: t for t in load_tools(CATALOG)})


def test_window_displays_package_and_tool_results(qapp):
    dependencies, tools = _catalog()
    result = CheckResult(
        [DependencyStatus(dependencies["PyQt6"], (EnvironmentVersion(SHARED, ("portal", "check"), "6.11.0"),
                                                  EnvironmentVersion(DEMO, ("mtool",), "6.11.0")), "6.12.0"),
         DependencyStatus(dependencies["obsws-python"], (EnvironmentVersion(DEMO, ("mtool",), "1.8.0"),),
                          "1.8.0"),
         DependencyStatus(dependencies["dbus-next"], (), "0.2.3")],
        [ToolStatus(tools["flashrom"], "/home/test/flashrom/usr/bin/flashrom"),
         ToolStatus(tools["speedtest"], "/home/test/.local/bin/speedtest"),
         ToolStatus(tools["mprime"]),
         ToolStatus(tools["setpci"])],
        frozenset({"portal", "check", "mtool", "bios", "cores"}),
    )
    window = _window(result)
    try:
        pyqt = window.cards["PyQt6"]
        assert pyqt.status.text() == "Update available"
        assert pyqt.latest.text() == "Latest on PyPI: 6.12.0"
        assert "BC-250 Bazzite Test" in pyqt.installed.text() and "Media Tool" in pyqt.installed.text()
        assert window.cards["obsws-python"].status.text() == "Up to date"
        assert window.cards["dbus-next"].status.text() == "Not needed"
        assert window.tool_cards["flashrom"].status.text() == "Available"
        assert window.tool_cards["flashrom"].location.text().endswith("/flashrom")
        assert window.tool_cards["speedtest"].status.text() == "Available"
        assert window.tool_cards["mprime"].status.text() == "Not installed"
        assert window.tool_cards["setpci"].status.text() == "Missing"
        text = window.result_label.text()
        assert "Missing, needed by an installed app:</b> setpci" in text
        assert "Optional, not installed: mprime" in text
        assert window.box_missing.value.text() == "1"
        assert window.box_updates.value.text() == "1"
    finally:
        window.close()


def test_missing_package_in_an_app_environment_is_reported(qapp):
    dependencies, _tools = _catalog()
    result = CheckResult(
        [DependencyStatus(dependencies["dbus-next"], (EnvironmentVersion(DEMO, ("mtool",), ""),), "0.2.3")],
        [], frozenset({"mtool"}))
    window = _window(result)
    try:
        assert window.cards["dbus-next"].status.text() == "Missing"
        assert "missing" in window.cards["dbus-next"].installed.text()
        assert "Packages missing or at a wrong version:</b> dbus-next" in window.result_label.text()
    finally:
        window.close()


def test_tools_that_need_root_say_so(qapp):
    _dependencies, tools = _catalog()
    window = _window(CheckResult([], [], frozenset()))
    try:
        def says_root(name):
            return any("Needs root." in label.text() for label in window.tool_cards[name].findChildren(QLabel))
        assert says_root("umr") and says_root("setpci")
        assert not says_root("pkexec") and not says_root("stress-ng")
        assert window.tool_cards["umr"].status.text() == "Not checked"
    finally:
        window.close()


def test_about_popup_describes_the_purpose(qapp):
    _dependencies, tools = _catalog()
    apps = load_apps(CATALOG)
    text = about_text(tools["cec-ctl"], apps)
    assert "HDMI-CEC" in text and "HDMI CEC Manager" in text and "(required)" in text
    assert "Needs root." in about_text(tools["umr"], apps)
    window = _window(CheckResult([], [], frozenset()))
    try:
        card = window.cards["obsws-python"]
        card.about_button.click()
        assert card.about_box is not None and card.about_box.isVisible()
        assert "OBS" in card.about_box.text() and "Media Tool" in card.about_box.text()
        card.about_box.close()
    finally:
        window.close()


def test_cve_marks(qapp):
    dependencies, _tools = _catalog()
    cve = Vulnerability("CVE-2099-1234", "Leaks a header", "6.12.1",
                        "https://security.snyk.io/vuln/?search=CVE-2099-1234")
    result = CheckResult(
        [DependencyStatus(dependencies["PyQt6"], (EnvironmentVersion(SHARED, ("portal",), "6.11.0", (), (cve,)),),
                          "6.12.1"),
         DependencyStatus(dependencies["obsws-python"], (EnvironmentVersion(DEMO, ("mtool",), "1.8.0"),), "1.8.0"),
         DependencyStatus(dependencies["dbus-next"], (EnvironmentVersion(DEMO, ("mtool",), "0.2.3"),), "0.2.3",
                          cve_error="offline")],
        [], frozenset({"portal", "mtool"}))
    window = _window(result)
    try:
        pyqt = window.cards["PyQt6"]
        assert "✗ CVE" in pyqt.cve.text() and pyqt.status.text() == "Needs update"     # a release fixes it
        assert "href='https://security.snyk.io/vuln/?search=CVE-2099-1234'>CVE-2099-1234</a> in 6.11.0" in \
            pyqt.vulnerabilities.text()
        assert "fixed in 6.12.1" in pyqt.vulnerabilities.text()
        assert "Update PyQt6 6.11.0 to 6.12.1 or newer for Portal" in pyqt.advice.text()
        assert "✓ CVE" in window.cards["obsws-python"].cve.text()
        assert window.cards["obsws-python"].advice.isHidden()
        assert "CVE ?" in window.cards["dbus-next"].cve.text()
        assert window.box_cves.value.text() == "1"
        assert "Known vulnerabilities:</b> PyQt6 6.11.0 (CVE-2099-1234)" in window.result_label.text()
        assert "Vulnerability check failed: dbus-next" in window.result_label.text()
    finally:
        window.close()


def test_missing_tools_advise_what_they_are_needed_for(qapp):
    dependencies, tools = _catalog()
    installed = frozenset({"bios", "cores", "check"})
    advice = tool_advice(tools["stress-ng"], installed, load_apps(CATALOG))
    assert advice.startswith("<b>Advice:</b> Install stress-ng to be able to use:")
    assert "BC-250 Cores Bisect</a>: Verified CPU load during core testing. <b>(required)</b>" in advice
    assert "BC-250 Bazzite Test</a>: CPU stress/load tests and CPU benchmark.</li>" in advice
    assert "Install speedtest or speedtest-cli" in tool_advice(tools["speedtest"], installed, load_apps(CATALOG))
    assert "Install a flashrom that has it" in tool_advice(tools["flashrom"], installed, load_apps(CATALOG),
                                                           "No internal programmer found.")
    assert tool_advice(tools["radeontop"], installed, load_apps(CATALOG)) == ""   # the governor is not installed
    window = _window(CheckResult(
        [DependencyStatus(dependencies["dbus-next"], (EnvironmentVersion(DEMO, ("mtool",), ""),), "0.2.3")],
        [ToolStatus(tools["mprime"]), ToolStatus(tools["umr"], "/usr/bin/umr")], installed | {"mtool"}))
    try:
        assert "Install mprime to be able to use <a href=" in window.tool_cards["mprime"].advice.text()
        assert "Prime95 torture test for a longer burn-in." in window.tool_cards["mprime"].advice.text()
        assert window.tool_cards["umr"].advice.isHidden()
        assert "Install Media Tool again from the portal to be able to use it" in \
            window.cards["dbus-next"].advice.text()
    finally:
        window.close()


def test_needs_update_when_an_app_wants_newer_or_a_release_fixes_a_vulnerability(qapp):
    dependencies, _tools = _catalog()
    link = "/home/test/.local/share/bc250-console-link/venv"
    sftp = "/home/test/.local/share/bc250-sftp-tools/venv"
    fixed = Vulnerability("CVE-2026-1", "a hole", "3.4.1")
    unfixed = Vulnerability("CVE-2026-2", "another hole")
    result = CheckResult(
        [DependencyStatus(dependencies["cryptography"],
                          (EnvironmentVersion(link, ("consoles",), "41.0.0", ("consoles",), (),
                                              ("consoles",)),), "46.0.0"),
         DependencyStatus(dependencies["paramiko"], (EnvironmentVersion(sftp, ("sftp",), "3.4.0", (),
                                                                        (fixed,)),), "3.5.0"),
         DependencyStatus(dependencies["obsws-python"], (EnvironmentVersion(DEMO, ("mtool",), "1.8.0", (),
                                                                            (unfixed,)),), "1.8.0"),
         DependencyStatus(dependencies["PyQt6"], (EnvironmentVersion(DEMO, ("mtool",), "7.0.0",
                                                                     ("mtool",)),), "7.0.0")],
        [], frozenset({"consoles", "sftp", "mtool"}))
    window = _window(result)
    try:
        crypto, paramiko = window.cards["cryptography"], window.cards["paramiko"]
        assert crypto.status.text() == "Needs update"
        assert "Console Link needs >=42,<51, installed is 41.0.0." in crypto.status.toolTip()
        assert paramiko.status.text() == "Needs update"
        assert "3.4.1 fixes known vulnerabilities in 3.4.0." in paramiko.status.toolTip()
        assert window.cards["obsws-python"].status.text() == "Vulnerable"     # no release fixes it yet
        assert window.cards["PyQt6"].status.text() == "Wrong version"          # too new: no update helps
        assert window.box_needs_update.value.text() == "2"
        text = window.result_label.text()
        assert "Needs update:</b> cryptography, paramiko" in text
        assert "wrong version:</b> PyQt6." in text                              # cryptography is under Needs update
    finally:
        window.close()


def test_the_bazzite_card_on_top(qapp):
    """An update waiting for a reboot: the card says so first, in the system section above the packages."""
    running = Deployment("44.20261012.1", 1791962757, booted=True, staged=False)
    waiting = Deployment("44.20261019.0", 1792567557, booted=False, staged=True)
    window = _window(CheckResult(packages=[], tools=[], installed=frozenset()),
                     bazzite=lambda: BazziteState(running, waiting, "ghcr.io/ublue-os/bazzite:stable"))
    assert _wait_for(lambda: "waits for a reboot" in window.bazzite_card.text.text())
    assert window.bazzite_card.status.text() == "Reboot to update"
    assert "Bazzite 44.20261019.0" in window.bazzite_card.text.text()
    window.close()


def test_the_bazzite_card_without_bazzite(qapp):
    window = _window(CheckResult(packages=[], tools=[], installed=frozenset()))
    assert _wait_for(lambda: window.bazzite_card.status.text() == "Not known")
    assert window.bazzite_card.text.text() == "Not read in a test."
    window.close()
