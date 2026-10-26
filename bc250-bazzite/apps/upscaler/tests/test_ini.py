# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import replace

from upscaler import backend
from upscaler.backend import DEFAULT_INI_TEXT, HelixIni, parse_ini, render_ini, validate_ini


def test_defaults_match_upstream_file():
    assert parse_ini(DEFAULT_INI_TEXT) == HelixIni()
    assert render_ini(HelixIni(), DEFAULT_INI_TEXT) == DEFAULT_INI_TEXT


def test_parse_values_and_comments():
    text = "[Sharpening]\nMode = override ; trailing\nSharpness=0.75\nMotionAdaptive = FALSE\n[ModelE]\nNetwork=main\n"
    ini = parse_ini(text)
    assert ini.sharpening_mode == "override"
    assert ini.sharpness == 0.75
    assert ini.motion_adaptive is False
    assert ini.network == "main"
    assert ini.log_enabled is True  # untouched keys keep HelixSR's default


def test_render_edits_in_place_and_keeps_comments():
    changed = replace(HelixIni(), sharpness=0.9, sharpening_mode="override", log_enabled=False)
    out = render_ini(changed, DEFAULT_INI_TEXT)
    assert "Sharpness = 0.9" in out
    assert "Mode = override" in out
    assert out.count("[Sharpening]") == 1
    assert out.splitlines()[0] == DEFAULT_INI_TEXT.splitlines()[0]   # leading comment block preserved
    assert parse_ini(out) == changed


def test_render_appends_missing_keys_and_sections():
    out = render_ini(replace(HelixIni(), forwarding_dll="other.dll", network="nvidia"), "[Sharpening]\nMode = off\n")
    assert "[Forwarding]" in out and "Dll = other.dll" in out
    assert "[ModelE]" in out and "Network = nvidia" in out
    assert parse_ini(out).forwarding_dll == "other.dll"


def test_round_trip_all_fields():
    ini = HelixIni("game", 1.0, False, 3.5, 20.0, 0.1, False, "ultraperformance", True, True, True, False,
                   "a.dll", "b.dll")
    assert parse_ini(render_ini(ini)) == ini


def test_validate():
    assert validate_ini(HelixIni()) == []
    bad = replace(HelixIni(), sharpness=2.0, sharpening_mode="bogus", network="nope", motion_reduction=-1)
    problems = validate_ini(bad)
    assert len(problems) >= 3
    assert any("Sharpness" in p or "sharpness" in p for p in problems)


def test_ini_template_prefers_payload(payload, tmp_path):
    (payload / backend.INI).write_text("[Log]\nEnabled = false\n; mine\n", encoding="utf-8")
    assert "; mine" in backend.ini_template(payload)
    assert backend.ini_template(tmp_path / "nowhere") == DEFAULT_INI_TEXT


def test_ignored_fields_per_version():
    assert backend.ini_ignored_fields("") == set()
    assert backend.ini_ignored_fields("1.4.3") == {"sharpener", "use_game_slider"}
    assert {"sharpening_mode", "sharpness", "sharpener", "network"} <= backend.ini_ignored_fields("1.7.0")
    assert backend.ini_ignored_fields("1.8.0") == {"sharpening_mode", "network"}


def test_new_1_8_keys_are_written_only_when_set():
    assert "Sharpener" not in render_ini(HelixIni()) and "UseGameSlider" not in render_ini(HelixIni())
    out = render_ini(replace(HelixIni(), sharpener="nvidia", sharpness=0.5, use_game_slider=True))
    assert "Sharpener = nvidia" in out and "UseGameSlider = true" in out and out.count("[Sharpening]") == 1
    assert parse_ini(out).sharpener == "nvidia"
    # a file that has the key keeps it, also when it goes back to the default
    assert "Sharpener = off" in render_ini(HelixIni(), out)
    assert any("Sharpener" in p for p in validate_ini(replace(HelixIni(), sharpener="nis")))
