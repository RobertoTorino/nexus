# SPDX-License-Identifier: GPL-3.0-or-later
"""The extraction comparison and the before/after delta of two of its reports, as modules and from Extract PKG."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from shadps4_manager import INFO, extract_dialog
from shadps4_manager.extract_dialog import ExtractDialog
from shadps4_manager.main_window import ShadSettings
from shadps4_manager.pkgxtractor import compare, compare_delta


def _tree(root: Path, files: dict[str, bytes]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return root


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    left = _tree(tmp_path / "left", {"a.bin": b"same", "b.bin": b"left-longer", "sce_sys/param.sfo": b"x",
                                     "only_left.txt": b"1", "c.bin": b"abcd"})
    right = _tree(tmp_path / "right", {"a.bin": b"same", "b.bin": b"right", "sce_sys/param.sfo": b"x",
                                       "only_right.txt": b"2", "c.bin": b"abce"})
    return left, right


def test_run_compare_counts_and_report(folders, tmp_path: Path) -> None:
    left, right = folders
    lines: list[str] = []
    report_path = tmp_path / "reports" / "compare_report_1.json"
    report = compare.run_compare(left, right, use_hash=True, json_out=report_path, log=lines.append)
    assert report["left_file_count"] == 5 and report["right_file_count"] == 5
    assert report["common_file_count"] == 4
    assert report["only_left"] == ["only_left.txt"]
    assert report["only_right"] == ["only_right.txt"]
    assert report["size_mismatch"] == ["b.bin"]
    assert report["hash_mismatch"] == ["c.bin"]        # same size, different content
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
    assert any("Hash mismatches:      1" in line for line in lines)


def test_run_compare_without_hash_ignores_content(folders) -> None:
    left, right = folders
    report = compare.run_compare(left, right, log=lambda _line: None)
    assert report["hash_mismatch"] == [] and report["size_mismatch"] == ["b.bin"]


def test_compare_main_rejects_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        compare.main([str(tmp_path / "nope"), str(tmp_path)])


def test_summarize_delta() -> None:
    before = {"size_mismatch_count": 2, "size_mismatch": ["a.bin", "b.bin"], "only_left_count": 0}
    after = {"size_mismatch_count": 1, "size_mismatch": ["b.bin"], "only_left_count": 1, "only_left": ["new.txt"]}
    text = compare_delta.summarize_delta(before, after)
    assert text.startswith("=== Compare Report Delta ===")
    assert "size_mismatch_count: before=2, after=1, delta=-1 (DOWN)" in text
    assert "only_left_count: before=0, after=1, delta=+1 (UP)" in text
    assert "hash_mismatch_count: before=0, after=0, delta=+0 (UNCHANGED)" in text
    assert "[size_mismatch] fixed=1, new=0" in text and "    - a.bin" in text
    assert "[only_left] fixed=0, new=1" in text and "    - new.txt" in text


def test_compare_delta_main_writes_out(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({"only_left": ["x"], "only_left_count": 1}), encoding="utf-8")
    after.write_text(json.dumps({"only_left": [], "only_left_count": 0}), encoding="utf-8")
    out = tmp_path / "out" / "delta.txt"
    assert compare_delta.main([str(before), str(after), "--out", str(out)]) == 0
    assert "[only_left] fixed=1, new=0" in out.read_text(encoding="utf-8")
    assert "Delta written to" in capsys.readouterr().out


def test_window_compare_report_delta(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_dialog, "app_data_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"unexpected warning: {a[1:3]}"))
    before = tmp_path / "compare_report_1.json"
    after = tmp_path / "compare_report_2.json"
    before.write_text(json.dumps({"hash_mismatch_count": 3, "hash_mismatch": ["a", "b", "c"]}), encoding="utf-8")
    after.write_text(json.dumps({"hash_mismatch_count": 1, "hash_mismatch": ["c"]}), encoding="utf-8")
    answers = iter([(str(before), ""), (str(after), "")])
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: next(answers))

    window = ExtractDialog(ShadSettings(INFO), [])
    window.show()
    window.on_compare_report_delta()
    log = window.log_output.toPlainText()
    assert "hash_mismatch_count: before=3, after=1, delta=-2 (DOWN)" in log
    assert "[hash_mismatch] fixed=2, new=0" in log
    delta_file = tmp_path / "compare_report_2_delta.txt"
    assert delta_file.is_file()
    assert f"Delta written to: {delta_file}" in log
    assert window.compare_btn.menu() is not None and len(window.compare_btn.menu().actions()) == 2
    window.close()


def test_window_compare_report_delta_cancel(qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extract_dialog, "app_data_dir", lambda: tmp_path / "state")
    (tmp_path / "state").mkdir()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    window = ExtractDialog(ShadSettings(INFO), [])
    window.on_compare_report_delta()
    assert "Before:" not in window.log_output.toPlainText()
    window.close()
