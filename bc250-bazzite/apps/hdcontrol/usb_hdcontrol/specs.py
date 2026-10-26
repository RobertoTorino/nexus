# SPDX-License-Identifier: GPL-3.0-or-later
"""The controllers' fixed facts for the info sheet (owner, 23-10-2026), each with its source: only what an official
source says goes in. The DualSense Edge's come from its instruction manual (CFI-ZCP1) and the PlayStation Blog's
launch post; the price is the one the owner saw still listed on PlayStation's own page (23-10-2026). No official
source for the plain DualSense was found yet (shops disagree on its battery), so it has none here. Also the parts the
drawing leaves out, as the controller does not report them: they never light. The charging contacts are the one part
the manual does not describe: the owner found them on the Edge (23-10-2026), and their text says so."""

from __future__ import annotations

from dataclasses import dataclass

from .controller import EDGE

MANUAL = ("Instruction manual, DualSense Edge (CFI-ZCP1)",
          "https://www.playstation.com/content/dam/global_pdc/en/corporate/support/manuals/accessories/ps5-accessories/"
          "dualsense-wireless-controller-edge/EN_AMER_DualSense_Edge_Wireless_Controller_Instruction_Man_Web.pdf")
BLOG = ("PlayStation Blog, 18-10-2022: the launch announcement",
        "https://blog.playstation.com/2022/10/18/dualsense-edge-wireless-controller-for-ps5-launches-globally-on-"
        "january-26/")


@dataclass(frozen=True)
class Fact:
    name: str
    value: str
    source: tuple[str, str]


@dataclass(frozen=True)
class Part:
    name: str
    where: str
    what: str


FACTS: dict[int, tuple[Fact, ...]] = {
    EDGE: (
        Fact("Model number", "CFI-ZCP1", MANUAL),
        Fact("Released", "26 January 2023", BLOG),
        Fact("Price", "$199.99 at launch; still $199.99 on PlayStation's page (seen 23-10-2026)", BLOG),
        Fact("Battery", "Built-in lithium-ion, 3.7 V, 1,050 mAh", MANUAL),
        Fact("Input power rating", "5 V, 1,500 mA", MANUAL),
        Fact("Weight", "About 325 g (11.5 oz)", MANUAL),
        Fact("Operating temperature", "5 °C to 35 °C (41 °F to 95 °F)", MANUAL),
        Fact("Stick module", "About 30 × 31 × 40 mm and 15 g", MANUAL),
        Fact("Replacement stick module", "$19.99", BLOG),
        Fact("In the box", "USB braided cable, carrying case, connector housing, stick caps (standard, high dome, "
                           "low dome), back buttons (half dome, lever)", MANUAL),
    ),
}

PARTS: dict[int, tuple[Part, ...]] = {
    EDGE: (
        Part("L2 and R2 stop sliders", "Back", "Three strokes for each trigger: long, medium and short. On medium "
             "and short the trigger effects are off."),
        Part("RELEASE latch", "Back", "Slide it to take off the front cover and change a stick module."),
        Part("Reset button", "Back, a pinhole", "Press it with a pin if the controller responds unexpectedly; the "
             "pairing and the profiles stay."),
        Part("Back button slots", "Back", "Take either of the two back button types in the box."),
        Part("Connector housing", "Top", "Locks the USB cable to the controller."),
        Part("Headset jack", "Bottom edge", "For a headset or headphones (3.5 mm)."),
        Part("Charging contacts", "Bottom edge, two pins on each side of the headset jack", "For a charging "
             "cradle: some docks charge the controller through them instead of the USB cable. Sony's manual does not "
             "describe them; they carry no sound or picture."),
        Part("Microphone", "Bottom edge", "Built in."),
        Part("Speaker", "Front", "Built in."),
    ),
}
DUALSENSE_PARTS = (
    Part("Headset jack", "Bottom edge", "For a headset or headphones (3.5 mm)."),
    Part("Charging contacts", "Bottom edge, two pins on each side of the headset jack", "For a charging "
         "cradle: some docks charge the controller through them instead of the USB cable. Sony's manual does not "
         "describe them; they carry no sound or picture."),
    Part("Microphone", "Bottom edge", "Built in."),
    Part("Speaker", "Front", "Built in."),
)


def facts(product: int) -> tuple[Fact, ...]:
    return FACTS.get(product, ())


def parts(product: int) -> tuple[Part, ...]:
    return PARTS.get(product, DUALSENSE_PARTS)
