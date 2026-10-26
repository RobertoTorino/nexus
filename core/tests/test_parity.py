# SPDX-License-Identifier: GPL-3.0-or-later
"""Migration gate: core's widgets render pixel-identical to the copies in governor and upscaler that they replace.

Each pair is built with the same arguments, rendered offscreen with grab() and compared as images. Once an app has
moved onto core its copy is gone and its cases are skipped."""

from __future__ import annotations

import importlib
import sys

import pytest
from PyQt6.QtWidgets import QPushButton, QWidget

from bc250_core import widgets as core
from conftest import SUITE

APPS = {"gpu": "gpu_governor", "upscaler": "upscaler"}


def _app_widgets(app: str):
    path = SUITE / "bc250-bazzite" / "apps" / app
    if not (path / APPS[app] / "widgets.py").is_file():
        pytest.skip(f"{app} has no widgets.py of its own any more")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return importlib.import_module(f"{APPS[app]}.widgets")


def _pixels(widget: QWidget, size=(240, 70)) -> bytes:
    widget.resize(*size)
    widget.ensurePolished()
    image = widget.grab().toImage()
    return bytes(image.constBits().asarray(image.sizeInBytes()))


def _same(make, old, new, **kwargs):
    a, b = make(old, **kwargs), make(new, **kwargs)
    assert _pixels(a) == _pixels(b)


CASES = {
    "status_pill": lambda m: (lambda p: (p.set_status("Active", "ok"), p)[1])(m.StatusPill("Active")),
    "status_pill_default": lambda m: m.StatusPill(),
    "metric_box": lambda m: (lambda b: (b.set_value("1800 MHz"), b)[1])(m.MetricBox("GPU clock", "#6a1b9a")),
    "metric_box_centred": lambda m: (lambda b: (b.set_value("1.4.3"), b)[1])(m.MetricBox("HelixSR payload", "#6a1b9a",
                                                                                         centred=True)),
    "metric_box_left": lambda m: (lambda b: (b.set_value("1.4.3"), b)[1])(m.MetricBox("HelixSR payload", "#6a1b9a",
                                                                                      centred=False)),
    "accent_button": lambda m: m.accent_button("Apply"),
    "hint_label": lambda m: m.hint_label("Takes effect after a restart of the governor service."),
    "page_header": lambda m: (lambda w: (w.setLayout(m.page_header("Tuning")[0]), w)[1])(QWidget()),
    "terminal": lambda m: (lambda t: (t.set_text("$ systemctl status\nactive (running)"), t)[1])(m.Terminal()),
}


@pytest.mark.parametrize("app", sorted(APPS))
@pytest.mark.parametrize("case", sorted(CASES))
def test_renders_like_app(qapp, app, case):
    if app == "gpu" and case == "status_pill_default":
        pytest.skip("core takes upscaler's StatusPill(); governor's differs only for text=None, which it never passes")
    old = _app_widgets(app)
    make = CASES[case]
    assert _pixels(make(old)) == _pixels(make(core))


def test_set_button_active_like_governor(qapp):
    old = _app_widgets("gpu")
    a, b = QPushButton("Stress test"), QPushButton("Stress test")
    old.set_button_active(a, True)
    core.set_button_active(b, True)
    assert _pixels(a, (160, 40)) == _pixels(b, (160, 40))


def test_palette_matches_every_copy():
    from bc250_core import theme
    for app in APPS:
        mod = _app_widgets(app)
        assert (mod.GREEN, mod.ORANGE, mod.RED, mod.BLUE, mod.GREY, mod.PURPLE, mod.ACCENT) == \
            (theme.GREEN, theme.ORANGE, theme.RED, theme.BLUE, theme.GREY, theme.PURPLE, theme.ACCENT)
        assert mod.STATE_COLORS == theme.STATE_COLORS
