# SPDX-License-Identifier: GPL-3.0-or-later
import time
from pathlib import Path

import pytest

from nexus_dashboard import tours
from nexus_dashboard.tours import AppsTourDialog, PortalTourDialog, TourApp

MANIFEST = '''
[apps.fan]
name = "BC-250 Fan Control"

[apps.compute]
name = "BC-250 CU Bisect"

[apps.gone]
name = "No program"

[checkout.installer-tests]
name = "BC-250 Installer Tests"
folder = "tools/gui"
'''

# Stands in for tools/record-app-tour.sh and tools/record-tour.sh: says what it got and writes the video it names.
FAKE_SCRIPT = '#!/usr/bin/env bash\necho "args: $*"\n{body}\n'


def checkout(tmp_path: Path, body: str = 'touch "$2"') -> Path:
    root = tmp_path / "suite"
    (root / "portal").mkdir(parents=True)
    (root / "portal" / "apps.toml").write_text(MANIFEST, encoding="utf-8")
    (root / "portal" / "VERSION").write_text("6.4.0\n", encoding="utf-8")
    for folder, packages, version in (("apps/fan", ["fan_control"], "0.5.1"),
                                      ("apps/compute", ["cu_unlock", "cu_bisect"], "0.3.0"),
                                      ("apps/gone", [], "1.0.0"),
                                      ("tools/gui", ["installer_tests"], "")):
        for package in packages:
            (root / folder / package).mkdir(parents=True)
            (root / folder / package / "__main__.py").touch()
        (root / folder).mkdir(parents=True, exist_ok=True)
        if version:
            (root / folder / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "tools").mkdir(exist_ok=True)
    (root / "tools" / "record-app-tour.sh").write_text(FAKE_SCRIPT.format(body=body), encoding="utf-8")
    (root / "tools" / "record-tour.sh").write_text(FAKE_SCRIPT.format(body='touch "$1"'), encoding="utf-8")
    return root


def wait(dialog, seconds: float = 10) -> None:
    from PyQt6.QtWidgets import QApplication
    end = time.monotonic() + seconds
    while dialog.running() and time.monotonic() < end:
        QApplication.processEvents()
        time.sleep(0.01)
    assert not dialog.running()


@pytest.fixture
def videos(tmp_path, monkeypatch):
    folder = tmp_path / "Videos"
    monkeypatch.setattr(tours, "videos_dir", lambda: folder)
    return folder


def test_every_program_of_the_manifest_once_in_its_order(tmp_path):
    apps = tours.tour_apps(checkout(tmp_path))

    assert [app.label for app in apps] == ["BC-250 Fan Control", "BC-250 CU Bisect (cu_bisect)",
                                           "BC-250 CU Bisect (cu_unlock)", "BC-250 Installer Tests"]
    assert [app.file_name for app in apps] == ["bc250-fan-tour-v0.5.1.mp4", "bc250-compute-cu_bisect-tour-v0.3.0.mp4",
                                               "bc250-compute-cu_unlock-tour-v0.3.0.mp4",
                                               "bc250-installer-tests-tour.mp4"]


def test_the_commands_carry_the_options(tmp_path):
    root = tmp_path / "suite"
    out = tmp_path / "out.mp4"

    assert tours.portal_command(root, out, music=True, wiki=False) == ["bash", str(root / "tools/record-tour.sh"),
                                                                       str(out)]
    assert tours.portal_command(root, out, music=False, wiki=True)[-2:] == ["--no-music", "--wiki"]
    assert tours.app_command(root, TourApp("compute", "CU", "cu_unlock"), out, 30, music=False) == [
        "bash", str(root / "tools/record-app-tour.sh"), "compute", str(out), "--package", "cu_unlock",
        "--seconds", "30", "--no-music"]


def test_a_size_other_than_1080p_is_passed_on_and_names_the_video(tmp_path):
    """--size goes to the scripts only for 1440p and 2160p, so an older checkout's scripts still run at 1080p; the
    video is then named as the scripts name it, -2160p before .mp4."""
    root = checkout(tmp_path)
    out = tmp_path / "out.mp4"

    assert tours.portal_command(root, out, music=True, wiki=False, size="1080p")[-1] == str(out)
    assert tours.portal_command(root, out, music=True, wiki=True, size="2160p")[-3:] == ["--wiki", "--size", "2160p"]
    assert tours.app_command(root, TourApp("fan", "Fan"), out, 40, music=True, size="1440p")[-4:] == [
        "--seconds", "40", "--size", "1440p"]
    assert tours.portal_video(root).name == "bc250-portal-tour-v6.4.0.mp4"
    assert tours.portal_video(root, "2160p").name == "bc250-portal-tour-v6.4.0-2160p.mp4"
    (root / "TAG_PREFIX").write_text("wp-\n", encoding="utf-8")         # a suite with a prefix: its videos too
    assert tours.portal_video(root).name == "wp-portal-tour-v6.4.0.mp4"
    assert tours.tour_apps(root)[0].file_name == "wp-fan-tour-v0.5.1.mp4"
    (root / "TAG_PREFIX").unlink()
    app = TourApp("fan", "Fan", None, "0.5.1")
    assert app.video() == app.file_name == "bc250-fan-tour-v0.5.1.mp4"
    assert app.video("2160p") == "bc250-fan-tour-v0.5.1-2160p.mp4"


def test_the_dialogs_record_at_the_chosen_size(qapp, tmp_path, videos):
    root = checkout(tmp_path)
    dialog = AppsTourDialog(root)
    assert dialog.size.currentText() == "1080p" and [dialog.size.itemText(i) for i in range(3)] == list(tours.SIZES)
    dialog.size.setCurrentText("2160p")
    assert dialog.apps.item(0).toolTip() == str(videos / "bc250-fan-tour-v0.5.1-2160p.mp4")
    dialog.apps.item(0).setCheckState(tours.Qt.CheckState.Checked)
    dialog.record()
    wait(dialog)
    assert dialog.made == [videos / "bc250-fan-tour-v0.5.1-2160p.mp4"]
    assert "--size 2160p" in dialog.output.toPlainText()
    dialog.close()

    dialog = PortalTourDialog(root)
    dialog.size.setCurrentText("1440p")
    dialog.record()
    wait(dialog)
    assert dialog.made == [videos / "bc250-portal-tour-v6.4.0-1440p.mp4"]
    assert "--size 1440p" in dialog.output.toPlainText()
    dialog.close()


def test_the_apps_dialog_records_the_ticked_apps_one_after_another(qapp, tmp_path, videos):
    dialog = AppsTourDialog(checkout(tmp_path))
    assert not dialog.record_button.isEnabled()                 # nothing ticked yet
    dialog.apps.item(0).setCheckState(tours.Qt.CheckState.Checked)
    dialog.apps.item(2).setCheckState(tours.Qt.CheckState.Checked)
    dialog.seconds.setValue(30)
    assert dialog.record_button.isEnabled()

    dialog.record()
    assert dialog.stop_button.isEnabled() and not dialog.record_button.isEnabled()
    wait(dialog)

    assert dialog.made == [videos / "bc250-fan-tour-v0.5.1.mp4", videos / "bc250-compute-cu_unlock-tour-v0.3.0.mp4"]
    text = dialog.output.toPlainText()
    assert "args: fan " in text and "--seconds 30" in text and "--package cu_unlock" in text
    assert "Done: 2 video(s)" in text
    assert dialog.record_button.isEnabled()
    dialog.close()


def test_a_failed_run_is_named_and_the_next_one_still_runs(qapp, tmp_path, videos):
    dialog = AppsTourDialog(checkout(tmp_path, body='[ "$1" = fan ] && exit 3; touch "$2"'))
    dialog._tick(True)

    dialog.record()
    wait(dialog)

    assert [path.name for path in dialog.failed] == ["bc250-fan-tour-v0.5.1.mp4"]
    assert len(dialog.made) == 3
    assert "stopped with status 3" in dialog.output.toPlainText()
    dialog.close()


def test_stop_ends_the_recording_and_what_it_started(qapp, tmp_path, videos):
    dialog = AppsTourDialog(checkout(tmp_path, body="sleep 60 & wait"))
    dialog._tick(True)

    dialog.record()
    start = time.monotonic()
    dialog.stop()
    wait(dialog, 5)

    assert time.monotonic() - start < 5
    assert dialog.made == [] and dialog.queue == []
    dialog.close()


def test_the_portal_dialog_records_into_videos_with_the_wiki_copy_when_asked(qapp, tmp_path, videos):
    played = []
    dialog = PortalTourDialog(checkout(tmp_path), played.append)
    dialog.music.setChecked(False)
    dialog.wiki.setChecked(True)

    dialog.record()
    wait(dialog)

    assert dialog.made == [videos / "bc250-portal-tour-v6.4.0.mp4"]
    assert "--no-music --wiki" in dialog.output.toPlainText()
    assert "wiki's copy is changed in the checkout" in dialog.output.toPlainText()
    dialog.play_button.click()
    assert played == [videos / "bc250-portal-tour-v6.4.0.mp4"]
    dialog.close()


def test_a_suite_without_the_tour_scripts_gets_the_dialog_greyed_out(qapp, tmp_path):
    """A Windows suite has no record-tour.sh: the dialog says so and records nothing."""
    root = checkout(tmp_path)
    (root / "tools" / "record-tour.sh").unlink()

    dialog = PortalTourDialog(root)

    assert dialog.checkout is None
    assert "has no tools/record-tour.sh" in dialog.output.toPlainText()
    assert not dialog.record_button.isEnabled()
    assert dialog.suite_label.text() == str(root)
    dialog.close()
