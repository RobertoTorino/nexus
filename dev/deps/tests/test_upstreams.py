# SPDX-License-Identifier: GPL-3.0-or-later
"""catalogs/upstreams.json in sync with the apps, and the cards of the emulators and of Sony's firmware from GitHub's
and Sony's answers (as they were on 09-11-2026)."""

from __future__ import annotations

import json
from pathlib import Path

from nexus_deps import upstreams
from nexus_deps.upstreams import CATALOG

INFO = json.dumps({"ApplicationLatestVersion": "2.2.1.2", "FwUpdate0004LatestVersion": "0x0630",
                   "FwUpdate000BLatestVersion": "0x0630", "FwUpdate000ELatestVersion": "0x0641",
                   "FwUpdate0044LatestVersion": "0x0217"}).encode()
PS4 = (b'<?xml version="1.0" ?>\n<update_data_list>\n\t<region id="us">\n\t\t<system_pup ex_version="0" '
       b'label="14.02" sdk_version="14.020.001" version="14.020.000">\n\t\t</system_pup>\n\t</region>\n'
       b'</update_data_list>\n')


def catalog():
    return upstreams.load()


def entry(key, data=None):
    data = data or catalog()
    return next(item for item in [*data["github"], *data["sony"]] if item["id"] == key)


def test_the_catalog_is_in_sync_with_the_apps():
    """The pins, repos, names and launchers are the apps' own: dev/deps/run.sh --sync-upstreams fixes this."""
    assert upstreams.dump(upstreams.sync(catalog())) == CATALOG.read_text(encoding="utf-8")


def test_every_app_with_a_pinned_upstream_is_listed():
    listed = {(app["suite"], app["app"]) for item in catalog()["github"] for app in item["apps"]}
    assert listed == upstreams.apps_with_upstreams()
    assert ("bc250-bazzite", "rpcs3") in listed and ("bazzite-console", "decky") in listed


def test_the_constants_are_read_without_running_the_module(tmp_path):
    module = tmp_path / "emulator.py"
    module.write_text('LANDMARK = "0.0.43"\nBUILD = 20395\nVERSION = f"{LANDMARK}-{BUILD}"\nNUMBER = str(BUILD)\n'
                      'COMMIT = "46b7fb67"\nASSET = f"x{COMMIT[:4]}"\nraise SystemExit("never run")\n')
    values = upstreams.constants(module)
    assert values["VERSION"] == "0.0.43-20395" and values["NUMBER"] == "20395" and "ASSET" not in values


def test_a_moved_pin_makes_the_catalog_stale(tmp_path):
    data = catalog()
    entry("pcsx2", data)["apps"][0]["pin"] = "2.8.1"
    assert upstreams.sync(data) != data
    assert entry("pcsx2", upstreams.sync(data))["apps"][0]["pin"] == entry("pcsx2")["apps"][0]["pin"]


def release(tag, published="2026-11-09T10:00:00Z"):
    return lambda url: {"tag_name": tag, "published_at": published, "html_url": f"https://github.com/x/{tag}"}


def install(home: Path, app: dict, version: str | None):
    """The app's launcher, and its program at *version* (None: the app without its program)."""
    launcher = home / app["launcher"].removeprefix("~/")
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text("")
    if version is None:
        return
    if "home" in app:
        folder = home / app["home"].removeprefix("~/")
        (folder / version).mkdir(parents=True)
        (folder / "current").symlink_to(version)
    else:
        path = home / app["version_file"].removeprefix("~/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"v{version}\n")


def test_an_emulator_at_its_pin_with_nothing_newer(tmp_path):
    rpcs3 = entry("rpcs3")
    app = rpcs3["apps"][0]
    install(tmp_path, app, app["version"])
    source = upstreams.check_github(rpcs3, release(f"v{app['pin']}"), tmp_path)
    assert source.updates == () and not source.manual and source.group == "apps"
    assert source.detail.startswith(f"Latest on GitHub: v{app['pin']}")


def test_installed_behind_the_pin_and_upstream_past_it(tmp_path):
    vita = entry("vita3k")
    app = vita["apps"][0]
    install(tmp_path, app, "4200")
    source = upstreams.check_github(vita, release(str(int(app["pin"]) + 14)), tmp_path)
    assert [update.name for update in source.updates] == ["Vita3K Manager (BC250 Bazzite Suite): installed",
                                                          "Vita3K on GitHub"]
    assert source.manual and source.step is None                        # never by a click
    assert "use its Install" in source.note and "comes with a release of the app" in source.note
    assert "release work" in source.about


def test_an_app_without_its_program_is_no_update(tmp_path):
    xenia = entry("xenia")
    install(tmp_path, xenia["apps"][0], None)
    source = upstreams.check_github(xenia, release("838850f", "2026-11-04T16:38:00Z"), tmp_path)
    assert source.updates == () and "Installed without Xenia Canary so far: Xenia Manager." in source.detail
    later = upstreams.check_github(xenia, release("cf206a3", "2026-11-09T09:00:00Z"), tmp_path)
    assert later.updates[0].latest == "cf206a3"


def test_decky_past_its_pin_updated_itself(tmp_path):
    decky = entry("decky")
    install(tmp_path, decky["apps"][0], "9.9.9")
    source = upstreams.check_github(decky, release("v9.9.9"), tmp_path)
    assert [update.name for update in source.updates] == ["Decky Loader on GitHub"]
    assert "update itself" in source.about


def test_github_offline(tmp_path):
    def offline(url):
        raise OSError("no network")
    source = upstreams.check_github(entry("pcsx2"), offline, tmp_path)
    assert source.error == "GitHub could not be asked: no network" and source.about


def test_the_comparisons():
    assert upstreams.newer("version", {"tag_name": "v.0.22.0"}, "0.21.0")
    assert not upstreams.newer("version", {"tag_name": "v1.20"}, "1.20.0")
    assert upstreams.newer("build", {"tag_name": "4283"}, "4269") and not upstreams.newer("build", {"tag_name": "x"}, "1")
    assert upstreams.newer("published", {"published_at": "2026-11-09T09:00:00Z"}, "2026-11-04T16:38:00Z")


def test_sonys_firmware_is_news_once(tmp_path):
    """The first look learns the versions; a later one names what changed; the one after says nothing again."""
    state = tmp_path / "state.json"
    catalog_ = {"github": [], "sony": [entry("dualsense"), entry("ps4")]}
    first = upstreams.read("seen", catalog_, get=lambda url: INFO if url.endswith(".json") else PS4, state=state)
    assert all(source.updates == () for source in first)
    assert first[0].detail.startswith("Latest: DualSense (0x0004) 0x0630") and first[1].detail == "Latest: PS4 14.02."
    newer_info = INFO.replace(b'"0x0217"', b'"0x0218"')
    second = upstreams.read("seen", catalog_, get=lambda url: newer_info if url.endswith(".json") else PS4,
                            state=state)
    assert [(u.name, u.current, u.latest) for u in second[0].updates] == [("DualSense Edge (0x0044)", "0x0217",
                                                                          "0x0218")]
    assert "USB cable" in second[0].note and second[0].manual
    third = upstreams.read("seen", catalog_, get=lambda url: newer_info if url.endswith(".json") else PS4,
                           state=state)
    assert third[0].updates == ()
    # The reminder keeps its own memory: the window's look does not use up its news
    assert upstreams.read("notified", catalog_, get=lambda url: newer_info if url.endswith(".json") else PS4,
                          state=state)[0].updates == ()                    # its first look


def test_the_ps4_list_is_read_by_its_one_attribute():
    assert upstreams.parse_ps4(PS4) == {"PS4": "14.02"}
    for bad in (b"<x/>", b'<system_pup label="14.02; rm -rf"/>', b"<!DOCTYPE x [<!ENTITY a 'b'>]><x>&a;</x>"):
        try:
            upstreams.parse_ps4(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_devices_with_no_list_say_where_to_look():
    for key in ("ps5", "psportal"):
        source = upstreams.check_sony(entry(key), None, get=lambda url: (_ for _ in ()).throw(AssertionError(url)))
        assert not source.checked and "System Software" in source.about and source.updates == ()


def test_the_reminder_names_an_upstream_once(tmp_path):
    from nexus_deps.system import Source, Update
    state = tmp_path / "state.json"
    late = Source("upstream-xenia", "Xenia Canary", (Update("Xenia Canary on GitHub", "838850f", "cf206a3"),),
                  note="newer", group="apps")
    machine = Source("brew", "Homebrew", (Update("node", "1.0", "1.1"),))
    assert upstreams.unnotified((late, machine), state)[0].updates == late.updates
    again = upstreams.unnotified((late, machine), state)
    assert again[0].updates == () and again[0].note == "" and again[1] is machine     # the machine's: every time
