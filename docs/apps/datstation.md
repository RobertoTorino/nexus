<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Bazzite DatStation](../assets/datstation/bazzite-datstation.webp){ .app-logo }

# Bazzite DatStation

Bazzite DatStation is the PlayStation knowledge part of the DatStation Android app, on **Bazzite** or any other
Linux desktop. A front page of tiles opens a PlayStation quiz against the clock, the history of every PlayStation
console, every system software release, the region codes explained, Sony's user guides and the latest PlayStation
news, and keeps your quiz scores and trophies.

The app does not change how the board runs. Nothing is installed system-wide and nothing is layered with
`rpm-ostree`.

## What it needs

- Python 3.10 or newer: Bazzite ships `python3`. The installer makes the app's own virtual environment with PyQt6
  in it (the wheel bundles Qt, with Qt Multimedia for the quiz music), so nothing else is needed.
- A network connection for PS News and for the links to PlayStation's pages. Everything else works offline: the
  questions, the history, the system versions and the region codes ship with the app.
- For Game Mode: Steam, for the non-Steam game the app adds.

## Install

In the [portal](../portal.md), click the Install button beside its icon. Or by hand: from the suite's
[Releases](https://github.com/RobertoTorino/nexus/releases) page, download the
`datstation-v<version>.tar.gz` release and extract it. Run `install.sh` as your own user, without `sudo`:

```shell
./install.sh
```

It installs:

- `~/.local/share/bazzite-datstation/app`: the app, and `venv` next to it with PyQt6.
- `~/.local/bin/bazzite-datstation`: starts the window.
- An app menu entry ("Bazzite DatStation", under Games) and an icon on the Desktop.
  `./install.sh --no-desktop-shortcut` leaves the Desktop icon out.

Install it again to update. Uninstall it in the portal, or with `./install.sh --uninstall`: that removes the app,
the venv, the launcher and the menu entry, and keeps your settings and scores; `./install.sh --uninstall --purge`
removes those too.

**Steam Game Mode:** in the app, open the **Menu** beside the title and choose **Add to Steam**. It adds the app
as a non-Steam game for every Steam user on the board, with artwork drawn from the app's icon, and the title line
shows **In Steam**. Steam closes while its shortcut file changes and starts again afterwards, so do this from Desktop
Mode; from Game Mode the app asks you to switch. **Remove from Steam** takes it out again, artwork included.

## Using it

The first line shows the logo, the name and version, whether the app is in Steam, and the **Menu** (Add to Steam,
Remove from Steam, Scores & Trophies, the project page, About). Under it the front page: four rows of four tiles,
one per feature; the others say Coming Soon and are grayed out. A tile opens its page; **Back** or Escape returns
to the tiles.

With a controller in Game Mode, Steam Input's default desktop layout does the work: the D-pad or the left stick
moves between the tiles and the buttons, A (cross) presses one, B (circle) is Escape and goes back. The keys 1
to 4 answer a quiz question when the layout has them.

### PlayStation Quiz

Pick a category (ALL, TRUE/FALSE, PS1 to PS5, PSVITA, PSP, CONTROLLER, GENERAL, DIALOGUE, APPS; the tooltip says
how many questions it has), or the **Quick Quiz**: 6 questions, nothing saved.

A round starts with 42 seconds on the clock. A right answer adds 5 seconds and the question's points (10); a
wrong answer or **Skip** takes 5 seconds. The clock stops while an answer is shown and while the game is paused
(**Pause**, then **Resume**). The right answer turns green, a wrong choice red, and for a wrong answer the right
one is named, with an explanation where the question has one. A question is not asked twice in one game until
the category's questions are used up.

The round ends when all its questions are answered, or when the clock runs out. The results show the right and
wrong answers, the time left, the total score with the share of right answers and, for a complete round, a review
with a bronze (50 % and more), silver (75 %) or gold (95 %) star. A round with every answer right is a **Perfect
round**: **Next round** then asks five questions more, with the score and the clock kept. Otherwise **Retry**
starts the category again from zero. **Change** picks another category.

Every finished round of a saved game adds a score to Scores & Trophies; a perfect round adds a Perfect trophy. The
quick quiz adds nothing. The music can be turned off with **Music on / Music off** beside the title; the choice
is kept.

### PlayStation History

Every console since 1994 with its launch year, what it sold and how many titles it had: the PlayStation,
PlayStation 2, Sony PSX, PlayStation Portable, PlayStation 3, PlayStation Vita, PlayStation 4, PlayStation 5 and the
PlayStation Portal. Under the totals, a brief overview of each console's legacy. Click a console's name, in either
list, for pictures of it on the web, in your browser.

### System Version History

The systems on the left, the versions of the chosen one on the right: every system software release with its
release date, its notes and, where the data has them, its region, model, color, size and hardware facts. The
PlayStation 6 entry is a placeholder until there is one.

### Region Codes Explained

Per PlayStation, what the prefix of a title ID says about the market and the publisher (PPSA, ELJM, BCES, SLUS,
...), in a table, and for the PS1 and PS2 what the last digit of the model number says about the region.

### PlayStation User Guides

Opens Sony's online manuals for every PlayStation product (`manuals.playstation.net`) in your browser.

### PS News

The latest announcements from the PlayStation.Blog feed, newest first, with their date; a click opens the post in
your browser. **Upcoming Games** and **New Releases** open PlayStation's pages. **Refresh** loads the feed again.
Only links to PlayStation's own sites (`playstation.com`, `blog.playstation.com`, `store.playstation.com`) are
opened; anything else in the feed is blocked and said so in the status line.

### Scores & Trophies

Your best score, the top ten rounds with their category, round and time, and the trophies. **Clear scores** removes
them all, after asking.

## From the terminal

```bash
bazzite-datstation              # the window
bazzite-datstation --version    # the app's and core's version
```

The window opens once: a second launch (the menu entry, the Desktop icon, the Steam shortcut) brings the open
window to the front.

## Files

- `~/.local/share/bazzite-datstation/scores.json`: the quiz scores and trophies.
- `~/.config/bazzite-datstation/bazzite-datstation.ini`: the window size and the music setting.
- Steam's `userdata/<user>/config/shortcuts.vdf` and `grid/`: the non-Steam game and its artwork, only when you
  choose Add to Steam, and removed again with Remove from Steam.

## Privacy

The app collects no personal data and sends none. It has no accounts, no analytics and no crash reporting. The
only network requests it makes are the ones you ask for: loading the PlayStation.Blog feed on the PS News page
(a plain HTTPS request to `blog.playstation.com`, identified as `bazzite-datstation/<version>`), and opening a
PlayStation page or a picture search in your browser when you click a link. Your scores, trophies and settings
stay in the files above, in your home folder, and go with `--uninstall --purge`.

## When something does not work

- **"Could not load announcements":** the board has no network, or the feed did not answer. The page says why;
  **Refresh** tries again.
- **"Blocked unexpected link":** a link in the feed points outside PlayStation's sites, which the app does not
  open.
- **No music:** the music needs an audio output and Qt Multimedia, which the PyQt6 wheel brings. Check that
  **Music on** shows beside the quiz title; the quiz plays the same without it.
- **"The launcher ... does not exist" from Add to Steam:** the app runs from a checkout; run `install.sh` first,
  so Steam has a program to start.
- **"Steam did not close":** Steam was asked to close for the change and did not within 30 seconds; nothing was
  changed. Close Steam yourself and try again.
- **Add to Steam from Game Mode:** the app asks you to switch to Desktop Mode; closing Steam from Game Mode would
  end the session.
- **No window on an X11 session:** PyQt6's X11 plugin needs `libxcb-cursor`; Bazzite's Wayland sessions do not.
  `QT_QPA_PLATFORM=xcb bazzite-datstation` or `=wayland` picks the backend by hand.

## Development

The app follows the suite's [architecture](../development/architecture.md): the package `datstation/` at
the app root (its data in `data/`, the music in `sounds/`), `images/` (the icon),
`tests/`, `install.sh`, `VERSION`, `CHANGELOG`, `LICENSE` and `.gitignore`, on `bc250_core` (the header, the
settings, the Steam shortcuts, the one-instance socket). The quiz engine (`quiz.py`) and the feed reader
(`news.py`) have no Qt in them, so their tests run without a display; the pages are tested offscreen.

```bash
./test.sh                                                  # every test suite of the checkout, offscreen
.venv-linux/bin/python -m pytest apps/datstation/tests   # this app's only
```

**How the data got here.** The questions are the Android app's `questions.dat`, decrypted once and shipped as
plain JSON (`data/questions.json`): the key was in the Android repository, so the encryption protected nothing.
True/false questions whose answer carried its explanation after a colon were split into the answer and an
`explanation` field. The system software versions are the Android app's JSON files, unchanged; the music its
`sea_breeze.ogg`.

**Security around the build.**

- The app runs as your own user: `install.sh` refuses to run with sudo and installs only into your home folder.
  Nothing runs as root, nothing is layered, no service is installed.
- The only dependency is PyQt6, pinned to a major version (`PyQt6>=6.11,<7`) and installed from PyPI into the
  app's own venv; the installer upgrades it within that range on every install, so a security fix in PyQt6
  reaches the app with the next `./install.sh`. The [Dependency Checker](package.md) lists the version
  and its known vulnerabilities.
- `bc250_core` ships with the app, so it runs on the core it was tested with; the launcher puts the app folder
  first on Python's path, so a module in the folder you start it from cannot shadow the app's own.
- The feed is read with Python's standard library over HTTPS and parsed with `xml.etree` (no external entities
  are resolved); titles are reduced to plain text before they are shown. Links are opened only when they are
  HTTPS on a PlayStation host, through `xdg-open`.
- Steam's shortcut file is written atomically (a temporary file, then a rename), with Steam closed, and only the
  app's own entry is added or removed; the other shortcuts stay as they are.
- A release of the suite comes with `SHA256SUMS`; check the download before you install it, as the suite's
  [security page](../SECURITY.md) describes. CI runs the tests, shellcheck and the installer end to end on every
  push.

## License

GPL-3.0-or-later. `bc250_core`'s bundled Inter font is under the SIL Open Font License.
