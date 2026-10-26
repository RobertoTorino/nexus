# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from usb_hdcontrol import controller, specs
from usb_hdcontrol.pages import info_html


def test_every_fact_has_an_official_source():
    for product in controller.MODELS:
        for fact in specs.facts(product):
            name, url = fact.source
            assert name and url.startswith(("https://www.playstation.com/", "https://blog.playstation.com/"))


def test_the_edges_facts_as_sony_gives_them():
    facts = {fact.name: fact.value for fact in specs.facts(controller.EDGE)}
    assert facts["Model number"] == "CFI-ZCP1" and facts["Released"] == "26 January 2023"
    assert facts["Battery"].endswith("1,050 mAh") and facts["Price"].startswith("$199.99")


def test_no_facts_for_the_plain_dualsense_without_a_source():
    assert specs.facts(0x0CE6) == ()
    assert [part.name for part in specs.parts(0x0CE6)][:3] == ["Headset jack", "Charging contacts", "Microphone"]


def test_the_parts_out_of_the_drawing():
    names = [part.name for part in specs.parts(controller.EDGE)]
    assert "L2 and R2 stop sliders" in names and "RELEASE latch" in names and "Reset button" in names
    contacts = [part for part in specs.parts(controller.EDGE) if part.name == "Charging contacts"]
    assert contacts and "manual does not describe them" in contacts[0].what


def test_the_sheet_numbers_its_sources():
    text = info_html([("Model", "DualSense Edge")], controller.EDGE)
    assert "This controller" in text and "Specifications" in text and "Not in the drawing" in text
    assert "1. <a href='https://www.playstation.com/" in text and "2. <a href='https://blog.playstation.com/" in text
    assert "CFI-ZCP1 <sup>1</sup>" in text and "26 January 2023 <sup>2</sup>" in text


def test_the_sheet_of_a_model_without_facts_says_so():
    text = info_html([("Model", "DualSense")], 0x0CE6)
    assert "no specifications of this model yet" in text and "Sources" not in text
