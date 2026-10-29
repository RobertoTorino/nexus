# SPDX-License-Identifier: GPL-3.0-or-later
"""Browsing with the controller (browse.py): the places, a folder's folders and files of the asked kinds by name, the
hidden ones left out, A into a folder or on a file, B up to the places and out."""

from __future__ import annotations

from pathlib import Path

from bc250_core import browse
from bc250_core.platform import private


def tree(tmp_path: Path) -> Path:
    home = tmp_path / "me"
    for folder in ("Games/PSP/Zeta", "Games/PSP/alpha", "Games/.cache", "Downloads", "Music"):
        (home / folder).mkdir(parents=True)
    (home / "Downloads" / "SCPH-70012.BIN").write_bytes(b"x")
    (home / "Downloads" / "notes.txt").write_text("x")
    return home


def test_the_places_are_the_usual_folders_then_the_drives(tmp_path):
    home = tree(tmp_path)
    card = tmp_path / "E"
    card.mkdir()
    assert browse.places(home, lambda: [card]) == [home / "Games", home / "Downloads", card]


def test_a_folder_lists_its_folders_by_name_without_the_hidden(tmp_path):
    home = tree(tmp_path)
    b = browse.Browser([home / "Games"])
    b.open(f"dir:{home / 'Games'}")
    b.open(f"dir:{home / 'Games' / 'PSP'}")
    assert b.rows() == [("up", f"‹ {private(home / 'Games')}"), (f"dir:{home / 'Games/PSP/alpha'}", "alpha"),
                        (f"dir:{home / 'Games/PSP/Zeta'}", "Zeta")]
    b.open("up")
    assert b.path == home / "Games" and [k for k, _ in b.rows()] == ["up", f"dir:{home / 'Games/PSP'}"]
    assert b.rows()[0] == ("up", "‹ The places")                    # a place: up goes to the places
    assert b.up() and b.path is None and not b.up()                      # at the places: the page leaves


def test_files_of_the_asked_kinds_are_picked(tmp_path):
    home = tree(tmp_path)
    b = browse.Browser([home / "Downloads"], suffixes=(".bin", ".rom"), path=home / "Downloads")
    assert [text for _, text in b.rows()] == ["‹ The places", "SCPH-70012.BIN"]
    assert b.open(f"file:{home / 'Downloads' / 'SCPH-70012.BIN'}") == home / "Downloads" / "SCPH-70012.BIN"


def test_a_folder_that_cannot_be_read_is_empty(tmp_path):
    assert browse.listing(tmp_path / "gone") == ([], [])
    assert browse.Browser([], path=tmp_path / "gone").rows()[1:] == []


def test_the_drives_are_there():
    assert browse.drives() and all(d.exists() for d in browse.drives())


def test_an_empty_card_slot_is_no_drive(monkeypatch):
    """A card reader or an SD slot without a card keeps its drive letter, and Windows raises when asked about it
    (WinError 1005 on this PC's E: and F:); it is left out of the drives rather than ending the app."""
    import sys

    class EmptySlot:
        def is_dir(self):
            raise OSError(22, "The volume does not contain a recognized file system.")
    assert not browse.mounted(EmptySlot()) and browse.mounted(Path.home())
    if sys.platform != "win32":
        assert browse.drives(lambda root: False) == [Path("/")]
        return
    assert browse.drives(lambda root: root == Path("C:\\")) == [Path("C:\\")]
    assert browse.drives(lambda root: False) == []
