#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Write DESIGN.md: every color of Nexus, core's themes and the Windows Portable Suite, where it is defined and
what it is for:

    python3 tools/make_design.py            # write DESIGN.md and its samples in design/colors/
    python3 tools/make_design.py --check    # only list what is out of date; exit 1 when anything is

A text color shows a sample sentence, any other color a block, each an SVG in design/colors/; a sample no
color uses any more is removed. The listing is the data below: change it here and run the script, not DESIGN.md
itself. The wikis' stylesheets are compared with their listings (STYLESHEETS): a color in a stylesheet that the
listing lacks, or a listed color the stylesheet no longer has, is reported by --check and by tools/tests."""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from pathlib import Path

S = ("A nexus is like a hub, the center every part leads back to. Nexus is where the suites connect: one repository "
     "holding every suite, the code they share, and the rules they’re built by.")
ROOT = Path(__file__).resolve().parent.parent
COLORS = "design/colors"                       # beside DESIGN.md: every suite's and the Nexus page's (owner, 28-10-2026)
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
      ("#7e97ad", "Accent: selection, progress."),
      ("#c0c4c9", "Silver outline: the border under the mouse, with the focus and of the chosen tab or item "
                  "(owner, 05-11-2026).")]),
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
      ("#5f7f9c", "Accent: selection, progress."),
      ("#7d8389", "Silver outline, darker on the light theme: the border under the mouse, with the focus and of "
                  "the chosen tab or item.")]),
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
      ("#b59a6e", "Accent: selection, progress."),
      ("#c0c4c9", "Silver outline: the border under the mouse, with the focus and of the chosen tab or item "
                  "(owner, 05-11-2026).")]),
]

STATE_TEXT = [
    ("#2e7d32", "Green: Passed, a valid entry."),
    ("#c62828", "Red: Failed, errors and problems in every app (the emulator managers' status lines, the Nexus Release Tool's "
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


NEXUS_TEXT = [
    ("#c0c0c0", "Silver: the header's links, table headings, the text, card titles, links and buttons of "
                "the dark sections, card text, the stage note, footer links, License and Disclaimer; text on the main "
                "color and the search field's hint."),
    ("#17b6a7", "Teal: links in the text, the icons on the home page's cards, the words at the top (the name and the "
                "claim), footer column headings, the footer's name and a footer link under the pointer, a dark "
                "section's link under the pointer, the text of the Nexus index button."),
    ("#808080", "A header link under the pointer (dimmed, no box); text on the hover color, and its dimmed text."),
    ("#010101", "Ink: a button's text on hover in the dark sections; text, links and buttons on the teal (the stage "
                "pill, Get started)."),
]
NEXUS_APP_TEXT = [
    ("#c0c0c0", "Silver: the text, the title, the boxes' values and captions, the buttons, the tabs and the fields."),
    ("#010101", "Ink: text on the teal accent (a selected row)."),
]
NEXUS_APP_BLOCKS = [
    ("#010101", "Ink: the window, the header and the dialogs; the bottom of a button's or a box's sheen; every other "
                "row of a table."),
    ("#0f0f0f", "Main color: the fields, lists and tables; the top of a button's or a box's sheen."),
    ("#17b6a7", "Teal: the accent: the selection, the outline of a selected cell or a focused field, a button or "
                "pill under the pointer, the main action (Apply, Bump portal, Retract), the progress bar."),
    ("#80808066", "Dimmed silver (40 %): the borders of the fields, boxes, tabs and buttons, and a box's neutral "
                  "edge."),
]
PORTABLE_TEXT = [
    ("#f5f4f0", "The text: the title, a card's title, the values, the legend and a gray pill's label."),
    ("#a5a5ab", "Dimmed: the version under the title, the line under a card's title, the labels of the values, the "
                "status line."),
    ("#f5a524", "Amber: an update in a tile or the detail pane, the selected tab."),
    ("#cd8b22", "The main pill's glyph letter, its pill's color."),
    ("#141414", "On the amber and the main pill: the main pill's label, a glyph on the amber."),
    ("#ff1f1f", "Hard red: the Turbo letter in the portal's status line, extra bold (owner, 31-10-2026)."),
]
PORTABLE_BLOCKS = [
    ("#121214", "The window, behind everything; a disabled pill's glyph circle."),
    ("#1d1e22", "A card, the detail pane, a field or list."),
    ("#292b31", "The focused card, a list's row, a disabled pill, a glyph's circle in the legend."),
    ("#3a3d45", "The focused row of a list (owner, 29-10-2026), with the amber edge."),
    ("#35383f", "Borders of fields and lists; a row under the pointer."),
    ("#f5a524", "Amber: the focused card's edge and the glow under it, the edge and glow of the pane the focus is "
                "in, the focused row's edge, the selected tab's line."),
    ("#cd8b22", "Every pill (owner, 29-10-2026: one kind of pill), and its glyph's letter."),
    ("#141414", "A pill's label and its glyph's circle."),
]
PORTABLE_WIKI_TEXT = [
    ("#f5f4f0", "The text: the pages, the header's name and links, table headings; on the home page the words under "
                "the handheld, the dark sections' text and card titles, the footer's name."),
    ("#a5a5ab", "Dimmed: the stage note and the card text on the home page, the footer's links, the search field's "
                "hint."),
    ("#f5a524", "Amber: links in the text, a header link under the pointer, the icons on the home page's cards, the "
                "footer's column headings, the Download button's text."),
    ("#141414", "Text on the amber: the stage pill, Get started."),
]
PORTABLE_WIKI_BLOCKS = [
    ("#121214", "The page and the header, as the window; the Download button, the footer's notice strip."),
    ("#1d1e22", "Code blocks, the home page's dark sections and its footer, as a card."),
    ("#292b31", "Table headings and Material's main color, as a focused card."),
    ("#35383f", "Lines: the header's bottom edge, between a table's rows, between the questions of the FAQ."),
    ("#f5a524", "Amber: links and buttons under the pointer, the outline on linked pictures, the main color's lighter "
                "step; the stage pill and the start of Get started's gradient on the home page."),
    ("#cd8b22", "The main color's darker step: the main pill's amber; the end of Get started's gradient."),
    ("#f5a5241a", "A faint amber behind what is under the pointer (10 %)."),
    ("#f5a52440", "The amber glow under the handheld on the home page and under a button under the pointer (25 %), "
                  "as under a focused card; behind code in Get started."),
]
NEXUS_BLOCKS = [
    ("#010101", "Ink: the page background, the header, the dark sections, the footer and its notice strip; the Nexus "
                "index button and a button under the pointer in Get started."),
    ("#0f0f0f", "Main color: Material's primary color, table headings."),
    ("#17b6a7", "Teal: the hover color of links and buttons, the outline on linked pictures; the stage pill and Get "
                "started on the home page."),
    ("#8080801a", "The hover color's faint fill behind what is under the pointer (10 %)."),
    ("#c0c0c0", "Silver: a button's fill under the pointer in the dark sections."),
    ("#ffffff", "The main color's lighter and darker steps, for Material."),
    ("#00000040", "The shadow under a button under the pointer (25 %)."),
    ("#010101e6", "The page dimmed behind the home page's video (90 %)."),
]

RULES = """## The rules

A design is recognizable by a few colors used the same way everywhere, not by a palette of every color there is.
Each design (a suite's, the Nexus page's) has its own; none is carried over to another.

### Windows Portable Suite

- **The identity** (owner, 26-10-2026: direction D, B's amber on C's cards): a near-black window `#121214`, cards a
  step lighter `#1d1e22`, the focused card raised `#292b31`, one amber `#f5a524` for the focus and every pill
  in `#cd8b22` (owner, 29-10-2026); text `#f5f4f0` with dimmed `#a5a5ab` for the second line. Inter, with
  heavy titles. From `core/bc250_core/portable.py`, a theme for core's widgets set with `create_app(theme=PORTABLE)`.
- **The focus is what a controller needs to see** (owner, 29-10-2026: "hardly visible where you are"): the focused
  card is raised with an amber edge and an amber glow under it. When the focus moves into the pane at the right, the
  pane takes the edge and the glow, and its card keeps the edge without the glow; back on the cards, the pane is
  plain again. In a list the focused row is lighter `#3a3d45` with the amber edge. Cards and pills share the corner
  radius 14.
- **One kind of pill, in popups only** (owner, 29-10-2026): `#cd8b22` with a dark label, the same height and
  minimum width, in a row at the bottom right of the popup with the A pill rightmost; a pane holds none, every action
  being in the legend. Focused or under the pointer it is dimmed. Nothing is grayed out: what cannot act says why
  (owner, 29-10-2026). The glyph paints its own circle (a stylesheet's radius showed a square on the Ally).
- **The legend at the bottom is the row of actions** (owner, 29-10-2026): every action is an entry there, A too
  (A Steam mark, Y Update Steam, LB Folders, RB Steam artwork), its glyph gray, and every legend ends with the shared
  ones: ☰ Info (the pane's information), B Back (while B can act) and ⧉ Exit; a tap on an entry does what the
  button does. The information icon at a pane's top right is touch only, a ring with its sign.
- **A tile is a card with an icon** (the portal's apps, 28-10-2026): the app's icon centered above its name and
  its status, two rows of four under the category tabs; a status that asks for something (an update, a reinstall,
  an install running) is amber, the rest dimmed. The strip under the tiles is the detail pane, flat, with the
  focused app's pills at its right.

### Nexus

- **The identity:** near-black ink `#010101`, silver text `#c0c0c0` and one teal `#17b6a7` (the icon's) for every
  link, title and icon; nothing else. Inter, with heavy titles. Nexus is not a suite: the page has no apps and no
  states. Its one app, Nexus Release Tool (`dev/nrt/`, owner, 26-10-2026: a Nexus app takes Nexus's design), has
  this design in its window (`nexus_release_tool/style.py`, a theme for core's widgets: ink surfaces, silver text, the
  teal accent) and the Nexus icon; its states (the working tree, a build) are the apps' state family, since a build
  passes or fails there too.
"""




# Each wiki's stylesheet and the listing of its colors: the two must name the same colors.
# A suite in a repository of its own (owner, 13-11-2026; tools/suites.py has the list) is in the checkout only when
# cloned into it as its folder.
OWN_REPOSITORY = ("windows-portable",)
STYLESHEETS = {
    "nexus/docs/stylesheets/nexus.css": (NEXUS_TEXT, NEXUS_BLOCKS),
    "windows-portable/docs/stylesheets/portable.css": (PORTABLE_WIKI_TEXT, PORTABLE_WIKI_BLOCKS),
}








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

The colors of Nexus, core's themes and the Windows Portable Suite, where they are defined and what they are for. Text colors show a sample sentence in that
color; background colors (surfaces, fills, borders and lines) show a block. The samples are SVG files in
`design/colors/`. A text sample sits on a dark or a light backdrop, whichever its color reads on; a color with
an opacity (written `#rrggbbaa` here, `#aarrggbb` in the Qt code) shows over a checkerboard. The icons are in
[ICONS.md](ICONS.md). Written by `tools/make_design.py`: change the listing there and run it.

The rules say what makes each design recognizable; the listings after them say where every color is used. The
BC250 Bazzite Suite's design is in its own repository's DESIGN.md (it moved there on 14-11-2026).
""", RULES, """## Core's themes

The theme, the state colors and the style sheets are in `core/bc250_core/theme.py` (bundled per app). The theme is
one choice for every app on it: Gunmetal, Silver or Warm.
"""]
    for title, t, b in THEMES:
        out.append(section(title, "", t, b))
    out.append(section("State colors", "The same in every theme: a state shows as a colored edge or dot on the "
                       "theme's surfaces.", STATE_TEXT, STATE_BLOCKS))
    out.append("## The Windows Portable Suite\n\n`core/bc250_core/portable.py`, the portable window: direction D "
               "(the owner's, 26-10-2026).\n")
    out.append(section("Portable window", "The apps of the Windows Portable Suite, sized for a handheld held in the "
                       "hands.", PORTABLE_TEXT, PORTABLE_BLOCKS))
    out.append(section("Wiki", "`windows-portable/docs/stylesheets/portable.css`: the portable window's colors on "
                       "Material's slate scheme.", PORTABLE_WIKI_TEXT, PORTABLE_WIKI_BLOCKS))
    out.append("## The Nexus page\n\n`nexus/docs/stylesheets/nexus.css`, ink, silver and teal (the owner's design, "
               "25-10-2026): the Nexus page has a\ndesign of its own, apart from the suites' (a design per system).\n")
    out.append(section("Nexus", "", NEXUS_TEXT, NEXUS_BLOCKS))
    out.append(section("Nexus Release Tool", "The window of Nexus's app (`dev/nrt/nexus_release_tool/style.py`): the "
                       "page's colors as a theme for core's widgets, set with `create_app(theme=NEXUS)`; its "
                       "states are the apps' state family.", NEXUS_APP_TEXT, NEXUS_APP_BLOCKS))
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
            if path.split("/")[0] in OWN_REPOSITORY and not (root / path.split("/")[0]).is_dir():
                continue                    # that suite is not in this checkout: its listing is checked where it is
            out.append(f"{path} is missing")
            continue
        listed = {hex_.lower() for hex_, _ in text_rows + block_rows}
        found = stylesheet_colours(sheet.read_text(encoding="utf-8"))
        out += [f"{path} has {hex_}, which the listing lacks" for hex_ in sorted(found - listed)]
        out += [f"{path} no longer has {hex_}, which the listing has" for hex_ in sorted(listed - found)]
    return out


def differences(files: dict[str, str], root: Path = ROOT) -> tuple[list[str], list[str]]:
    """The files that are missing or differ from *files*, and the samples in design/colors/ no color uses."""
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
