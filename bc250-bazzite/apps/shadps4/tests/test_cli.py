# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end tests against a synthetic, properly encrypted PKG."""

from __future__ import annotations

from pathlib import Path

import pytest

from shadps4_manager.pkgxtractor import cli
from shadps4_manager.pkgxtractor.pkg import PFS_DIR, PFS_FILE, PKG, is_pkg_file
from shadps4_manager.pkgxtractor.psf import PSF

from pkg_builder import build_pkg, default_tree


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    folder = tmp_path_factory.mktemp("pkg")
    return build_pkg(folder / "synthetic.pkg", default_tree())


def test_open_reads_header_and_sfo(built) -> None:
    assert is_pkg_file(built.path)
    with PKG() as pkg:
        pkg.open(built.path)
        assert pkg.content_id == built.content_id
        assert pkg.title_id == built.title_id
        assert pkg.sfo == built.sce_sys_plain["param.sfo"]
        psf = PSF.from_bytes(pkg.sfo)
        assert psf.get_string("TITLE") == "Synthetic Test Title"
        assert psf.get_string("APP_VER") == "01.00"
        assert psf.get_integer("ATTRIBUTE") == 0
        assert pkg.get_entry_data_by_id(0x1200) == built.sce_sys_plain["icon0.png"]


def test_full_extraction(built, tmp_path: Path) -> None:
    out = tmp_path / "out"
    with PKG() as pkg:
        pkg.extract(built.path, out)
        assert pkg.warnings == []

        # sce_sys entries, with the NP data decrypted in place.
        assert (out / "sce_sys" / "param.sfo").read_bytes() == built.sce_sys_plain["param.sfo"]
        assert (out / "sce_sys" / "icon0.png").read_bytes() == built.sce_sys_plain["icon0.png"]
        assert (out / "sce_sys" / "license.dat").read_bytes() == built.sce_sys_plain["license.dat"]
        assert (out / "sce_sys" / "entry_keys").stat().st_size == 2048

        names = {(entry.name, entry.type) for entry in pkg.fs_table}
        assert ("data", PFS_DIR) in names
        assert ("eboot.bin", PFS_FILE) in names
        assert ("big.bin", PFS_FILE) in names
        assert ("bad:name?.txt", PFS_FILE) in names

        for index in range(pkg.num_files):
            ok, reason = pkg.can_extract_file(index)
            assert ok, reason
            pkg.extract_files(index)

        assert pkg.export_file_list(out / "filelist.txt")
        listing = (out / "filelist.txt").read_text(encoding="utf-8")
        assert 'Name: "eboot.bin"' in listing

    for rel, content in built.expected_files.items():
        rel = rel.replace("bad:name?.txt", "bad_name_.txt")
        actual = out / rel
        assert actual.is_file(), rel
        assert actual.read_bytes() == content, rel
    assert (out / "data").is_dir()
    assert not (out / "bad:name?.txt").exists()


def test_cli_extracts_into_title_id_folder(built, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    rc = cli.main([str(built.path), str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "Extraction complete!" in out
    target = tmp_path / built.title_id
    assert (target / "eboot.bin").read_bytes() == built.expected_files["eboot.bin"]
    assert (target / "data" / "zeros.dat").read_bytes() == built.expected_files["data/zeros.dat"]
    assert (target / "filelist.txt").exists()


def test_version_is_the_apps(capsys: pytest.CaptureFixture) -> None:
    import shadps4_manager
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--version"])
    assert capsys.readouterr().out.strip() == f"bc250-shadps4-pkg-cli {shadps4_manager.__version__}"


def test_cli_rejects_non_pkg(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    bogus = tmp_path / "bogus.pkg"
    bogus.write_bytes(b"nope" * 100)
    assert cli.main([str(bogus)]) == 1
    assert "is not a valid PKG file" in capsys.readouterr().out
