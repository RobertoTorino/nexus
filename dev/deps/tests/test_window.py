# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QLabel

from nexus_deps import CATALOG
from nexus_deps.bazzite import BazziteState, Deployment
from nexus_deps.dependencies import (
    CheckResult, DependencyStatus, EnvironmentVersion, ToolStatus, Vulnerability, load_apps, load_catalog,
    load_tools,
)
from nexus_deps.fixes import Plan, Step
from nexus_deps.main_window import DependencyWindow, FixDialog, about_text, confirm_text, tool_advice

SHARED = "/home/test/.local/share/bc250-bazzite-suite/venv"
SFTP = "/home/test/.local/share/bc250-bazzite-sftp-tools/venv"   # an app with a venv of its own


def _wait_for(predicate, ms=3000):
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: predicate() and loop.quit())
    timer.start(10)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    timer.stop()
    return predicate()


def _window(result: CheckResult, bazzite=None, system=(), **kwargs) -> DependencyWindow:
    """The window on *result*; Bazzite's state from *bazzite*, else none, and the machine's updates from *system* (the
    board's own are never read here). Fix's question is answered No unless a test passes its own *ask*."""
    kwargs.setdefault("ask", lambda text: False)
    window = DependencyWindow(load_catalog(CATALOG), load_tools(CATALOG), load_apps(CATALOG), check=lambda: result,
                              bazzite=bazzite or (lambda: BazziteState(error="Not read in a test.")),
                              system=lambda: tuple(system), **kwargs)
    assert _wait_for(lambda: window.check_button.isEnabled())
    return window


def _catalog():
    return ({d.name: d for d in load_catalog(CATALOG)}, {t.name: t for t in load_tools(CATALOG)})


def test_window_displays_package_and_tool_results(qapp):
    dependencies, tools = _catalog()
    result = CheckResult(
        [DependencyStatus(dependencies["PyQt6"], (EnvironmentVersion(SHARED, ("portal", "check"), "6.11.0"),
                                                  EnvironmentVersion(SFTP, ("sftp",), "6.11.0")), "6.12.0"),
         DependencyStatus(dependencies["paramiko"], (EnvironmentVersion(SFTP, ("sftp",), "5.1.0"),),
                          "5.1.0"),
         DependencyStatus(dependencies["pygame-ce"], (), "2.5.8")],
        [ToolStatus(tools["flashrom"], "/home/test/flashrom/usr/bin/flashrom"),
         ToolStatus(tools["speedtest"], "/home/test/.local/bin/speedtest"),
         ToolStatus(tools["mprime"]),
         ToolStatus(tools["setpci"])],
        frozenset({"portal", "check", "sftp", "bios", "cores"}),
    )
    window = _window(result)
    try:
        pyqt = window.cards["PyQt6"]
        assert pyqt.status.text() == "Update available"
        assert pyqt.latest.text() == "Latest on PyPI: 6.12.0"
        assert "BC-250 Bazzite Test" in pyqt.installed.text() and "Bazzite SFTP Tools" in pyqt.installed.text()
        assert window.cards["paramiko"].status.text() == "Up to date"
        assert window.cards["pygame-ce"].status.text() == "Not needed"
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
        [DependencyStatus(dependencies["pygame-ce"], (EnvironmentVersion(SFTP, ("sftp",), ""),), "2.5.8")],
        [], frozenset({"sftp"}))
    window = _window(result)
    try:
        assert window.cards["pygame-ce"].status.text() == "Missing"
        assert "missing" in window.cards["pygame-ce"].installed.text()
        assert "Packages missing or at a wrong version:</b> pygame-ce" in window.result_label.text()
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
        card = window.cards["paramiko"]
        card.about_button.click()
        assert card.about_box is not None and card.about_box.isVisible()
        assert "SSH" in card.about_box.text() and "Bazzite SFTP Tools" in card.about_box.text()
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
         DependencyStatus(dependencies["paramiko"], (EnvironmentVersion(SFTP, ("sftp",), "5.1.0"),), "5.1.0"),
         DependencyStatus(dependencies["pygame-ce"], (EnvironmentVersion(SFTP, ("sftp",), "2.5.8"),), "2.5.8",
                          cve_error="offline")],
        [], frozenset({"portal", "sftp"}))
    window = _window(result)
    try:
        pyqt = window.cards["PyQt6"]
        assert "✗ CVE" in pyqt.cve.text() and pyqt.status.text() == "Needs update"     # a release fixes it
        assert "href='https://security.snyk.io/vuln/?search=CVE-2099-1234'>CVE-2099-1234</a> in 6.11.0" in \
            pyqt.vulnerabilities.text()
        assert "fixed in 6.12.1" in pyqt.vulnerabilities.text()
        assert "Update PyQt6 6.11.0 to 6.12.1 or newer for Portal" in pyqt.advice.text()
        assert "✓ CVE" in window.cards["paramiko"].cve.text()
        assert window.cards["paramiko"].advice.isHidden()
        assert "CVE ?" in window.cards["pygame-ce"].cve.text()
        assert window.box_cves.value.text() == "1"
        assert "Known vulnerabilities:</b> PyQt6 6.11.0 (CVE-2099-1234)" in window.result_label.text()
        assert "Vulnerability check failed: pygame-ce" in window.result_label.text()
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
        [DependencyStatus(dependencies["pygame-ce"], (EnvironmentVersion(SFTP, ("sftp",), ""),), "2.5.8")],
        [ToolStatus(tools["mprime"]), ToolStatus(tools["umr"], "/usr/bin/umr")], installed | {"sftp"}))
    try:
        assert "Install mprime to be able to use <a href=" in window.tool_cards["mprime"].advice.text()
        assert "Prime95 torture test for a longer burn-in." in window.tool_cards["mprime"].advice.text()
        assert window.tool_cards["umr"].advice.isHidden()
        assert f"Fix installs pygame-ce in {SFTP}, which Bazzite SFTP Tools needs" in \
            window.cards["pygame-ce"].advice.text()
    finally:
        window.close()


def test_needs_update_when_an_app_wants_newer_or_a_release_fixes_a_vulnerability(qapp):
    dependencies, _tools = _catalog()
    link = "/home/test/.local/share/bc250-console-link/venv"
    sftp = "/home/test/.local/share/bc250-sftp-tools/venv"
    CLB = "/home/test/.local/share/bc250-console-linkb/venv"
    fixed = Vulnerability("CVE-2026-1", "a hole", "3.4.1")
    unfixed = Vulnerability("CVE-2026-2", "another hole")
    result = CheckResult(
        [DependencyStatus(dependencies["cryptography"],
                          (EnvironmentVersion(link, ("consoles",), "41.0.0", ("consoles",), (),
                                              ("consoles",)),), "46.0.0"),
         DependencyStatus(dependencies["paramiko"], (EnvironmentVersion(sftp, ("sftp",), "3.4.0", (),
                                                                        (fixed,)),), "3.5.0"),
         DependencyStatus(dependencies["aiortc"], (EnvironmentVersion(CLB, ("clb",), "1.14.0", (),
                                                                       (unfixed,)),), "1.14.0"),
         DependencyStatus(dependencies["PyQt6"], (EnvironmentVersion(SFTP, ("sftp",), "7.0.0",
                                                                     ("sftp",)),), "7.0.0")],
        [], frozenset({"consoles", "sftp", "clb"}))
    window = _window(result)
    try:
        crypto, paramiko = window.cards["cryptography"], window.cards["paramiko"]
        assert crypto.status.text() == "Needs update"
        assert "Console Link needs >=42,<51, installed is 41.0.0." in crypto.status.toolTip()
        assert paramiko.status.text() == "Needs update"
        assert "3.4.1 fixes known vulnerabilities in 3.4.0." in paramiko.status.toolTip()
        assert window.cards["aiortc"].status.text() == "Vulnerable"       # no release fixes it yet
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


def _broken() -> CheckResult:
    dependencies, tools = _catalog()
    return CheckResult(
        [DependencyStatus(dependencies["pygame-ce"], (EnvironmentVersion(SFTP, ("sftp",), ""),))],
        [ToolStatus(tools["setpci"])], frozenset({"sftp", "cores"}))


def test_fix_is_off_until_there_is_something_to_fix(qapp):
    dependencies, _tools = _catalog()
    fine = CheckResult([DependencyStatus(dependencies["PyQt6"], (EnvironmentVersion(SHARED, ("portal",), "6.11.0"),),
                                         latest="6.11.0")], [], frozenset({"portal"}))
    window = _window(fine)
    try:
        assert not window.fix_button.isEnabled() and window.fix_button.toolTip() == "Nothing to fix."
    finally:
        window.close()
    window = _window(_broken())
    try:
        assert window.fix_button.isEnabled() and "pygame-ce into" in window.fix_button.toolTip()
        assert window.plan.steps[0].command[0] == f"{SFTP}/bin/python"
    finally:
        window.close()


def test_fix_asks_with_every_command_and_no_changes_nothing(qapp):
    asked: list[str] = []
    window = _window(_broken(), ask=lambda text: asked.append(text) or False)
    try:
        window.fix()
        assert len(asked) == 1 and "pip install" in asked[0] and "Run them now?" in asked[0]
        assert window.fix_dialog is None and window.fix_button.isEnabled()
    finally:
        window.close()


def test_fix_offered_at_once_with_fix(qapp):
    """--fix: the notification's Fix… button asks as soon as the check is done, once."""
    asked: list[str] = []
    window = _window(_broken(), ask=lambda text: asked.append(text) or False, offer_fix=True)
    try:
        assert len(asked) == 1 and not window.offer_fix
        window.check_updates()
        assert _wait_for(lambda: window.check_button.isEnabled()) and len(asked) == 1
    finally:
        window.close()


def test_the_question_names_a_restart_and_what_fix_leaves(qapp):
    steps = (Step("pip", "a into v", ("v/bin/python", "-m", "pip", "install", "a")),
             Step("rpm-ostree", "setpci into the Bazzite image", ("rpm-ostree", "install", "pciutils"), restart=True))
    text = confirm_text(Plan(steps, ("Steam",)))
    assert "rpm-ostree install pciutils" in text and "systemctl reboot" in text and "never does by itself" in text
    assert "Not by Fix: Steam" in text
    assert "restart" not in confirm_text(Plan(steps[:1])).lower()


def test_the_fix_dialog_runs_the_steps_and_stops_at_a_failure(qapp):
    ok = Step("pip", "first", ("sh", "-c", "echo one"))
    bad = Step("brew", "second", ("sh", "-c", "echo two; exit 3"))
    never = Step("brew", "third", ("sh", "-c", "echo three"))
    dialog = FixDialog(Plan((ok, bad, never)))
    dialog.start()
    assert _wait_for(lambda: dialog.buttons.isEnabled())
    assert dialog.done == [ok] and dialog.failed == bad
    assert "one" in dialog.output and "two" in dialog.output and "three" not in dialog.output
    assert "second failed" in dialog.status.text()
    dialog.close()
    layered = Step("rpm-ostree", "layered", ("sh", "-c", "true"), restart=True)
    dialog = FixDialog(Plan((layered,)))
    dialog.start()
    assert _wait_for(lambda: dialog.buttons.isEnabled())
    assert "Done." in dialog.status.text() and "systemctl reboot" in dialog.status.text()
    dialog.close()


def _sources():
    from nexus_deps.system import Source, Update
    brew = Source("brew", "Homebrew", tuple(Update(f"formula{n}", "1.0", "1.1") for n in range(14)),
                  step=Step("brew", "14 Homebrew update(s)", ("sh", "-c", "true")))
    venv = Source("venv", "Python venv (.venv-linux)", (Update("paramiko", "", "5.1.0"),),
                  (Update("mkdocs", "1.6.1", "2.0.1"),), step=Step("pip", "1 package(s)", ("sh", "-c", "true")),
                  note="The venv was made with Python 3.14 and runs Python 3.15 now.")
    return (Source("flatpak", "Flatpak"), brew, Source("rust", "Rust", error="offline"), venv)


def test_the_machines_updates_have_a_card_each(qapp):
    """Every update system wide is shown (09-11-2026: the hourly notice named updates the window did not)."""
    window = _window(CheckResult([], [], frozenset()), system=_sources())
    try:
        cards = window.system_cards
        assert list(cards) == ["flatpak", "brew", "rust", "venv"] and not window.system_waiting.isVisible()
        assert cards["flatpak"].status.text() == "Up to date" and cards["flatpak"].update_button.isHidden()
        brew = cards["brew"]
        assert brew.status.text() == "14 updates" and not brew.update_button.isHidden()
        assert "formula0 1.0 → 1.1" in brew.text.text() and "And 2 more: formula12, formula13." in brew.text.text()
        assert cards["rust"].status.text() == "Check failed" and cards["rust"].update_button.isHidden()
        venv = cards["venv"]
        assert "paramiko 5.1.0 (missing)" in venv.text.text()
        assert venv.held.text() == "Held back by requirements-dev.txt: mkdocs 1.6.1 → 2.0.1 (major)."
        assert "Python 3.15" in venv.note.text()
        assert window.box_system.value.text() == "15" and "Homebrew (14)" in window.box_system.toolTip()
        # Fix takes the machine's updates too; it is on with nothing else to fix
        assert window.fix_button.isEnabled() and [step.kind for step in window.plan.steps] == ["brew", "pip"]
    finally:
        window.close()


def test_a_cards_update_asks_for_its_own_step_alone(qapp):
    asked: list[str] = []
    window = _window(CheckResult([], [], frozenset()), system=_sources(), ask=lambda text: asked.append(text) or False)
    try:
        window.system_cards["brew"].update_button.click()
        assert len(asked) == 1 and "14 Homebrew update(s)" in asked[0] and "1 package(s)" not in asked[0]
        assert window.fix_dialog is None
    finally:
        window.close()


def test_fix_offered_for_the_machines_updates_alone(qapp):
    """--fix from a notification about Homebrew alone: the question comes once both checks are done."""
    asked: list[str] = []
    window = _window(CheckResult([], [], frozenset()), system=_sources(), offer_fix=True,
                     ask=lambda text: asked.append(text) or False)
    try:
        assert len(asked) == 1 and "14 Homebrew update(s)" in asked[0]
    finally:
        window.close()


def test_an_image_of_a_new_fedora_release_is_by_hand(qapp):
    """A system-wide change has no Update: the card says why, and its i gives the steps."""
    from nexus_deps.system import Source, Update
    image = Source("image", "Bazzite image", (Update("Bazzite", "44.20261012.1", "45.20261105.0"),),
                   note="Bazzite 45.20261105.0 moves from Fedora 44 to Fedora 45.", about="<ol><li>ujust update</li></ol>")
    window = _window(CheckResult([], [], frozenset()), system=(image,))
    try:
        card = window.system_cards["image"]
        assert card.status.text() == "By hand" and card.update_button.isHidden()
        assert "(major)" in card.text.text() and "Fedora 44 to Fedora 45" in card.note.text()
        assert not card.info.isHidden() and "ujust update" in card.info.text_
        assert not window.fix_button.isEnabled()                    # nothing Fix may run
    finally:
        window.close()


def test_the_emulators_and_firmware_have_a_section_of_their_own(qapp):
    from nexus_deps.system import Source, Update
    vita = Source("upstream-vita3k", "Vita3K", (Update("Vita3K on GitHub", "4269", "4283"),), group="apps",
                  note="it comes with a release of the app", about="<p>release work</p>")
    pads = Source("upstream-dualsense", "DualSense firmware", group="apps", detail="Latest: DualSense Edge 0x0217.",
                  known=(("DualSense Edge (0x0044)", "0x0217"),), about="<p>USB cable</p>")
    portal = Source("upstream-psportal", "PlayStation Portal", group="apps", checked=False, detail="On the device.",
                    about="<p>Settings</p>")
    window = _window(CheckResult([], [], frozenset()), system=(Source("flatpak", "Flatpak"), vita, pads, portal))
    try:
        assert not window.apps_heading.isHidden()
        assert window.apps_layout.indexOf(window.system_cards["upstream-vita3k"]) == 0
        assert window.system_layout.indexOf(window.system_cards["flatpak"]) >= 0
        card = window.system_cards["upstream-vita3k"]
        assert card.status.text() == "By hand" and card.update_button.isHidden()
        assert window.system_cards["upstream-dualsense"].status.text() == "Nothing new"
        assert window.system_cards["upstream-psportal"].status.text() == "On the device"
        assert not window.fix_button.isEnabled()                    # nothing here is installed by a click
    finally:
        window.close()
