#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write DESIGN.md: every color of the suites, where it is defined and what it is for:

    python3 tools/make_design.py            # write DESIGN.md and its samples in docs/design/colors/
    python3 tools/make_design.py --check    # only list what is out of date; exit 1 when anything is

A text color shows a sample sentence, any other color a block, each an SVG in docs/design/colors/; a sample no
color uses any more is removed. The listing is the data below: change it here and run the script, not DESIGN.md
itself. The wikis' stylesheets are compared with their listings (STYLESHEETS): a color in a stylesheet that the
listing lacks, or a listed color the stylesheet no longer has, is reported by --check and by tools/tests."""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

S = ("A nexus is a hub, the center every part leads back to. Nexus is where the suites connect: one repository "
     "holding every suite, the code they share, and the rules they’re built by.")
ROOT = Path(__file__).resolve().parent.parent
SUITE_DIR = "bc250-bazzite"                 # the BC250 Bazzite Suite's folder
COLORS = f"{SUITE_DIR}/docs/design/colors"
DARK, LIGHT = "#22262a", "#eceef0"      # the backdrops: Gunmetal's and Silver's fields
FILES: dict[str, str] = {}              # what build() writes: path in the checkout -> text


def luminance(hex_):
    def channel(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(hex_[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def write(name, svg):
    FILES[f"{COLORS}/{name}"] = svg
    return f"{COLORS}/{name}"


def text_svg(hex_):
    backdrop = DARK if contrast(hex_, DARK) >= contrast(hex_, LIGHT) else LIGHT
    lines = textwrap.wrap(S, 74)
    width, height = 600, 16 + 20 * len(lines)
    spans = "".join(f'<tspan x="12" dy="{20 if i else 0}">{line}</tspan>' for i, line in enumerate(lines))
    return write(f"text-{hex_[1:]}.svg",
                 f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
                 f'viewBox="0 0 {width} {height}">\n'
                 f'  <rect width="{width}" height="{height}" rx="6" fill="{backdrop}"/>\n'
                 f'  <text x="12" y="25" fill="{hex_}" font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif" '
                 f'font-size="14">{spans}</text>\n'
                 f'</svg>\n')


def block_svg(hex_):
    colour, alpha = hex_[:7], int(hex_[7:9], 16) / 255 if len(hex_) == 9 else None
    fill = f'<rect width="64" height="24" fill="{colour}"/>'
    checker = ""
    if alpha is not None:       # a translucent color over a checkerboard, so its opacity shows
        checker = ('  <defs><pattern id="c" width="8" height="8" patternUnits="userSpaceOnUse">'
                   '<rect width="8" height="8" fill="#ffffff"/><rect width="4" height="4" fill="#c4c8cd"/>'
                   '<rect x="4" y="4" width="4" height="4" fill="#c4c8cd"/></pattern></defs>\n'
                   '  <rect width="64" height="24" fill="url(#c)"/>\n')
        fill = f'<rect width="64" height="24" fill="{colour}" fill-opacity="{alpha:.3f}"/>'
    return write(f"block-{hex_[1:]}.svg",
                 '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="24" viewBox="0 0 64 24">\n'
                 f'{checker}  {fill}\n'
                 '  <rect x="0.5" y="0.5" width="63" height="23" fill="none" stroke="#808080" stroke-opacity="0.5"/>\n'
                 '</svg>\n')


def text(rows):
    out = []
    for hex_, use in rows:
        out.append(f"- `{hex_}` {use}\n\n  ![Sample text in {hex_}]({text_svg(hex_)})\n")
    return "\n".join(out)


def blocks(rows):
    out = ["| Color | Hex | Used for |", "| --- | --- | --- |"]
    for hex_, use in rows:
        out.append(f"| ![{hex_}]({block_svg(hex_)}) | `{hex_}` | {use} |")
    return "\n".join(out) + "\n"


THEMES = [
    ("Gunmetal (dark, the default)",
     [("#d9dde2", "Text on every surface."),
      ("#82868b", "Muted text: versions, hints, placeholders, disabled buttons (text and window mixed)."),
      ("#ffffff", "Text on the accent (selected rows and items)."),
      ("#7e97ad", "Links.")],
     [("#2b2f34", "Window and dialog background; the selected tab."),
      ("#22262a", "Text fields, lists, tables, tooltips, progress bars and scroll bars."),
      ("#292d32", "Every other row of a list or table."),
      ("#4a5058", "Button face, top of its sheen; scroll bar handles."),
      ("#3b4048", "Button face, bottom of its sheen."),
      ("#606872", "Palette light (the button face 30 % lighter)."),
      ("#14171a", "Borders and shadows."),
      ("#7e97ad", "Accent: selection, focus, hover outline, progress, the selected tab's top edge.")]),
    ("Silver (light)",
     [("#1e2226", "Text on every surface."),
      ("#7a7d81", "Muted text: versions, hints, placeholders, disabled buttons."),
      ("#ffffff", "Text on the accent."),
      ("#5f7f9c", "Links.")],
     [("#d5d8dc", "Window and dialog background; the selected tab."),
      ("#eceef0", "Text fields, lists, tables, tooltips, progress bars and scroll bars."),
      ("#e2e5e8", "Every other row of a list or table."),
      ("#eef0f2", "Button face, top of its sheen; scroll bar handles."),
      ("#c4c8cd", "Button face, bottom of its sheen."),
      ("#ffffff", "Palette light (the button face 30 % lighter)."),
      ("#8d9298", "Borders and shadows."),
      ("#5f7f9c", "Accent: selection, focus, hover outline, progress, the selected tab's top edge.")]),
    ("Warm (dark)",
     [("#e3dfd8", "Text on every surface."),
      ("#8c8984", "Muted text: versions, hints, placeholders, disabled buttons."),
      ("#1b1a18", "Text on the accent."),
      ("#b59a6e", "Links.")],
     [("#35332f", "Window and dialog background; the selected tab."),
      ("#292826", "Text fields, lists, tables, tooltips, progress bars and scroll bars."),
      ("#302e2b", "Every other row of a list or table."),
      ("#57534d", "Button face, top of its sheen; scroll bar handles."),
      ("#45423d", "Button face, bottom of its sheen."),
      ("#716c64", "Palette light (the button face 30 % lighter)."),
      ("#181716", "Borders and shadows."),
      ("#b59a6e", "Accent: selection, focus, hover outline, progress, the selected tab's top edge.")]),
]

STATE_TEXT = [
    ("#2e7d32", "Green: Passed, a valid entry."),
    ("#c62828", "Red: Failed, errors and problems in every app (the emulator managers' status lines, Suite Releases' "
                "bad tags, the upscaler's problems, a folder that is missing)."),
    ("#ffffff", "Bright text (palette BrightText); text on the state colors."),
]
STATE_BLOCKS = [
    ("#2e7d32", "Green, ok: a state's edge or dot; an unlocked CU; a pressed controller button."),
    ("#ef6c00", "Orange, warn."),
    ("#c62828", "Red, bad; the red buttons of the bisect apps and of Clean up logs."),
    ("#b71c1c", "The red buttons under the pointer or pressed (the bisect apps, Clean up logs)."),
    ("#1565c0", "Blue, info."),
    ("#3a3f4b", "Gray, neutral."),
    ("#6a1b9a", "Purple, the logo's purple."),
    ("#fdd835", "Yellow, running: never confused with a failed (red) state."),
    ("#8b0000", "Active red: the GPU Governor's active button."),
    ("#a00000", "Active red on hover."),
    ("#424242", "Off: a locked CU, a core without a state."),
    ("#1d4f91", "Steam artwork: the accent when an icon gives no bright color."),
]

WIKI_TEXT = [
    ("#ffffff", "Header, hero, cards and footer text; table headings; the stage pill; buttons on the dark and accent "
                "sections."),
    ("#ffffffb3", "Dimmed text on the main and the hover color: the search field's hint."),
    ("#a98bff", "Suite soft: links in the dark scheme; hover on the dark section; footer column headings."),
    ("#c9bfee", "Suite mist: card text and footer links."),
    ("#1e1340", "Suite deep: a button's text on hover in the dark and accent sections."),
]
WIKI_BLOCKS = [
    ("#5835ce", "Suite primary: Material's primary color, table headings, page icons, the hero and Get started "
                "gradients."),
    ("#7a5ce0", "Primary, light."),
    ("#4426a8", "Primary, dark."),
    ("#8a2be2", "Suite secondary: the accent (hover rings on linked images), the end of the gradients."),
    ("#8a2be21a", "The accent at 10 %."),
    ("#1e1340", "Suite deep: header and tabs, the hero's top, the Download button."),
    ("#120c22", "Suite ink: the dark section and the home page's footer."),
    ("#120c2273", "The shadow under the board and the controller at the top of the home page (45 %)."),
    ("#17141f", "Page background (the dark scheme)."),
    ("#8b4fd8", "The stage pill under the claim."),
    ("#ffffff", "Button background on hover in the dark and accent sections."),
    ("#ffffff1f", "Behind a link in the header under the pointer (12 %)."),
    ("#00000040", "The shadow under a button under the pointer (25 %)."),
    ("#00000059", "The strip with the notice at the bottom of the home page's footer (35 %)."),
]

NEXUS_TEXT = [
    ("#c0c0c0", "Silver: the header's links, table headings, the text, card titles, links and buttons of "
                "the dark sections, card text, footer links; text on the main color and the search field's hint."),
    ("#17b6a7", "Teal: links in the text, the icons on the home page's cards, the words at the top (the name and the "
                "claim), footer column headings, the footer's name and a footer link under the pointer, a dark "
                "section's link under the pointer."),
    ("#808080", "A header link under the pointer (dimmed, no box); text on the hover color, and its dimmed text."),
    ("#010101", "Ink: a button's text on hover in the dark sections."),
]
NEXUS_BLOCKS = [
    ("#010101", "Ink: the page background, the header, the dark sections, the footer and its notice strip."),
    ("#0f0f0f", "Main color: Material's primary color, table headings."),
    ("#17b6a7", "Teal: the hover color of links and buttons, the outline on linked pictures."),
    ("#8080801a", "The hover color's faint fill behind what is under the pointer (10 %)."),
    ("#c0c0c0", "Silver: a button's fill under the pointer in the dark sections."),
    ("#ffffff", "The main color's lighter and darker steps, for Material."),
    ("#00000040", "The shadow under a button under the pointer (25 %)."),
]

RULES = """## The rules

A design is recognizable by a few colors used the same way everywhere, not by a palette of every color there is.
Each design (a suite's, the Nexus page's) has its own; none is carried over to another.

### BC250 Bazzite Suite

- **The identity:** the purple of the board icon and the wiki (`#5835ce` with `#8a2be2`, the logo's `#6a1b9a`),
  and the apps' Gunmetal theme, steel gray with the steel-blue accent `#7e97ad`. Inter, with heavy titles. Every
  app has the icon of its category.
- **One theme for every app** (Gunmetal, Silver or Warm, the user's choice), from `core/bc250_core/theme.py`: the
  surfaces, text and accent below. An app adds no surface or text color of its own.
- **One state family,** the same in every theme: green `#2e7d32` ok, orange `#ef6c00` warn, red `#c62828` bad,
  blue `#1565c0` info, yellow `#fdd835` running, gray `#3a3f4b` neutral. A state is an edge or a dot on the theme's
  surface; a header box or pill in the neutral state shows the blue as its edge, as the portal's pills (owner,
  26-10-2026), never the theme's dark edge color. A red button is the red with `#b71c1c` pressed. Active red `#8b0000` (`#a00000` under the pointer) is a
  toggled-on state, never an error.
- **Text in a state color sits on a dark surface** in the next lighter tint of the same hue (Material's 300:
  red `#e57373`, orange `#ffb74d`, green `#81c784`, blue `#64b5f6`, purple `#ce93d8`), because the state fills read
  poorly as text on the dark views. The log in the check app uses them; a second tint of a hue is a deviation.
- **Brand and hardware colors stay what they are:** PlayStation blue and the face-button colors in the PlayStation
  apps, the light bar's and the color wheel's pure colors in HD Control, a game's own artwork, the gaming blue
  `#0a55b0` of the gaming category's icon in the emulator managers.
- **Anything else is a deviation**, listed under Color families below with the app it is in. A new color is
  added to the family it belongs to, or it needs a reason here.

### Nexus

- **The identity:** near-black ink `#010101`, silver text `#c0c0c0` and one teal `#17b6a7` (the icon's) for every
  link, title and icon; nothing else. Inter, with heavy titles. The Nexus page is not a suite: it has no apps, no
  theme and no states.
"""

# The hues of the BC250 Bazzite Suite: every tint in use, what it is and why. kind: family, tint, brand, hardware,
# deviation. A deviation is a second color for a job the family already has a color for.
FAMILIES = [
    ("Red", [
        ("#c62828", "family", "Bad: failed, an error, a problem; the red buttons."),
        ("#b71c1c", "family", "A red button pressed or under the pointer (the bisect apps, Clean up logs)."),
        ("#8b0000", "family", "Active red: the GPU Governor's active button (a toggled-on state, not an error)."),
        ("#a00000", "family", "Active red under the pointer."),
        ("#e57373", "tint", "Red text on a dark surface: the check app's findings, log, in-game checks, history and "
                            "scores; the error labels of ACPI, CU Unlock and Cores Unlock; SFTP Tools' password "
                            "requirements not met; NetcatGUI's error lines."),
        ("#d04545", "brand", "NetcatGUI's red tab (its own palette, below)."),
        ("#e8505b", "brand", "PlayStation's circle: HD Control's circle button, DatStation's circle symbol."),
        ("#ff2020", "hardware", "The light bar's red; `#ff0000` the color wheel's."),
    ]),
    ("Orange and yellow", [
        ("#ef6c00", "family", "Warn."),
        ("#fdd835", "family", "Running."),
        ("#ffb74d", "tint", "Orange text on a dark surface: the check app's warnings, log, in-game checks and middle "
                            "scores; SFTP Tools' password warning."),
        ("#e08a1e", "brand", "NetcatGUI's orange tab (its own palette, below)."),
        ("#ffd166", "brand", "DatStation's PS News symbol."),
        ("#ffd700", "brand", "DatStation's gold: trophies and stars; `#c0c0c0` silver, `#cd7f32` bronze."),
        ("#ffff00", "hardware", "The color wheel's yellow."),
    ]),
    ("Green", [
        ("#2e7d32", "family", "Ok: passed, valid, unlocked, a pressed controller button; a right answer."),
        ("#81c784", "tint", "Green text on a dark surface: the check app's log success, in-game ok, a better result "
                            "in its history and full scores; SFTP Tools' password requirements met; NetcatGUI's "
                            "success lines."),
        ("#2e9e5b", "brand", "NetcatGUI's green tab (its own palette, below)."),
        ("#3dbf9c", "brand", "PlayStation's triangle: HD Control's triangle button, DatStation's triangle symbol."),
        ("#10d040", "hardware", "The light bar's green; `#00ff00` the color wheel's."),
    ]),
    ("Blue", [
        ("#1565c0", "family", "Info; the check app's GPU score box; HDMI CEC's adapter box."),
        ("#64b5f6", "tint", "Blue text on a dark surface: the check app's info and hint findings."),
        ("#0a55b0", "brand", "Gaming blue, the gaming icon's: the emulator managers' primary button, with `#2a6cc4` "
                             "under the pointer and `#08448d` pressed; `#5b93da` their links."),
        ("#003791", "brand", "PlayStation blue (DatStation), `#0072ce` light, `#1a85e0` under the pointer, "
                             "`#00589f` pressed; `#4da3ef` its links."),
        ("#6f9fe8", "brand", "PlayStation's cross: HD Control's cross button, DatStation's cross symbol (the square "
                             "is `#e48fc0` in both)."),
        ("#3c7dd9", "brand", "NetcatGUI's header names and blue tab (its own palette, below)."),
        ("#1f3e9c", "brand", "BIOS Reader's bar and selection, with `#0b2a8a` and `#10205a`: a classic BIOS screen."),
        ("#0050ff", "hardware", "The light bar's blue (the default); `#0000ff` the color wheel's."),
    ]),
    ("Purple", [
        ("#6a1b9a", "family", "The logo's purple, the suite's own state color."),
        ("#5835ce", "family", "The wiki's purple, with `#8a2be2`: the suite's identity on the web."),
        ("#ce93d8", "tint", "Purple text on a dark surface: the check app's log hints, Show in log link, in-game "
                            "accent and the overlay's frame rate and border."),
        ("#8b4fd8", "family", "The stage pill under the claim on the wiki's home page."),
        ("#8e5bd0", "brand", "NetcatGUI's purple tab (its own palette, below)."),
        ("#a020f0", "hardware", "The light bar's purple; `#ff00ff` the color wheel's magenta."),
    ]),
    ("Palettes of their own", [
        ("#d04545", "brand", "NetcatGUI's tabs: red, orange `#e08a1e`, green `#2e9e5b`, blue `#3c7dd9`, purple "
                             "`#8e5bd0`, gray `#8a8f98`: the tab colors of the tool it ports, a user's choice per tab."),
        ("#8a5a2e", "brand", "Upscaler's copper and teal `#0e6f75` boxes, cyan `#26a9b0` outlines: the icon's colors."),
        ("#ad1457", "brand", "The check app's System overview: cores, threads `#00796b`, upload `#3949ab`, NVMe "
                             "`#6d4c41`, packages `#5e35b1`, BIOS `#00838f`, a seventh series `#5d4037`: a chart's "
                             "series, each told apart from the others."),
    ]),
]
KINDS = {"family": "the family", "tint": "text tint", "brand": "brand or icon", "hardware": "hardware",
         "deviation": "deviation"}


def families() -> str:
    out = ["## Color families", "",
           "Every tint of each hue in the BC250 Bazzite Suite, and why it is there. *The family* is the suite's "
           "state color, *text tint* its lighter tint for text on a dark surface, *brand or icon* a color that "
           "belongs to something else (PlayStation, a tool ported, an icon), *hardware* a color the device shows, "
           "and *deviation* a second color for a job the family already has one for: there is none (the last were "
           "unified 26-10-2026).", ""]
    for hue, rows in FAMILIES:
        out += [f"### {hue}", "", "| Color | Hex | Kind | Where and why |", "| --- | --- | --- | --- |"]
        for hex_, kind, use in rows:
            out.append(f"| ![{hex_}]({block_svg(hex_)}) | `{hex_}` | {KINDS[kind]} | {use} |")
        out.append("")
    return "\n".join(out)


# Each wiki's stylesheet and the listing of its colors: the two must name the same colors.
STYLESHEETS = {
    f"{SUITE_DIR}/docs/stylesheets/suite.css": (WIKI_TEXT, WIKI_BLOCKS),
    "nexus/docs/stylesheets/nexus.css": (NEXUS_TEXT, NEXUS_BLOCKS),
}

GAMING_TEXT = [
    ("#5b93da", "Links on a dark window (Console Link, Console LinkB, Decky, PCSX2, PPSSPP, RPCS3, shadPS4, Vita3K, "
                "Xenia; HD Control's lit parts)."),
    ("#ffffff", "Text on the blue primary button and on the shortcut artwork."),
]
GAMING_BLOCKS = [
    ("#0a55b0", "Gaming blue: the primary button, hover borders; the blue of the gaming apps' icon."),
    ("#2a6cc4", "Gaming blue on hover."),
    ("#08448d", "Gaming blue while pressed."),
    ("#0a55b01a", "Blue tint (10 %): hover, every other table row."),
    ("#0a55b059", "Blue line (35 %): outlines, a pressed button."),
    ("#80808080", "Disabled (50 % gray)."),
    ("#5b93da", "HD Control: lit parts of the controller, the chosen card."),
    ("#0b1d3a", "shadPS4 shortcut artwork, top of the gradient."),
    ("#030810", "shadPS4 shortcut artwork, bottom."),
    ("#16123a", "RPCS3 shortcut artwork, top."),
    ("#05040f", "RPCS3 shortcut artwork, bottom."),
    ("#0d2a4a", "PPSSPP shortcut artwork, top."),
    ("#04080f", "PPSSPP shortcut artwork, bottom."),
    ("#3a2c0d", "Vita3K shortcut artwork, top."),
    ("#0f0b03", "Vita3K shortcut artwork, bottom."),
    ("#000000", "Console Link's stream view."),
]

DAT_TEXT = [
    ("#4da3ef", "Links on a dark window."),
    ("#0072ce", "Links on a light window."),
    ("#3dbf9c", "Triangle: the Quiz symbol (the face-button colors, as HD Control draws them)."),
    ("#e8505b", "Circle: the History symbol."),
    ("#6f9fe8", "Cross: the System Version History symbol."),
    ("#e48fc0", "Square: the Region Codes symbol."),
    ("#ffd166", "The PS News symbol."),
    ("#ffd700", "Gold: the Scores & Trophies symbol, a perfect quiz, gold stars."),
    ("#c0c0c0", "Silver stars."),
    ("#cd7f32", "Bronze stars."),
    ("#2e7d32", "Right answers: the count and the feedback."),
    ("#c62828", "Wrong answers: the count; little time left."),
]
DAT_BLOCKS = [
    ("#003791", "PlayStation blue."),
    ("#0072ce", "PlayStation light blue: hover borders."),
    ("#1a85e0", "Blue on hover."),
    ("#00589f", "Blue while pressed."),
    ("#2e7d32", "A right answer's button."),
    ("#c62828", "A wrong answer's button."),
]

UPSCALER_TEXT = [
    ("#3fc8cf", "Links on a dark window."),
    ("#0e6f75", "Links on a light window."),
]
UPSCALER_BLOCKS = [
    ("#8a5a2e", "Copper: boxes, white text on them."),
    ("#0e6f75", "Teal: boxes, white text on them."),
    ("#26a9b0", "Cyan, the icon's: button outlines."),
]

CHECK_TEXT = [
    ("#9aa0a6", "Muted: versions, hints, notes, baselines, the in-game and overlay labels."),
    ("#e6e6e6", "Text in the results and history views, on idle buttons, the overlay's values."),
    ("#e8e8e8", "Code blocks in the README view."),
    ("#d0d0d0", "The log; a disabled Clean up logs button."),
    ("#1a1a1a", "Text on the yellow running button."),
    ("#222222", "Text on the system score boxes."),
    ("#333333", "Labels on the graph's bars."),
    ("#e57373", "Error findings; a worse result in the history; a low score; the log's errors; error labels (also in "
                "ACPI, CU Unlock and Cores Unlock); the in-game error."),
    ("#ffb74d", "Warning findings; a middle score; the log's warnings; the in-game warning."),
    ("#64b5f6", "Info and hint findings."),
    ("#81c784", "A better result in the history; the log's success; a full score; the in-game ok."),
    ("#fdd835", "A score's warning: the running yellow."),
    ("#ce93d8", "Log: hint; the Show in log link; the in-game accent; the overlay's frame rate and thin border."),
    ("#90a4ae", "Log: note."),
    ("#ffffff", "README table headings."),
]
CHECK_BLOCKS = [
    ("#111418", "The log; the overlay's background (82 %)."),
    ("#1e1f24", "The results and history views; code blocks in the README view."),
    ("#14161c", "The results card and the score dialog."),
    ("#2a2d36", "The empty part of a score ring."),
    ("#2a2f37", "The log's border."),
    ("#3a3f4a", "The borders of the preview, setup, checks and stat cards."),
    ("#555555", "The screenshot's border."),
    ("#888888", "README table borders."),
    ("#3a3f4b", "Idle buttons; README table headings; Clean up logs, disabled."),
    ("#b71c1c", "Clean up logs under the pointer and pressed."),
    ("#f8fafc", "The system score boxes."),
    ("#1565c0", "The GPU score box: the info blue."),
    ("#ad1457", "System overview: cores."),
    ("#00796b", "System overview: threads."),
    ("#3949ab", "System overview: upload speed."),
    ("#6d4c41", "System overview: NVMe."),
    ("#5e35b1", "System overview: packages."),
    ("#00838f", "System overview: BIOS; the graph's sixth series."),
    ("#5d4037", "The graph's seventh series."),
]

OTHER_TEXT = [
    ("#888888", "Busy and hint labels in italics (ACPI, CU Bisect, CU Unlock, Cores Bisect, Cores Unlock)."),
    ("#ef6c00", "An incomplete ACPI override; a CU mask that needs checking."),
    ("#b8b8c8", "System Overlay: the names of the values."),
    ("#dddddd", "Console Link's stream view."),
    ("#ffb74d", "SFTP: the password warning."),
    ("#e57373", "SFTP: password requirements not met; NetcatGUI: error lines in the session."),
    ("#81c784", "SFTP: password requirements met; NetcatGUI: success lines in the session."),
    ("#d2691e", "NetcatGUI: HTTP and status replies."),
    ("#3c7dd9", "NetcatGUI: header names."),
    ("#8a8f98", "NetcatGUI: byte counts."),
    ("#ffffff", "BIOS Reader: tabs, crumbs, the legend and the selection."),
    ("#0b2a8a", "BIOS Reader: the screen's text."),
    ("#10205a", "BIOS Reader: subtitles."),
    ("#6e6e6e", "BIOS Reader: hidden items."),
    ("#7d7d8c", "BIOS Reader: locked items."),
    ("#2e7d32", "Installer Tests: passed."),
]
OTHER_BLOCKS = [
    ("#1f3e9c", "BIOS Reader: the bar and the selection."),
    ("#c6c6c6", "BIOS Reader: the screen."),
    ("#1565c0", "HDMI-CEC: the adapter box."),
    ("#000000", "HDMI-CEC: the display box; HD Control: the light bar off."),
    ("#c62828", "SFTP: the errors button."),
    ("#5f6368", "VRAM: firmware in the memory map."),
    ("#00838f", "VRAM: zswap in the memory map."),
    ("#3dbf9c", "HD Control: the triangle button."),
    ("#e8505b", "HD Control: the circle button."),
    ("#6f9fe8", "HD Control: the cross button."),
    ("#e48fc0", "HD Control: the square button."),
    ("#0050ff", "HD Control light bar: blue (the default)."),
    ("#ff2020", "Light bar: red."),
    ("#10d040", "Light bar: green."),
    ("#a020f0", "Light bar: purple."),
    ("#ffffff", "Light bar: white."),
    ("#ff0000", "The light bar's color wheel: red."),
    ("#ffff00", "Color wheel: yellow."),
    ("#00ff00", "Color wheel: green."),
    ("#00ffff", "Color wheel: cyan."),
    ("#0000ff", "Color wheel: blue."),
    ("#ff00ff", "Color wheel: magenta."),
    ("#d04545", "NetcatGUI tab: red."),
    ("#e08a1e", "NetcatGUI tab: orange."),
    ("#2e9e5b", "NetcatGUI tab: green."),
    ("#3c7dd9", "NetcatGUI tab: blue."),
    ("#8e5bd0", "NetcatGUI tab: purple."),
    ("#8a8f98", "NetcatGUI tab: gray."),
    ("#04060c", "Portal Big Picture: the backdrop."),
    ("#1b1b1b", "Portal Big Picture: the outline of the update badge."),
    ("#808080", "Portal Big Picture: a tab on hover (16 %)."),
]

SCREENSHOT_TEXT = [
    ("#fcfcfc", "Window, field, button and tooltip text."),
    ("#a1a9b1", "Placeholders."),
    ("#1d99f3", "Links."),
]
SCREENSHOT_BLOCKS = [
    ("#202326", "Window."), ("#141618", "Fields and lists."), ("#1d1f22", "Every other row."),
    ("#292c30", "Buttons and tooltips."), ("#3daee9", "Selection."), ("#43474d", "Mid."),
    ("#33373b", "Midlight."), ("#101113", "Dark."), ("#3d4146", "Light."),
]


def section(title, intro, text_rows, block_rows):
    parts = [f"### {title}\n", intro + "\n" if intro else ""]
    if text_rows:
        parts += ["Text colors:\n", text(text_rows)]
    if block_rows:
        parts += ["Background colors:\n", blocks(block_rows)]
    return "\n".join(p for p in parts if p)


def build() -> dict[str, str]:
    """DESIGN.md and its samples: each path in the checkout with its text."""
    FILES.clear()
    out = ["""# Design

The colors of the suite, where they are defined and what they are for. Text colors show a sample sentence in that
color; background colors (surfaces, fills, borders and lines) show a block. The samples are SVG files in
`bc250-bazzite/docs/design/colors/`. A text sample sits on a dark or a light backdrop, whichever its color reads on; a color with
an opacity (written `#rrggbbaa` here, `#aarrggbb` in the Qt code) shows over a checkerboard. The icons are in
[ICONS.md](ICONS.md). Written by `tools/make_design.py`: change the listing there and run it.

The rules say what makes each design recognizable; the color families say, for every tint of a hue, why it is
there; the listings after them say where every color is used.
""", RULES, families(), """## The apps

The theme, the state colors and the style sheets are in `core/bc250_core/theme.py` (bundled per app; the apps that
are not on core yet carry a copy). The theme is one choice for every app: Gunmetal, Silver or Warm.
"""]
    for title, t, b in THEMES:
        out.append(section(title, "", t, b))
    out.append(section("State colors", "The same in every theme: a state shows as a colored edge or dot on the "
                       "theme's surfaces.", STATE_TEXT, STATE_BLOCKS))
    out.append("## The wiki\n\n`bc250-bazzite/docs/stylesheets/suite.css`, Material's slate scheme with the suite's purple.\n")
    out.append(section("Wiki", "", WIKI_TEXT, WIKI_BLOCKS))
    out.append("## The Nexus page\n\n`nexus/docs/stylesheets/nexus.css`, ink, silver and teal (the owner's design, "
               "25-10-2026): the Nexus page has a\ndesign of its own, apart from the suites' (a design per system).\n")
    out.append(section("Nexus", "", NEXUS_TEXT, NEXUS_BLOCKS))
    out.append("## The apps' own colors\n\nOn top of the theme, in the apps' `style.py` or where they are used.\n")
    out.append(section("Gaming apps", "Console Link, Console LinkB, Decky, HD Control, PCSX2, PPSSPP, RPCS3, "
                       "shadPS4, Vita3K and Xenia.", GAMING_TEXT, GAMING_BLOCKS))
    out.append(section("DatStation", "", DAT_TEXT, DAT_BLOCKS))
    out.append(section("Upscaler", "", UPSCALER_TEXT, UPSCALER_BLOCKS))
    out.append(section("BC-250 Bazzite Test (check)", "", CHECK_TEXT, CHECK_BLOCKS))
    out.append(section("Other apps", "", OTHER_TEXT, OTHER_BLOCKS))
    out.append("## Tools\n")
    out.append(section("Portal screenshots", "`bc250-bazzite/tools/portal_screenshot.py` paints the portal in a fixed dark palette "
                       "(Breeze Dark, as Bazzite's desktop shows the portal), so screenshots look the same on every "
                       "machine.", SCREENSHOT_TEXT, SCREENSHOT_BLOCKS))
    FILES["DESIGN.md"] = "\n".join(out).rstrip("\n") + "\n"
    return dict(FILES)


def stylesheet_colours(css: str) -> set[str]:
    """The colors written in a stylesheet (its comments left out), as #rrggbb or #rrggbbaa in lower case."""
    code = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    found = set()
    for hex_ in re.findall(r"#[0-9a-fA-F]{3,8}\b", code):
        hex_ = hex_.lower()
        if len(hex_) in (4, 5):                         # #rgb and #rgba, written out
            hex_ = "#" + "".join(c + c for c in hex_[1:])
        found.add(hex_)
    return found


def unlisted(root: Path = ROOT) -> list[str]:
    """What the wikis' stylesheets and their listings disagree on: a color in the one but not in the other."""
    out = []
    for path, (text_rows, block_rows) in STYLESHEETS.items():
        sheet = root / path
        if not sheet.is_file():
            out.append(f"{path} is missing")
            continue
        listed = {hex_.lower() for hex_, _ in text_rows + block_rows}
        found = stylesheet_colours(sheet.read_text(encoding="utf-8"))
        out += [f"{path} has {hex_}, which the listing lacks" for hex_ in sorted(found - listed)]
        out += [f"{path} no longer has {hex_}, which the listing has" for hex_ in sorted(listed - found)]
    return out


def differences(files: dict[str, str], root: Path = ROOT) -> tuple[list[str], list[str]]:
    """The files that are missing or differ from *files*, and the samples in docs/design/colors/ no color uses."""
    changed = [name for name, text in files.items()
               if not (root / name).is_file() or (root / name).read_text(encoding="utf-8") != text]
    folder = root / COLORS
    stale = sorted(f"{COLORS}/{p.name}" for p in folder.glob("*.svg") if f"{COLORS}/{p.name}" not in files) \
        if folder.is_dir() else []
    return changed, stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="only list what is out of date")
    args = parser.parse_args(argv)
    files = build()
    changed, stale = differences(files)
    disagree = unlisted()
    if args.check:
        for name in changed:
            print(f"out of date: {name}")
        for name in stale:
            print(f"no longer used: {name}")
        for line in disagree:
            print(f"not listed: {line}")
        if disagree:
            print("change the listing in tools/make_design.py and run it")
        if changed or stale:
            print("run python3 tools/make_design.py")
        if changed or stale or disagree:
            return 1
        print("DESIGN.md and its samples are up to date")
        return 0
    for line in disagree:
        print(f"not listed: {line}")
    for name in changed:
        path = ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[name], encoding="utf-8", newline="\n")
    for name in stale:
        (ROOT / name).unlink()
    print(f"wrote {len(changed)} files, removed {len(stale)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
