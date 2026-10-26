# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from gpu_governor.backends.base import GovernorConfig
from gpu_governor.profiles import ProfileStore, ProfilesBox, clean_name


def test_store_round_trip(tmp_path):
    path = tmp_path / "profiles.json"
    store = ProfileStore(path)
    assert store.names() == [] and "x" not in store
    config = GovernorConfig(freq_min=1200, freq_max=1900, load_upper=0.9, sample_us=500)
    store.save("Quiet gaming", config)
    store.save("alpha", GovernorConfig())
    again = ProfileStore(path)
    assert again.names() == ["alpha", "Quiet gaming"]           # case-insensitive order
    assert again.get("Quiet gaming", GovernorConfig()) == config
    again.delete("alpha")
    assert ProfileStore(path).names() == ["Quiet gaming"]


def test_store_tolerates_old_or_broken_files(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text('{"Old": {"freq_min": "1500", "bogus": 1, "fix_metrics": 0, "load_upper": "x"}, "bad": 3}')
    store = ProfileStore(path)
    assert store.names() == ["Old"]
    config = store.get("Old", GovernorConfig(load_upper=0.9))
    assert config.freq_min == 1500 and config.fix_metrics is False and config.load_upper == 0.9
    path.write_text("not json")
    assert ProfileStore(path).names() == []


def test_clean_name():
    assert clean_name("  My   profile ") == "My profile"
    assert len(clean_name("x" * 100)) == 40


def test_box_buttons_follow_names(qapp):
    box = ProfilesBox()
    assert not box.load_button.isEnabled() and "No profiles" in box.hint.text()
    box.set_names(["a", "b"], select="b")
    assert box.combo.currentText() == "b" and box.apply_button.isEnabled() and box.hint.text() == ""
