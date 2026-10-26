# SPDX-License-Identifier: GPL-3.0-or-later
"""The drawn controller: it paints in every state, lights parts and pressed buttons in the blue, follows the sticks
and triggers, and runs its animations (the cable, the data of an update, the shake, turning back) only while
needed."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor

from usb_hdcontrol import drawing, style


def count(view, colour: str) -> int:
    image = view.grab().toImage()
    wanted = QColor(colour)
    return sum(image.pixelColor(x, y) == wanted for x in range(0, image.width(), 2)
               for y in range(0, image.height(), 2))


def make(edge: bool = True) -> drawing.ControllerView:
    view = drawing.ControllerView(edge=edge)
    view.resize(400, 300)
    return view


@pytest.mark.parametrize("edge", [True, False])
def test_paints_and_lights_parts(qapp, edge):
    view = make(edge)
    assert count(view, style.BLUE_LIGHT) == 0
    view.lit({"sticks", "triggers"})
    assert count(view, style.BLUE_LIGHT) > 0


def test_the_back_buttons_only_on_the_edge(qapp):
    edge, plain = make(True), make(False)
    for view in (edge, plain):
        view.lit({"back", "fn"})
    assert count(edge, style.BLUE_LIGHT) > 0 and count(plain, style.BLUE_LIGHT) == 0


def test_a_pressed_button_lights_and_lets_go(qapp):
    view = make()
    view.show_input({"l1"}, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0))
    lit = count(view, style.BLUE_LIGHT)
    assert lit > 0 and view.is_lit("l1") and not view.is_lit("r1")
    view.clear_input()
    assert count(view, style.BLUE_LIGHT) == 0


def test_a_pressed_face_button_takes_its_own_colour(qapp):
    view = make()
    before = count(view, drawing.FACE_COLOURS["circle"])
    view.show_input({"circle"}, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0))
    assert count(view, drawing.FACE_COLOURS["circle"]) > before


def test_a_pulled_trigger_fills_and_a_pushed_stick_lights(qapp):
    view = make()
    view.show_input(set(), (0.0, 0.0, 0.0, 0.0), (0.5, 0.0))
    half = count(view, style.BLUE_LIGHT)
    view.show_input(set(), (0.0, 0.0, 0.0, 0.0), (1.0, 0.0))
    full = count(view, style.BLUE_LIGHT)
    assert 0 < half < full
    view.show_input(set(), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0))
    assert count(view, style.BLUE_LIGHT) > 0


def test_the_light_bar_shows_its_colour(qapp):
    view = make()
    assert count(view, "#ff2020") == 0
    view.set_light(QColor("#ff2020"))
    assert count(view, "#ff2020") > 0


def test_an_unknown_part_is_an_error(qapp):
    with pytest.raises(ValueError, match="no such part: wheel"):
        make().lit({"wheel"})


def test_the_cable_comes_down_into_the_port_and_stays_a_moment():
    assert drawing.cable_offset(0.0) == pytest.approx(70)
    assert 0 < drawing.cable_offset(0.3) < 70
    assert drawing.cable_offset(0.6) == 0 and drawing.cable_offset(0.9) == 0
    assert drawing.cable_offset(1.0) == pytest.approx(70)


def test_animations_run_only_while_needed(qapp):
    view = make()
    assert not view.timer.isActive()
    view.animate_cable(True)
    assert view.timer.isActive()
    view._step()
    assert view.cable_phase > 0
    view.grab()
    view.animate_cable(False)
    assert not view.timer.isActive() and view.cable_phase is None
    view.show_data(0.4)
    assert view.timer.isActive() and count(view, style.BLUE_LIGHT) > 0
    view.show_data(None)
    view.shake("left")
    assert view.timer.isActive()
    view.grab()
    view.shake("")
    assert not view.timer.isActive()


def test_the_dpad_is_white_with_black_borders_and_gaps(qapp):
    view = make()
    assert count(view, "#ffffff") > 0
    image = view.grab().toImage()
    # The middle of the d-pad, between the four arms, is the body, not an arm.
    scale = min(view.width() / drawing.BOX.width(), view.height() / drawing.BOX.height())
    centre_x = view.width() / 2 + (drawing.DPAD_X - drawing.BOX.center().x()) * scale
    centre_y = view.height() / 2 + (106 - drawing.BOX.center().y()) * scale
    assert image.pixelColor(round(centre_x), round(centre_y)) != QColor("white")
    view.show_input({"up"}, (0.0, 0.0, 0.0, 0.0), (0.0, 0.0))
    assert count(view, style.BLUE_LIGHT) > 0



@pytest.mark.parametrize("point, name", [
    ((drawing.FACE_X, 81), "Triangle"), ((drawing.FACE_X, 131), "Cross"), ((drawing.DPAD_X, 86), "D-pad up"),
    ((drawing.x(150), 150), "Left stick: press it for L3"), ((200, 140), "PS button"),
    ((drawing.x(80), 20), "L2 trigger"), ((drawing.x(80), 36), "L1"), ((200, 36), "USB-C port"),
    ((200, 70), "Touchpad: press it to click"), ((drawing.x(136) + 3, 80), "Light bar"),
    ((drawing.x(150), 184), "Fn, left"), ((drawing.x(288), 214), "Right back button"),
    ((200, 250), ""),                                   # between the grips: no part
])
def test_each_part_is_named_where_it_is_drawn(point, name):
    found = drawing.part_at(True, QPointF(*point))
    assert found.startswith(name) if name else found == ""


def test_the_plain_dualsense_has_no_fn_or_back_buttons():
    for point in ((drawing.x(150), 184), (drawing.x(288), 214)):
        assert not drawing.part_at(False, QPointF(*point)).startswith(("Fn", "Right back"))


def test_the_tooltip_follows_the_mouse(qapp, monkeypatch):
    from PyQt6.QtGui import QMouseEvent
    shown, hidden = [], []
    monkeypatch.setattr(drawing, "show_tooltip", lambda pos, text, owner: shown.append(text))
    monkeypatch.setattr(drawing, "hide_tooltip", lambda: hidden.append(1))
    view = make()
    scale = min(view.width() / drawing.BOX.width(), view.height() / drawing.BOX.height())

    def move_to(bx, by):
        px = view.width() / 2 + (bx - drawing.BOX.center().x()) * scale
        py = view.height() / 2 + (by - drawing.BOX.center().y()) * scale
        assert view.to_box(QPointF(px, py)).x() == pytest.approx(bx)
        view.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, QPointF(px, py), QPointF(px, py),
                                        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                                        Qt.KeyboardModifier.NoModifier))
    move_to(drawing.FACE_X, 131)
    move_to(drawing.FACE_X, 132)                        # still the cross: shown once
    move_to(200, 140)
    move_to(200, 250)
    assert shown == ["Cross", "PS button"] and hidden == [1]


def test_the_player_indicator_names_the_player(qapp):
    view = drawing.ControllerView()
    assert drawing.part_at(True, QPointF(200, 118)) == "Player indicator"
    assert view._name("Player indicator") == "Player indicator"
    view.set_players((False, False, True, False, False))
    assert view._name("Player indicator") == "Player indicator: player 1" and view._name("Cross") == "Cross"
    view.set_players((False, True, True, False, False))                # no known pattern: no number
    assert view._name("Player indicator") == "Player indicator"
