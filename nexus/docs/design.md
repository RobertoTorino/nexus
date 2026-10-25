<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Design

A suite has one design: the same colours, icons, fonts and shapes in every app and in the suite's wiki. Each suite
may have a design of its own.

Two listings at the root of the repository show what is in use:

- [DESIGN.md](https://github.com/RobertoTorino/nexus/blob/main/DESIGN.md): every colour, where it is defined and
  what it is for, with a sample of each.
- [ICONS.md](https://github.com/RobertoTorino/nexus/blob/main/ICONS.md): every icon, per suite, and where it is used.

`tools/make_design.py` and `tools/make_icons.py` write them. Change the listing in the script and run it; `--check`
says whether a file is up to date.

## Try a design in the wiki

### Live preview

Run MkDocs' own server from the root of the repository, in the venv:

```bash
mkdocs serve                        # the BC250 Bazzite Suite's wiki
mkdocs serve -f nexus/mkdocs.yml    # the Nexus page
```

Open the address it prints. Each time you save a page, a stylesheet or a template (`tools/mkdocs/overrides/`,
`nexus/overrides/`), the site is built again and the browser reloads. The stylesheets:

- `docs/stylesheets/suite.css`: the wiki's layout and the BC250 Bazzite Suite's colours. The Nexus page takes its
  layout too.
- `nexus/docs/stylesheets/nexus.css`: the Nexus page's own colours, over that layout.

Without a terminal: in BC250 Suite Releases, on **Test on this board** under **Test local apps**, the last icons are
the wikis, one for each `mkdocs.yml` in the checkout. A click serves that wiki and opens it with the design panel
open; a second click only opens the page again.

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
CSS variables of the site's own stylesheets (`extra_css` in its `mkdocs.yml`), grouped by the rule that defines them,
and the theme's fonts. Where two stylesheets set the same variable, the panel shows the one the page uses: the
later one, such as `nexus.css` over `suite.css`. Add `?design` to an address to open the page with the panel open.

- A colour has a colour picker; a colour with an opacity keeps it.
- A size (`px`, `rem`, `em`) has a slider.
- Every variable has a text field for any value. A font field suggests common fonts; a font the device does not have
  falls back to the next one in the list.
- ↺ sets one variable back, **Reset all** every one. A changed variable shows in purple.

A change shows at once, and goes to every page open on the same server within a second: a phone, the board and the
TV all show the same mock. The panel's top line says **shared with every device**, or **this device only** when the
server cannot be reached; the changes then stay in that browser.

**Copy CSS** copies the changed variables, under the rules that define them, to paste into the stylesheet: for the
Nexus page's colours that is `nexus.css`, for the BC250 Bazzite Suite's wiki `suite.css`. Over
`http://` from another device the browser has no clipboard for it: the CSS below the buttons is then selected, to
copy by hand.

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

Only what the stylesheet gives a variable can be changed in the panel. To make a colour or a size adjustable, give
it a variable in the stylesheet and use that.
