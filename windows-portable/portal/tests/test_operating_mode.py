# SPDX-License-Identifier: GPL-3.0-or-later
import re
import sys
from pathlib import Path

import pytest

from portable_portal import operating_mode as om


class FakeApi:
    def __init__(self, plan="", overlay=om.BALANCED, fails=()):
        self._plan, self._overlay, self.fails, self.calls = plan, overlay, fails, []

    def plan(self):
        return self._plan

    def overlay(self):
        return self._overlay

    def set_plan(self, plan):
        self.calls.append(("plan", plan))
        if "plan" in self.fails:
            return False
        self._plan = plan
        return True

    def set_overlay(self, overlay):
        self.calls.append(("overlay", overlay))
        if "overlay" in self.fails:
            return False
        self._overlay = overlay
        return True


class FakeHelper:
    """The helper as the window sees it: installed or not, the modes asked for, its result, the installs started."""

    def __init__(self, installed=True, answer=None, error="", install_error=""):
        self._installed, self.answer, self.error, self.install_error = installed, answer, error, install_error
        self.requests, self.installs, self.when = [], [], 0.0

    def installed(self):
        return self._installed

    def request(self, mode):
        self.requests.append(mode.letter)
        if not self.error and self.answer:
            self.when += 1
        return self.error

    def result(self):
        return self.when, (om.parse_result(self.answer) if self.answer else None)

    def install(self, remove=False):
        self.installs.append(remove)
        return self.install_error


def test_the_ally_x_is_told_by_its_product_name():
    assert om.is_ally_x(lambda: "ROG Xbox Ally X RC73XA_RC73XA")
    assert not om.is_ally_x(lambda: "ROG Xbox Ally RC73YA_RC73YA")     # the Ally without the X: not measured
    assert not om.is_ally_x(lambda: "")


def test_every_mode_is_a_plan_and_a_power_mode():
    # The owner's measurements on the Ally X (31-10-2026): Command Center switches both with its mode
    assert [mode.letter for mode in om.MODES] == ["S", "P", "T", "W"]
    assert om.BY_LETTER["S"].overlay == om.EFFICIENCY and om.BY_LETTER["P"].overlay == om.BALANCED
    assert om.BY_LETTER["T"].overlay == om.PERFORMANCE and om.BY_LETTER["W"].overlay is None
    assert om.BY_LETTER["W"].plan == "381b4222-f694-41f0-9685-ff5bb260df2e"   # Windows' own Balanced
    assert om.BY_LETTER["T"].battery == (25, 30, 36) and om.BY_LETTER["T"].charger[0] == 35
    assert om.BY_LETTER["W"].charger == om.BY_LETTER["P"].charger    # Windows mode on the charger: Performance's watts


def test_the_active_mode_is_read_from_the_plan_and_the_power_mode():
    turbo = om.BY_LETTER["T"]
    assert om.active(FakeApi(turbo.plan.upper(), turbo.overlay)) is turbo
    assert om.active(FakeApi(turbo.plan, om.BALANCED)) is None          # Turbo's plan with another power mode
    windows = om.BY_LETTER["W"]
    assert om.active(FakeApi(windows.plan, om.PERFORMANCE)) is windows  # Windows mode: any power mode
    assert om.active(FakeApi("11111111-1111-1111-1111-111111111111")) is None
    assert om.marker(FakeApi(turbo.plan, turbo.overlay)) == "T" and om.marker(FakeApi()) == ""


def test_a_mode_sets_its_plan_and_its_power_mode():
    api = FakeApi()
    assert om.apply(om.BY_LETTER["S"], api)
    assert api.calls == [("plan", om.BY_LETTER["S"].plan), ("overlay", om.EFFICIENCY)] and om.marker(api) == "S"
    api = FakeApi(overlay=om.PERFORMANCE)
    assert om.apply(om.BY_LETTER["W"], api)                             # the power mode stays the player's
    assert api.calls == [("plan", om.BY_LETTER["W"].plan)] and om.marker(api) == "W"
    api = FakeApi(fails=("plan",))
    assert not om.apply(om.BY_LETTER["T"], api) and api.calls == [("plan", om.BY_LETTER["T"].plan)]


def test_the_watts_as_a_row_shows_them():
    assert om.watts_text(om.BY_LETTER["T"].charger) == "35 / 44 / 55 W"
    assert om.BY_LETTER["W"].battery == (17, 21, 26)       # measured on battery (owner's Ally X, 31-10-2026)


def test_only_the_ally_x_gets_the_power_api():
    assert om.power_api(lambda: "ROG Xbox Ally RC73YA_RC73YA") is None


def test_a_guid_goes_both_ways():
    text = "64a64f24-65b9-4b56-befd-5ec1eaced9b3"
    assert om._GUID.of(text).text() == text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' power API (powrprof)")
def test_windows_power_api_reads_the_plan_and_the_power_mode():
    api = om.PowerApi()                                 # read only: nothing is set on this machine
    assert len(api.plan()) == 36 and len(api.overlay()) == 36
    assert om.marker(api) in ("", "S", "P", "T", "W")
    assert om.power_api(lambda: "Some other PC") is None


def test_the_helper_s_result_line():
    assert om.parse_result("T ok charger 35 / 44 / 55 W") == om.Outcome("T", True, "35 / 44 / 55 W")
    assert om.parse_result("W ok battery 17 / 21 / 26 W") == om.Outcome("W", True, "17 / 21 / 26 W")
    assert om.parse_result("S failed no ASUS WMI (AsusAtkWmi_WMNB)") == om.Outcome("S", False,
                                                                                   "no ASUS WMI (AsusAtkWmi_WMNB)")
    assert om.parse_result("") is None and om.parse_result("? not a mode: x") is None


def test_the_helper_is_asked_through_its_request_and_its_task(tmp_path):
    runs = []
    helper = om.Helper(tmp_path / "programs", tmp_path / "data", run=lambda argv: runs.append(argv) or 0)
    assert not helper.installed() and helper.result() == (0.0, None)
    (tmp_path / "programs").mkdir()
    (tmp_path / "programs" / "operating-mode.ps1").write_text("", encoding="utf-8")
    (tmp_path / "data").mkdir()
    helper.request_file.write_text("", encoding="ascii")
    assert helper.installed()
    assert helper.request(om.BY_LETTER["T"]) == ""
    assert helper.request_file.read_text(encoding="ascii") == "T"
    assert runs == [["schtasks.exe", "/Run", "/TN", r"\Windows Portable Suite\Operating Mode"]]
    helper.run = lambda argv: 1
    assert helper.request(om.BY_LETTER["S"]) == "the helper's task could not be started (schtasks: 1)"
    helper.result_file.write_bytes("\ufeffT ok charger 35 / 44 / 55 W".encode("utf-8"))   # PowerShell's UTF-8
    when, outcome = helper.result()
    assert when > 0 and outcome == om.Outcome("T", True, "35 / 44 / 55 W")


def test_the_helper_s_table_is_the_portal_s():
    """The helper (PowerShell, as SYSTEM) has its own table, never the portal's word for the watts: the same values."""
    text = (om.HELPER / "operating-mode.ps1").read_text(encoding="utf-8")
    guids = {name: guid for name, guid in re.findall(r"\$(Balanced|Efficiency|Performance) = '([0-9a-f-]+)'", text)}
    assert guids == {"Balanced": om.BALANCED, "Efficiency": om.EFFICIENCY, "Performance": om.PERFORMANCE}
    found = re.findall(r"(\w) = @\{ Name = '(\w+)'; Plan = '([0-9a-f-]+)'; Overlay = (\$\w+)\s+"
                       r"Charger = @\(([^)]*)\); Battery = @\(([^)]*)\) \}", text)
    overlays = {"$Balanced": om.BALANCED, "$Efficiency": om.EFFICIENCY, "$Performance": om.PERFORMANCE, "$null": None}

    def watts(text):
        return tuple(int(part) for part in text.split(","))
    assert [(letter, name, plan, overlays[overlay], watts(charger), watts(battery))
            for letter, name, plan, overlay, charger, battery in found] == \
        [(m.letter, m.name, m.plan, m.overlay, m.charger, m.battery) for m in om.MODES]
    assert "MODEL" and f"$Model = '{om.MODEL}'" in (om.HELPER / "install-helper.ps1").read_text(encoding="utf-8")
    assert f"'{om.TASK.rsplit(chr(92), 1)[1]}'" in (om.HELPER / "install-helper.ps1").read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell's parser")
def test_the_helper_s_scripts_parse():
    import subprocess
    for script in sorted(om.HELPER.glob("*.ps1")):
        check = ("$e = $null; [System.Management.Automation.Language.Parser]::ParseFile("
                 f"'{script}', [ref]$null, [ref]$e) | Out-Null; $e | ForEach-Object {{ $_.ToString() }}")
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", check], capture_output=True, text=True)
        assert out.returncode == 0 and out.stdout.strip() == "", (script.name, out.stdout)
        assert b"\r" not in script.read_bytes()
