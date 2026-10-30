# SPDX-License-Identifier: GPL-3.0-or-later
"""The Xbox app's library (xbox.py), on a file in a temp folder shaped as the Xbox app 2611.1001.9.0 wrote it on the
owner's Ally (30-10-2026): an app added once, never twice, the file backed up, one in another shape left alone, and
the Xbox app closed while it changes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bc250_core import xbox

PROGRAM = Path(r"C:\Users\me\AppData\Local\windows-portable-suite\portal\app\Windows-Portable-Suite.exe")
OTHER = {"id": "{3ae38f80-4800-4348-b96b-85e785521ae0}", "lastPlayedDate": "1793377938817",
         "addedDate": "1793375492967", "imagePath": "C:\\x\\Images\\3055008164425239568.png", "title": "Other Game",
         "installLocation": "C:\\Games\\Other\\", "executableName": "Other.exe", "executableCommandArgs": ""}


def ran(change):
    change()


def test_an_app_is_added_once_beside_the_others(tmp_path):
    path = xbox.manifest_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "provider": {"version": 1, "enabled": True},
                                "gameCache": {"version": 1, OTHER["id"]: OTHER}}), encoding="utf-8")
    before = path.read_bytes()
    assert not xbox.listed(PROGRAM, tmp_path)
    assert xbox.add(PROGRAM, "Windows Portable Suite", local=tmp_path, closed=ran, now=1793400000.0)
    data = json.loads(path.read_text(encoding="utf-8"))
    added = [e for k, e in data["gameCache"].items() if k != "version" and e["title"] == "Windows Portable Suite"]
    assert len(added) == 1 and data["gameCache"][OTHER["id"]] == OTHER and data["provider"]["enabled"] is True
    new = added[0]
    assert new["installLocation"] == "C:\\Users\\me\\AppData\\Local\\windows-portable-suite\\portal\\app\\"
    assert new["executableName"] == "Windows-Portable-Suite.exe"
    assert new["addedDate"] == "1793400000000" and new["id"].startswith("{") and new["id"] in data["gameCache"]
    assert path.with_name(path.name + ".bak").read_bytes() == before        # backed up first
    assert xbox.listed(PROGRAM, tmp_path)
    assert xbox.listed(Path(str(PROGRAM).upper()), tmp_path)                 # Windows' names, any case
    assert not xbox.add(PROGRAM, "Windows Portable Suite", local=tmp_path, closed=ran)    # never twice
    assert len(json.loads(path.read_text(encoding="utf-8"))["gameCache"]) == 3


def test_an_app_is_removed_and_the_others_kept(tmp_path):
    """The portal's Xbox menu row takes the suite out again (owner, 30-10-2026): only its entry goes, the file backed
    up, the Xbox app closed while it changes; not there, nothing is written."""
    path = xbox.manifest_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "provider": {"version": 1, "enabled": True},
                                "gameCache": {"version": 1, OTHER["id"]: OTHER}}), encoding="utf-8")
    assert xbox.add(PROGRAM, "Windows Portable Suite", local=tmp_path, closed=ran)
    before = path.read_bytes()
    changes = []
    assert xbox.remove(Path(str(PROGRAM).lower()), local=tmp_path, closed=lambda c: changes.append(c) or c())
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["gameCache"] == {"version": 1, OTHER["id"]: OTHER} and len(changes) == 1
    assert path.with_name(path.name + ".bak").read_bytes() == before and not xbox.listed(PROGRAM, tmp_path)
    assert not xbox.remove(PROGRAM, local=tmp_path, closed=changes.append) and len(changes) == 1   # not there


def test_the_first_app_makes_the_file(tmp_path):
    """No file yet (nothing added by hand), or an empty one: the shape the Xbox app writes."""
    assert xbox.add(PROGRAM, "Windows Portable Suite", local=tmp_path, closed=ran)
    data = json.loads(xbox.manifest_path(tmp_path).read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["gameCache"]["version"] == 1 and len(data["gameCache"]) == 2
    empty = tmp_path / "other"
    xbox.manifest_path(empty).parent.mkdir(parents=True)
    xbox.manifest_path(empty).write_text("", encoding="utf-8")
    assert xbox.add(PROGRAM, "Windows Portable Suite", local=empty, closed=ran) and xbox.listed(PROGRAM, empty)


@pytest.mark.parametrize("text", ['{"customApps": []}', "not json", '{"gameCache": {"x": {"title": "y"}}}'])
def test_a_file_in_another_shape_is_never_written(tmp_path, text):
    path = xbox.manifest_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    closed = []
    with pytest.raises(xbox.FormatError):
        xbox.add(PROGRAM, "Windows Portable Suite", local=tmp_path, closed=closed.append)
    assert path.read_text(encoding="utf-8") == text and closed == [] and not xbox.listed(PROGRAM, tmp_path)


def test_the_xbox_app_is_closed_while_the_file_changes_and_started_again():
    events = []
    running = [[11, 12], [11], []]
    xbox.with_xbox_closed(lambda: events.append("change"), running=lambda: running.pop(0) if running else [],
                          end=lambda pid: events.append(f"end {pid}"), start=lambda: events.append("start"),
                          sleep=lambda s: None)
    assert events == ["end 11", "end 12", "change", "start"]
    events.clear()
    xbox.with_xbox_closed(lambda: events.append("change"), running=lambda: [], end=events.append,
                          start=lambda: events.append("start"), sleep=lambda s: None)
    assert events == ["change"]                                             # not running: not started either


def test_without_the_xbox_app(tmp_path):
    assert not xbox.installed(tmp_path)
    (tmp_path / "Packages" / xbox.PACKAGE).mkdir(parents=True)
    assert xbox.installed(tmp_path)
