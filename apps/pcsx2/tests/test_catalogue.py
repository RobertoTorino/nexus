# SPDX-License-Identifier: GPL-3.0-or-later
"""PCSX2's catalog (catalogue.py): the titles read out of a GameIndex.yaml as PCSX2 writes it, the widescreen
patches looked up as PCSX2 does, and the files taken out of the AppImage."""

from __future__ import annotations

import io
import subprocess
import zipfile

import pytest

from pcsx2_manager import catalogue

GAME_INDEX = '''# ---------------------------------------------
# PCSX2 Game Database!
# ---------------------------------------------
ALCH-00003:
  name: "ショコラ ～maid cafe curio～ [限定版]"
  name-sort: "しょこら maid cafe curio [げんていばん]"
  name-en: "Chocolat Maid Cafe Curio [Limited Edition]"
  region: "NTSC-J"
SLPM-60104:
  name: "Zero - Shisei no Koe" # Fatal Frame - Rei - Irezumi no Sei
  region: "NTSC-J"
SLUS-21553:
  name: "Lumines Plus"
  region: "NTSC-U"
  compat: 5
SLUS-29999:
  name: "The \\"Quoted\\" Game"
SCUS-00000:
  region: "NTSC-U"
'''


def _zip(files: dict[str, str]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return out.getvalue()


def test_titles_from_the_game_index(tmp_path):
    (tmp_path / catalogue.GAME_INDEX).write_text(GAME_INDEX, encoding="utf-8")
    titles = catalogue.titles(tmp_path)
    assert titles == {"ALCH-00003": "Chocolat Maid Cafe Curio [Limited Edition]",       # the English name first
                      "SLPM-60104": "Zero - Shisei no Koe",                               # the comment left out
                      "SLUS-21553": "Lumines Plus",
                      "SLUS-29999": 'The "Quoted" Game'}
    assert catalogue.titles(tmp_path / "missing") == {}


def test_the_titles_are_read_again_when_the_file_changes(tmp_path):
    path = tmp_path / catalogue.GAME_INDEX
    path.write_text('SLUS-00001:\n  name: "One"\n')
    assert catalogue.titles(tmp_path) == {"SLUS-00001": "One"}
    path.write_text('SLUS-00001:\n  name: "One, renamed"\n')
    stamp = path.stat().st_mtime
    import os
    os.utime(path, (stamp + 10, stamp + 10))
    assert catalogue.titles(tmp_path) == {"SLUS-00001": "One, renamed"}


def test_widescreen_patches_are_looked_up_as_pcsx2_does(tmp_path):
    (tmp_path / catalogue.PATCHES).write_bytes(_zip({
        "SLUS-21002_88A808FA.pnach": "gametitle=Tiger Woods\n\n[Widescreen 16:9]\ngsaspectratio=16:9\n",
        "SLUS-21553_93262D20.pnach": "gametitle=Lumines Plus\n\n[No-Interlacing]\n",
        "6D980D22.pnach": "[Widescreen 16:9]\n",                                          # by its CRC alone
    }))
    assert catalogue.has_widescreen(tmp_path, "SLUS-21002", 0x88A808FA)
    assert not catalogue.has_widescreen(tmp_path, "SLUS-21553", 0x93262D20)              # a patch, not widescreen
    assert catalogue.has_widescreen(tmp_path, "SLES-00000", 0x6D980D22)
    assert not catalogue.has_widescreen(tmp_path, "SLUS-21002", 0)                       # no CRC, no lookup
    assert not catalogue.has_widescreen(tmp_path / "missing", "SLUS-21002", 0x88A808FA)


def test_the_files_are_taken_out_of_the_appimage(tmp_path):
    """--appimage-extract with each file's path inside, in a work folder beside the AppImage; the files land
    beside it and the work folder goes."""
    image = tmp_path / "2.8.2" / "pcsx2.AppImage"
    image.parent.mkdir()
    image.write_bytes(b"")
    calls = []

    def run(command, cwd, **kwargs):
        calls.append(command)
        inside = cwd / "squashfs-root" / command[-1]
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_text(command[-1])
        return subprocess.CompletedProcess(command, 0)
    catalogue.extract(image, run)
    assert calls == [[str(image), "--appimage-extract", "usr/bin/resources/GameIndex.yaml"],
                     [str(image), "--appimage-extract", "usr/bin/resources/patches.zip"]]
    assert sorted(p.name for p in image.parent.iterdir()) == ["GameIndex.yaml", "patches.zip", "pcsx2.AppImage"]
    assert not catalogue.missing(image.parent)


def test_a_failed_extraction_leaves_nothing_behind(tmp_path):
    image = tmp_path / "pcsx2.AppImage"
    image.write_bytes(b"")

    def run(command, cwd, **kwargs):
        raise subprocess.CalledProcessError(1, command)
    with pytest.raises(subprocess.CalledProcessError):
        catalogue.extract(image, run)
    assert [p.name for p in tmp_path.iterdir()] == ["pcsx2.AppImage"] and catalogue.missing(tmp_path)
