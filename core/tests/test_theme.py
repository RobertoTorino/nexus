# SPDX-License-Identifier: GPL-3.0-or-later
"""The suite's theme: one choice for every app, kept in one file, gunmetal when none is chosen."""

from __future__ import annotations

import pytest

from bc250_core import theme


def test_the_default_is_gunmetal(tmp_path):
    assert theme.DEFAULT_THEME == "gunmetal"
    assert theme.theme_name(tmp_path / "theme") == "gunmetal"                   # nothing chosen


def test_a_chosen_theme_is_kept(tmp_path):
    path = tmp_path / "bc250-bazzite-suite" / "theme"
    theme.save_theme_name("silver", path)
    assert path.read_text(encoding="utf-8") == "silver\n"
    assert theme.theme_name(path) == "silver"


def test_an_unknown_theme_is_the_default(tmp_path):
    path = tmp_path / "theme"
    path.write_text("Titanium\n", encoding="utf-8")
    assert theme.theme_name(path) == "gunmetal"
    with pytest.raises(ValueError):
        theme.save_theme_name("titanium", path)


def test_three_themes():
    assert list(theme.THEMES) == ["gunmetal", "silver", "warm"]
    assert [t.dark for t in theme.THEMES.values()] == [True, False, True]


def test_the_file_follows_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert theme.theme_file() == tmp_path / "bc250-bazzite-suite" / "theme"
    theme.save_theme_name("warm")
    assert theme.theme_name() == "warm"


@pytest.mark.parametrize("name", list(theme.THEMES))
def test_apply_theme(qapp, name):
    chosen = theme.THEMES[name]
    before = qapp.styleSheet()
    try:
        theme.apply_theme(qapp, "QLabel { color:red; }", chosen)
        assert qapp.palette().window().color().name() == chosen.window
        assert qapp.palette().highlight().color().name() == chosen.accent
        assert qapp.styleSheet() == theme.stylesheet(chosen) + "QLabel { color:red; }"     # the app's sheet after
    finally:
        theme.apply_theme(qapp, before.replace(theme.stylesheet(), ""))


def test_surface_style():
    plain = theme.surface_style()
    assert f"border-left:4px solid {theme.THEME.edge};" in plain and theme.THEME.text in plain
    assert "border-left:4px solid #c62828;" in theme.surface_style(theme.RED, "QLabel", 6)
    assert theme.surface_style(selector="QLabel", radius=6).startswith("QLabel {")


@pytest.mark.parametrize("name", list(theme.THEMES))
def test_muted_lies_between_text_and_window(name):
    from PyQt6.QtGui import QColor
    t = theme.THEMES[name]
    lightness = sorted(QColor(c).lightness() for c in (t.text, t.window))
    assert lightness[0] < QColor(theme.muted(t)).lightness() < lightness[1]


def test_hover_focus_and_chosen_borders_are_silver():
    """Every border under the mouse, with the focus or on the chosen tab is silver (owner, 05-11-2026), a darker
    silver on the light theme, never the accent; a theme without an outline of its own (Nexus's) keeps its accent."""
    from bc250_core.nexus import NEXUS
    assert {name: t.outline for name, t in theme.THEMES.items()} == {
        "gunmetal": "#c0c4c9", "silver": "#7d8389", "warm": "#c0c4c9"}
    for t in theme.THEMES.values():
        sheet = theme.stylesheet(t)
        assert f"QPushButton:hover, QToolButton:hover {{ border-color:{t.outline}; }}" in sheet
        assert f"border-top:2px solid {t.outline}" in sheet and f"border-color:{t.accent}" not in sheet
    assert theme.outline(NEXUS) == NEXUS.accent
    assert theme.OUTLINE in theme.HOVER_STYLESHEET
