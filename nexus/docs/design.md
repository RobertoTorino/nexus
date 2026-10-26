<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Design

A suite has one design: the same colors, icons, fonts and shapes in every app and in the suite's wiki. Each suite
may have a design of its own.

Two listings at the root of the repository show what is in use:

- [DESIGN.md](https://github.com/RobertoTorino/nexus/blob/main/DESIGN.md): every color, where it is defined and
  what it is for, with a sample of each.
- [ICONS.md](https://github.com/RobertoTorino/nexus/blob/main/ICONS.md): every icon, per suite, and where it is used.

`tools/make_design.py` and `tools/make_icons.py` write them. Change the listing in the script and run it; `--check`
says whether a file is up to date. `make_design.py --check` also compares each wiki's stylesheet with its listing,
and the tests in `tools/tests/` do the same for the colors, the Material icons on the pages and the files of the
Nexus icon: a color or an icon added to a wiki fails the tests until the listing has it.

## Try a design in the wiki

### Live preview

Run MkDocs' own server from the root of the repository, in the venv:

```bash
mkdocs serve                        # the BC250 Bazzite Suite's wiki
mkdocs serve -f nexus/mkdocs.yml    # the Nexus page
```

Open the address it prints. Each time you save a page, a stylesheet or a template (`tools/mkdocs/overrides/`,
`nexus/overrides/`), the site is built again and the browser reloads.

Each wiki has a design of its own and shares no stylesheet, template or setting with another, so a change to one
never reaches the others:

| Wiki | Settings | Stylesheet | Templates |
| --- | --- | --- | --- |
| BC250 Bazzite Suite | `mkdocs.yml` | `docs/stylesheets/suite.css` | `tools/mkdocs/overrides/` |
| Nexus | `nexus/mkdocs.yml` | `nexus/docs/stylesheets/nexus.css` | `nexus/overrides/` |

Without a terminal: in BC250 Suite Releases, on **Test on this board** under **Test local apps**, the last icons are
the wikis, one for each `mkdocs.yml` in the checkout. A click serves that wiki and opens it with the design panel
open; a second click only opens the page again.

### Stop a wiki

`mkdocs serve` in a terminal stops with Ctrl+C. A wiki Suite Releases started keeps running when you close Suite
Releases, and a click on its icon only opens the page again, so a wiki started before the checkout changed (after a
pull, or a change to its `mkdocs.yml` or the design panel) can still show the old setup. Stop it, then click its
icon again. On Linux:

```bash
pkill -f "mkdocs serve"
```

On Windows, in PowerShell:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*mkdocs serve*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

Both stop every wiki that `mkdocs serve` serves on the computer.

### On other devices

To see the same pages on a phone, a handheld, the board or the TV, serve them on your network:

```bash
mkdocs serve -f nexus/mkdocs.yml -a 0.0.0.0:8000
```

Then open `http://<the computer's address>:8000` on each device. `ipconfig` (Windows) or `hostname -I` (Linux) shows
the address. In Suite Releases, tick **Wikis on the network** before clicking a wiki's icon: it serves the wiki that
way, on a port of its own (8785 for the BC250 Bazzite Suite's wiki, 8786 for the Nexus page), and shows the
addresses for the other devices. Every device shows the live version, so you see a design in real browsers, on real
screens and at real sizes at once.

The computer's firewall has to let the devices in:

- Windows asks the first time Python listens on the network: allow it on private networks.
- On Bazzite, open the port until the next boot with `sudo firewall-cmd --add-port=8000/tcp` (or `8785-8786/tcp`
  for Suite Releases' ports).

Serve on a network you trust only: everyone on it can open the pages and change the mock.

### The design panel

While `mkdocs serve` runs, every page has a **Design** button in its bottom left corner. It opens a panel with the
CSS variables of that wiki's own stylesheet, and the theme's fonts. Its first line names the wiki it changes and the
file the changes belong in. Add `?design` to an address to open the page with the panel open.

Each group is a part of the design, and each row says what it colors or sizes, with the variable's name below.
Hover over a row to see where the stylesheet uses the variable. The groups, the same in every wiki:

| Group | What it changes |
| --- | --- |
| The suite's colors (Nexus's colors on the Nexus page) | The few colors the rest of the design is made from. A change here changes every place that uses the color. |
| Corners | How round notes, code blocks, tables and pictures are. |
| Header | The bar at the top: its background, the color of the name and the links in it, and a link under the pointer (on the BC250 Bazzite Suite's wiki a fill behind it, on the Nexus page the dimmed word). |
| Material's main color | Buttons and Material's highlights, and the text on them. |
| Material's hover color | Links and buttons under the pointer. |
| The page | The page background and the links in the text. |
| Buttons | The shadow under a button under the pointer. |
| Tables | The background and text of a table's headings. |
| The home page | The words at the top, the dark sections (background, text, links and buttons) and, on the BC250 Bazzite Suite's wiki, the shadow under the pictures and the stage pill. |
| The home page's footer | Its background, the name and a link under the pointer, and the strip with the notice. |
| Fonts | The theme's fonts, set in `mkdocs.yml`. |

To change only the header, use **Header**. A change to a color under **The suite's colors** changes the header too
when the header uses that color (it uses the deep color until you set its background).

- A color has a color picker; a color with an opacity keeps it.
- A size (`px`, `rem`, `em`) has a slider.
- Every variable has a text field for any value. A font field suggests common fonts; a font the device does not have
  falls back to the next one in the list.
- ↺ sets one variable back, **Reset all** every one. A changed variable shows in purple.

A change shows at once, and goes to every page open on the same server within a second: a phone, the board and the
TV all show the same mock. The panel's top line says **shared with every device**, or **this device only** when the
server cannot be reached; the changes then stay in that browser.

**Copy CSS** copies the changed variables alone, under the rules that define them: a few lines, not a stylesheet.
**Copy stylesheet** copies the whole stylesheet with the changes written in, in place: the file as it is, comments
and all, only the values changed. Paste it over the stylesheet the panel's first line names:
`nexus/docs/stylesheets/nexus.css` for the Nexus page, `docs/stylesheets/suite.css` for the BC250 Bazzite Suite's
wiki. (The changes alone, pasted at the end of the file, work too, as the last rule wins, but then a variable is set
twice.) Over `http://` from another device the browser has no clipboard for it: the text below the buttons is then
selected, to copy by hand.

Without the browser, from the checkout:

```bash
python3 tools/apply_design.py nexus/mkdocs.yml    # one wiki; without an argument, every wiki that has a mock
```

Both write the same file: `tools/tests/test_design_panel.py` runs the panel's script in Node.js against the tool
(on Bazzite, `brew install node`; the test skips without it).

It writes the mock (`.design-mock.json` beside the wiki's `mkdocs.yml`) into the wiki's stylesheet the same way,
then empties the mock, as **Reset all** does, so the pages show the saved stylesheet. A font changed under **Fonts**
is set in `mkdocs.yml`, not in a stylesheet: the tool names it and leaves it to you.

The mock is kept next to the site's `mkdocs.yml`, in `.design-mock.json`, until **Reset all**; it outlasts a restart
of the server, and git ignores it. The panel is never part of `mkdocs build` or the published wiki.

### Screen sizes

**Screens** in the panel opens the page at the sizes of PC, laptop and handheld screens, one below the other:

| Screen | Size in the browser | The screen |
| --- | --- | --- |
| ASUS ROG Xbox Ally X | 1280 × 720 | 7 inch, 1920 × 1080 at 150 % scaling |
| Laptop | 1366 × 768 | 1366 × 768 |
| Laptop | 1536 × 864 | 1920 × 1080 at 125 % scaling |
| Laptop | 1440 × 900 | 16:10, 2880 × 1800 at 200 % scaling |
| Desktop | 1920 × 1080 | Full HD |
| Desktop | 2560 × 1440 | QHD |
| Desktop | 3840 × 2160 | 4K UHD at 100 % scaling |

The size in the browser is the screen's pixels divided by the system's display scaling: that is the width the page's
layout sees. Each is a real page of that size, scaled down to fit the window (or at 100 % or 50 %), so the layout
changes where it would on that screen; the browser's own bars take a little of the height on the device itself.

Tick the sizes to show, or add one as `1600x900`. Type another page's address in **Page** to show that one. The
pages follow the mock and reload when the site is built again, so a saved stylesheet shows on every size at once.

Every color in the stylesheets is a variable, so every color can be changed in the panel; sizes are variables
where the panel lists them. To make another size adjustable, give it a variable in the stylesheet and use that. Put a comment before its rule (the group's name) and one after the
variable on its line (what it does): the panel shows them, and the tests ask for them.
