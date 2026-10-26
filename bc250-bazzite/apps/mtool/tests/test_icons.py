# SPDX-License-Identifier: GPL-3.0-or-later
import subprocess
import sys
from pathlib import Path

from media_tool import icons

SUITE = Path(__file__).resolve().parents[3]


def _checkout(root: Path) -> Path:
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "sync_icons.py").write_text("", encoding="utf-8")
    (root / "icons" / "leaf").mkdir(parents=True)
    (root / "icons" / "gear").mkdir()
    (root / "icons" / "categories.toml").write_text("", encoding="utf-8")
    return root


def test_checkout_is_found_from_a_folder_inside_it(tmp_path):
    root = _checkout(tmp_path / "suite")
    (root / "apps" / "mtool").mkdir(parents=True)

    assert icons.find_checkout(None, tmp_path, root / "apps" / "mtool") == root
    assert icons.find_checkout(tmp_path) is None
    assert icons.categories(root) == ["gear", "leaf"]


def test_the_tool_finds_its_own_checkout():
    assert icons.find_checkout(Path(icons.__file__).parent) == SUITE


def test_whole_set_runs_first_then_each_size_in_order(tmp_path):
    root = _checkout(tmp_path)
    tool = [sys.executable, str(root / "tools" / "sync_icons.py"), "--category", "leaf"]

    assert icons.convert_commands(root, "leaf", Path("/a.png"), {128: Path("/s.png"), 512: Path("/m.png")}) == [
        tool + ["--from", "/a.png"],
        tool + ["--from", "/m.png", "--size", "512"],
        tool + ["--from", "/s.png", "--size", "128"],
    ]
    assert icons.convert_commands(root, "leaf", None, {}) == []


def test_icon_names_match_the_suite_tool():
    sys.path.insert(0, str(SUITE / "tools"))
    try:
        import sync_icons
    finally:
        sys.path.remove(str(SUITE / "tools"))
    assert icons.SIZES == sync_icons.SIZES
    for size in icons.SIZES:
        assert icons.icon_path(SUITE, "leaf", size) == sync_icons.icon_path(SUITE / "icons" / "leaf", size)


def test_dialog_runs_the_conversions_and_shows_their_output(qapp, tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    runs = []

    def run(command, **kwargs):
        runs.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="converted: leaf-512\n", stderr="")

    monkeypatch.setattr(icons.subprocess, "run", run)
    dialog = icons.IconsDialog(root)
    assert dialog.checkout_path.text() == str(root)
    assert not dialog.convert_button.isEnabled()
    dialog.category.setCurrentText("leaf")
    dialog.sizes[512].setText("/new.png")
    assert dialog.convert_button.isEnabled()

    assert dialog.convert()

    assert runs == [icons.convert_commands(root, "leaf", None, {512: Path("/new.png")})[0]]
    assert "converted: leaf-512" in dialog.output.toPlainText()
    assert dialog.sizes[512].text() == ""
    dialog.close()


def test_dialog_stops_at_the_first_failure(qapp, tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    runs = []

    def run(command, **kwargs):
        runs.append(command)
        return subprocess.CompletedProcess(command, 1, stdout="",
                                           stderr="/a.png: 512 x 256 px, an icon must be square\n")

    monkeypatch.setattr(icons.subprocess, "run", run)
    dialog = icons.IconsDialog(root)
    dialog.whole.setText("/a.png")
    dialog.sizes[128].setText("/b.png")

    assert not dialog.convert()

    assert len(runs) == 1
    assert "must be square" in dialog.output.toPlainText()
    assert "stopped with status 1" in dialog.output.toPlainText()
    assert dialog.whole.text() == "/a.png"
    dialog.close()


def test_dialog_without_a_checkout_asks_for_one(qapp):
    dialog = icons.IconsDialog(None)
    assert dialog.category.count() == 0
    assert not dialog.convert_button.isEnabled()
    assert "Choose the folder of a suite checkout" in dialog.output.toPlainText()
    dialog.close()


def test_dialog_converts_real_images_in_a_copy_of_the_icons(qapp, tmp_path):
    """The whole way, with the suite's own tool on a copy of its icons and the apps' copies."""
    import shutil

    root = tmp_path / "suite"
    shutil.copytree(SUITE / "icons", root / "icons")
    (root / "tools").mkdir()
    shutil.copy(SUITE / "tools" / "sync_icons.py", root / "tools")
    for copy in [p for p in (SUITE / "apps").glob("*/images/*") if p.suffix in (".png", ".webp")] + \
            list((SUITE / "portal" / "images" / "apps").glob("*.webp")):
        target = root / copy.relative_to(SUITE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(copy, target)
    from PIL import Image
    Image.new("RGBA", (300, 300), "blue").save(tmp_path / "blue.png")
    dialog = icons.IconsDialog(root)
    dialog.category.setCurrentText("gaming")
    dialog.sizes[256].setText(str(tmp_path / "blue.png"))

    assert dialog.convert(), dialog.output.toPlainText()

    with Image.open(root / "icons" / "gaming" / "gaming-256.webp") as image:
        assert image.size == (256, 256) and image.format == "WEBP"
    assert (root / "portal" / "images" / "apps" / "rpcs3.webp").read_bytes() == \
        (root / "icons" / "gaming" / "gaming-256.webp").read_bytes()
    assert (root / "icons" / "gaming" / "gaming-512.webp").read_bytes() == \
        (SUITE / "icons" / "gaming" / "gaming-512.webp").read_bytes()
    dialog.close()
