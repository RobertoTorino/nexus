# SPDX-License-Identifier: GPL-3.0-or-later
"""The build steps (the pinned fetch from the mirror with upstream as the fallback, the newest sources, the make
line) and the output layout, without git or a compiler."""

from __future__ import annotations

from pathlib import Path

from conftest import KERNEL, fake_source, write

from usb_wifidriver import builder


def layout(tmp_path, branch="legacy-mcu1", newest=False) -> builder.Layout:
    return builder.Layout(tmp_path / "data", branch, KERNEL, newest)


def argvs(steps) -> list[list[str]]:
    return [s.argv for s in steps]


def test_pins_name_both_branches_of_the_fork():
    assert builder.BRANCHES == ("main", "legacy-mcu1")
    for pin in builder.PINS.values():
        assert len(pin.commit) == 40 and pin.date.count("-") == 2 and pin.chips
    assert builder.MIRROR == "https://github.com/RobertoTorino/aic8800d80"
    assert builder.UPSTREAM == "https://github.com/shenmintao/aic8800d80"


def test_fetch_steps_take_the_pinned_commit_from_the_mirror_with_upstream_as_fallback(tmp_path):
    lay = layout(tmp_path)
    src = str(lay.source)
    steps = builder.fetch_steps(lay)
    pin = builder.PINS["legacy-mcu1"].commit
    assert argvs(steps) == [["git", "init", "-q", src],
                            ["git", "-C", src, "remote", "add", "mirror", builder.MIRROR],
                            ["git", "-C", src, "remote", "add", "upstream", builder.UPSTREAM],
                            ["git", "-C", src, "fetch", "-q", "--depth", "1", "mirror", pin],
                            ["git", "-C", src, "checkout", "-q", "--force", "FETCH_HEAD"]]
    fetch = steps[3]
    assert fetch.fallback == ["git", "-C", src, "fetch", "-q", "--depth", "1", "upstream", pin]
    assert "did not answer" in fetch.note and builder.UPSTREAM in fetch.note
    assert all(s.fallback is None for s in steps if s is not fetch)
    # A folder that already is a repository is fetched into, not initialized again.
    (lay.source / ".git").mkdir(parents=True)
    again = builder.fetch_steps(lay)
    assert len(again) == 2 and again[0].argv[1:4] == ["-C", src, "fetch"]


def test_fetch_is_skipped_when_the_pinned_commit_is_there(tmp_path):
    lay = layout(tmp_path)
    fake_source(lay.source)
    assert builder.checked_out(lay) == ""
    builder.mark_checked_out(lay)
    assert builder.checked_out(lay) == builder.PINS["legacy-mcu1"].commit
    assert builder.fetch_steps(lay) == []
    # Another branch's pin, or the newest sources, in the same folder is not good enough.
    write(lay.commit_file, builder.PINS["main"].commit)
    assert builder.fetch_steps(lay) != []
    write(lay.commit_file, builder.NEWEST)
    assert builder.fetch_steps(lay) != []


def test_newest_sources_fetch_the_branch_head_every_time(tmp_path):
    lay = layout(tmp_path, newest=True)
    src = str(lay.source)
    fake_source(lay.source)
    (lay.source / ".git").mkdir()
    builder.mark_checked_out(lay)
    assert builder.checked_out(lay) == builder.NEWEST
    steps = builder.fetch_steps(lay)
    assert argvs(steps) == [["git", "-C", src, "fetch", "-q", "--depth", "1", "mirror", "legacy-mcu1"],
                            ["git", "-C", src, "checkout", "-q", "--force", "FETCH_HEAD"]]
    assert steps[0].fallback[-2:] == ["upstream", "legacy-mcu1"]
    assert lay.output == tmp_path / "data/build/legacy-mcu1-newest" / KERNEL
    # The commit comes from what git checked out.
    assert builder.source_commit(lay) == ""
    write(lay.source / ".git/HEAD", "a" * 40)
    assert builder.source_commit(lay) == "a" * 40
    write(lay.source / ".git/HEAD", "ref: refs/heads/main")
    assert builder.head_commit(lay) == ""
    assert builder.source_commit(layout(tmp_path)) == builder.PINS["legacy-mcu1"].commit


def test_make_uses_the_kernels_build_tree(tmp_path):
    lay = layout(tmp_path, "main")
    tree = Path("/usr/lib/modules") / KERNEL / "build"
    step = builder.make_step(lay, tree, jobs=4)
    assert step.argv == ["make", "-C", str(tree), f"M={lay.source}/drivers/aic8800", "-j4", "modules"]
    assert step.fallback is None
    assert builder.make_step(lay, tree).argv[4].startswith("-j")


def test_collect_lays_the_output_out_for_the_loader(tmp_path):
    lay = layout(tmp_path)
    fake_source(lay.source)
    assert "aic_load_fw.ko, aic8800_fdrv.ko" in builder.collect(lay)
    for module in builder.built_modules(lay):
        write(module, "ELF")
    assert builder.collect(lay) == ""
    assert (lay.output / "aic_load_fw.ko").is_file() and (lay.output / "aic8800_fdrv.ko").is_file()
    fw = lay.output / "fw"
    assert (fw / "fmacfw_8800d80_u02.bin").is_file() and (fw / "aic_userconfig_8800d80.txt").is_file()
    # The self link: the Wi-Fi module appends /aic8800D80 to the folder, once per probe.
    assert (fw / "aic8800D80").is_symlink() and (fw / "aic8800D80/aic8800D80/fmacfw_8800d80_u02.bin").is_file()
    assert builder.complete(lay.output)
    assert builder.output_commit(lay.output) == builder.PINS["legacy-mcu1"].commit
    (lay.output / "aic8800_fdrv.ko").unlink()
    assert not builder.complete(lay.output)
    assert builder.output_commit(tmp_path / "nowhere") == ""


def test_collect_reports_missing_firmware(tmp_path):
    lay = layout(tmp_path)
    for module in builder.built_modules(lay):
        write(module, "ELF")
    assert "no aic8800D80 firmware folder" in builder.collect(lay)
