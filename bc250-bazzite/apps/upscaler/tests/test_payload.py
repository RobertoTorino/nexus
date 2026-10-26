# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from upscaler import backend
from tests.conftest import make_release


def test_status_of_empty_folder(tmp_path):
    status = backend.payload_status(tmp_path / "payload")
    assert not status.ready and status.missing() == list(backend.ESSENTIAL_FILES)
    assert status.version == ""


def test_import_folder(release, tmp_path):
    dest = tmp_path / "payload"
    result = backend.import_payload(release, dest)
    assert set(result.copied) >= {backend.HELIXSR_DLL, backend.WEIGHTS, backend.KERNELS, backend.INI, "README.md"}
    assert result.missing == []
    assert not (dest / "helixsr-setup.sh").exists()     # only known files are taken
    status = backend.payload_status(dest)
    assert status.ready and status.version == "1.2.0"


def test_import_nested_folder(release, tmp_path):
    outer = tmp_path / "Downloads"
    outer.mkdir()
    release.rename(outer / "extracted")
    assert backend.import_payload(outer, tmp_path / "payload").missing == []


def test_import_zip(release, tmp_path):
    archive = tmp_path / "HelixSR-v1.2.0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for file in release.iterdir():
            zf.write(file, f"HelixSR-v1.2.0/{file.name}")
    result = backend.import_payload(archive, tmp_path / "payload")
    assert backend.HELIXSR_DLL in result.copied and result.missing == []
    assert (tmp_path / "payload" / backend.WEIGHTS).read_bytes() == b"weights"


def test_import_without_network_files_reports_missing(tmp_path):
    src = make_release(tmp_path / "src", network=False)
    result = backend.import_payload(src, tmp_path / "payload")
    assert set(result.missing) == set(backend.NETWORK_FILES)
    assert not backend.payload_status(tmp_path / "payload").ready


def test_import_refuses_folder_without_dll(tmp_path):
    (tmp_path / "junk").mkdir()
    (tmp_path / "junk" / "readme.txt").write_text("x")
    with pytest.raises(backend.HelixError):
        backend.import_payload(tmp_path / "junk", tmp_path / "payload")
    with pytest.raises(backend.HelixError):
        backend.import_payload(tmp_path / "missing", tmp_path / "payload")
    (tmp_path / "notzip.zip").write_bytes(b"nope")
    with pytest.raises(backend.HelixError):
        backend.import_payload(tmp_path / "notzip.zip", tmp_path / "payload")
