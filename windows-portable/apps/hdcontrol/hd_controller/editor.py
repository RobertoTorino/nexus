# SPDX-License-Identifier: GPL-3.0-or-later
"""The profile editor (the BC250 app's, owner 23-10-2026) for the handheld: a profile's name, its sticks' curves and
sensitivity, its triggers' ranges and what each button sends, for Fn + Square, Cross or Circle, as rows a controller
steps through (the window's editor page: A the next value, X the one before; the name on a page of its own). It keeps
what the BC250 app's dialog keeps: a curve's points as they are until its curve or its sensitivity changes, a
trigger's exact byte while its percentage is unchanged, and every button as the dialog's list showed it. It returns
the settings; the window writes them."""

from __future__ import annotations

from . import profiles

BACK_BUTTONS = (14, 15)             # the back buttons send nothing of their own to another input
PERCENT_STEP = 5                    # a trigger's range moves this many percent a press
STICKS = (("left", "Left stick"), ("right", "Right stick"))
TRIGGERS = (("l2", "L2"), ("r2", "R2"))


def _percent(value: int) -> int:
    return round(value * 100 / 255)


def targets(index: int) -> list[int]:
    """What input *index* may send, its own first, as the dialog's list offered it."""
    return [index] + [value for value in profiles.OUTPUTS if value != index and value not in BACK_BUTTONS]


def _cycle(values: list, current, delta: int):
    """The value *delta* steps from *current* in *values*, round; the first one when *current* is not there."""
    at = values.index(current) if current in values else -delta if delta > 0 else 0
    return values[(at + delta) % len(values)]


def _percent_step(percent: int, delta: int) -> int:
    """The next multiple of PERCENT_STEP up or down from *percent*, round from 100 to 0 and back."""
    if delta > 0:
        nxt = (percent // PERCENT_STEP + 1) * PERCENT_STEP
        return 0 if nxt > 100 else nxt
    nxt = percent // PERCENT_STEP * PERCENT_STEP if percent % PERCENT_STEP else percent - PERCENT_STEP
    return 100 if nxt < 0 else nxt


class Editor:
    """The values of one profile while it is edited. rows() are (key, text) for the page; step(key, delta) changes
    one (+1 the next value, -1 the one before); settings() gives them back."""

    def __init__(self, slot: str, settings: profiles.Settings, creating: bool):
        self.slot, self.creating = slot, creating
        self.title = f"{'Create' if creating else 'Edit'} the profile Fn + {slot}"
        self.name = settings.name
        # A curve the list does not know shows as its first, Default, as the dialog's list showed it
        self.curves = {side: curve if curve in profiles.CURVES else 0
                       for side, curve in (("left", settings.left_curve), ("right", settings.right_curve))}
        # The level shown (the default while the points are kept), and whether the points are kept as they are
        self.levels = {"left": profiles.DEFAULT_LEVEL if settings.left_level is None else settings.left_level,
                       "right": profiles.DEFAULT_LEVEL if settings.right_level is None else settings.right_level}
        self.kept = {"left": settings.left_level is None, "right": settings.right_level is None}
        start_l2, end_l2, start_r2, end_r2 = settings.triggers
        self.raw = {"l2": (start_l2, end_l2), "r2": (start_r2, end_r2)}
        self.percents = {"l2": [_percent(start_l2), _percent(end_l2)], "r2": [_percent(start_r2), _percent(end_r2)]}
        self.buttons = []
        for index, value in enumerate(settings.buttons):
            choices = targets(index)
            self.buttons.append(value if value in choices else choices[0])    # the dialog's list showed its first

    def rows(self) -> list[tuple[str, str]]:
        rows = [("name", f"Name: {self.name}")]
        for side, label in STICKS:
            rows.append((f"{side}_curve", f"{label}: {profiles.CURVES[self.curves[side]]}"))
            rows.append((f"{side}_level", f"{label} sensitivity: "
                                          + ("as it is" if self.kept[side] else f"level {self.levels[side]}")))
        for trigger, label in TRIGGERS:
            start, end = self.percents[trigger]
            rows.append((f"{trigger}_start", f"{label} starts counting at: {start} %"))
            rows.append((f"{trigger}_end", f"{label} stops counting at: {end} %"))
        for index, name in enumerate(profiles.INPUTS):
            value = self.buttons[index]
            rows.append((f"button_{index}", f"{name} sends: "
                                            + ("its own" if value == index else profiles.OUTPUTS[value])))
        return rows

    def step(self, key: str, delta: int) -> None:
        for side, _label in STICKS:
            if key == f"{side}_curve":
                self.curves[side] = _cycle(list(profiles.CURVES), self.curves[side], delta)
                self.kept[side] = False
            elif key == f"{side}_level":
                self.levels[side] = (self.levels[side] + delta) % profiles.SENSITIVITY_LEVELS
                self.kept[side] = False
        for trigger, _label in TRIGGERS:
            for part, suffix in enumerate(("start", "end")):
                if key == f"{trigger}_{suffix}":
                    self.percents[trigger][part] = _percent_step(self.percents[trigger][part], delta)
        if key.startswith("button_"):
            index = int(key.split("_")[1])
            self.buttons[index] = _cycle(targets(index), self.buttons[index], delta)

    def set_name(self, name: str) -> None:
        self.name = name[:profiles.NAME_BYTES // 2]

    def problem(self) -> str:
        if not self.name.strip():
            return "Give the profile a name."
        if not profiles.name_fits(self.name):
            return "The name is too long."
        for trigger, label in TRIGGERS:
            start, end = self.percents[trigger]
            if start >= end:
                return f"{label}'s range must start before it ends."
        return ""

    def trigger(self, trigger: str) -> tuple[int, int]:
        """A trigger's range in bytes: an unchanged percentage keeps its exact byte."""
        def byte(percent: int, raw: int) -> int:
            return raw if percent == _percent(raw) else round(percent * 255 / 100)
        (start, end), (raw_start, raw_end) = self.percents[trigger], self.raw[trigger]
        return byte(start, raw_start), byte(end, raw_end)

    def settings(self) -> profiles.Settings:
        return profiles.Settings(self.name.strip(), self.curves["left"],
                                 None if self.kept["left"] else self.levels["left"], self.curves["right"],
                                 None if self.kept["right"] else self.levels["right"],
                                 self.trigger("l2") + self.trigger("r2"), tuple(self.buttons))
