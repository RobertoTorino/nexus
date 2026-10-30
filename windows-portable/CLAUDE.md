<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md (Windows Portable Suite)

The rules of the **Windows Portable Suite**, the suite in this folder of Nexus. The root's [CLAUDE.md](../CLAUDE.md)
holds what is Nexus's (git, releases, the CHANGELOG format and kinds, line endings, the checks) and applies here
too. Status and plans: [MIGRATION.md](../MIGRATION.md). Paths below are written from this folder unless they start
with `../`.

## What this is

The **Windows Portable Suite** (exactly that name): tools for Windows 10/11 on portable gaming devices, any Windows
handheld, first the owner's ASUS ROG Xbox Ally X. Its `SYSTEM` is `windows` and its `TAG_PREFIX` `wp-` (owner,
26-10-2026): tags are `wp-<app>-v<x.y.z>` and `wp-portal-v<x.y.z>`. A **portal** installs and starts the apps listed
in its manifest. **test** (Windows Portable Test) is always installed and always listed first; every other listed
app is an optional tile. The wiki is at robertotorino.github.io/nexus/windows-portable-suite/.

- `apps/<name>/`: one folder per app, each with its own VERSION, CHANGELOG, LICENSE and .gitignore. Every app has a
  `category` in `portal/apps.toml`: sustainable, graphics, gaming or utilities (owner, 27-10-2026: the BC250
  suite's without development), the portal's tab for it. No `[checkout.*]` apps and no Development tab: the portal
  lists only released apps.
- `portal/`: the portal (`portable_portal/`), `apps.toml` (one pinned release per app), its `install.ps1` and
  `run.ps1`, its images and the intro's sound.
- `tools/`: `build_release.py` (an app's or the portal's release zip, on Windows), `check_manifest.py`,
  `suite_release.py` and `publish_release.sh` (the release workflow's plan, pin and publish steps),
  `check-release.ps1` (the release checks on the handheld, from the Nexus Release Tool's test buttons; `draft`: the
  device test of a Nexus release), `mkdocs/`
  (the wiki's overrides), their tests in `tools/tests/`, and `tools/installer-tests/<name>.ps1` (an installer test
  per app and per manifest entry, and the Nexus Release Tool's `nrt.ps1`).
- `docs/` and `mkdocs.yml`: the wiki; `icons/`: the suite's pictures and the category icons
  (`icons/<category>/<category>-<size>.png`), the PNG sources of their copies: every optional app takes its
  category's icon (`../tools/make_icons.py` writes the copies, `../ICONS.md` lists them).
- `../core/bc250_core/`: shared Python code, every suite's, **bundled per app** in its release. The portable window
  (`portable.py`: `PortableWindow`, `Card`, `Pane`, `Pill`, `InfoPill`, `Legend`, `PortableHeader`), the
  controller (`gamepad.py`), the battery (`power.py`) and the Windows folders and shortcuts (`platform.py`) are
  this suite's base.

## Rules from the owner

- **Each suite stands apart** (owner, 27-10-2026): a change here never edits the BC250 suite's folder, its CI or its
  release workflow, and a change both suites want is two changes, one per suite, each with its own release. This
  suite's CI is `../.github/workflows/ci-windows-portable.yml`, its releases `release-windows-portable.yml` (never
  GitHub's Latest: that is the Nexus index), its weekly emulator check `upstream-windows-portable.yml`.
- **An emulator moves only with its app** (owner, 29-10-2026: a new emulator release can break things): each app
  pins one tested release in its `emulator.py` (`REPO`, `VERSION`, `ASSET`, `SHA256`), and a newer one reaches the
  device only with a new release of the app, tried first. Every Monday `tools/check_upstream.py` compares each pin
  with the newest stable release and with the file GitHub publishes, and keeps the "Upstream review (Windows
  Portable Suite)" issue up to date; a new emulator app's `emulator.py` with those constants is checked by itself.
- **Worked on and tested on Windows** (owner, 26-10-2026): the suite's tests, installer tests and release builds
  run on Windows (`./test.sh` runs them only there, unless `NEXUS_SYSTEM=windows`).
- **A design of its own, with the weight on UX and UI** (owner, 25-10-2026): the portable design (direction D, B's
  amber on C's cards; `../DESIGN.md`), never the Bazzite design. A small screen held in the hands, touch and a
  controller, often without a keyboard:
  - Every action is reachable with the controller and by touch: the d-pad moves an amber focus between cards and
    rows, A acts, B goes back (a pane to its card, a page to where it came from; nothing on a card; in a pane
    the d-pad stays in it, never jumping to the cards at a list's end: core's `move_focus()`), View (⧉)
    exits the app and Menu (☰) opens the information of the pane that shows (owner, 29-10-2026: "Close" on B was
    not clear; core's `PortableWindow`, the legend ending with `common_items()`: ☰ Info, B Back, ⧉ Exit app). **The
    legend at the bottom is the row of actions** (owner, 29-10-2026:
    "use that bottom row for actions"; then "one way everywhere"): **every action is a button and a legend entry,
    A too (A Install, A Read, A Steam mark, A View log), and a pane holds no pill** (no Install, Remove, Save or
    Open the log pill); a tap on the entry does the same (core's `Legend`, through `PortableWindow.act()`, A
    beside a card or row through `bind("accept")`). An action without a button of its own takes a free one on its
    pane (Remove PCSX2 on RB, Remove BIOS on LB, Remove PPSSPP on X). A tap on a pane may do its A where that is
    safe (the Log pane shows the log). Pills stay only inside a popup, as its choices (the stick lights). The
    information icon is touch only: the d-pad never lands on it, Menu (☰) opens it.
  - No dialogs: an action that needs care asks for a second press within five seconds (Remove; View while a
    download or an install runs), and the legend's entry and the status line say so meanwhile. **Nothing is grayed
    out** (owner, 29-10-2026): pressed when its action cannot run now, a button says why on the pane's status
    line. Never `setEnabled(False)` on a `Pill` or a row.
  - Windows' own windows are not used: they cannot be used with the controller (owner, 29-10-2026: a folder could
    not be chosen). A folder or a file is chosen in core's browser (`browse.Browser`: the places, then folders,
    A opens, B goes up, X adds the folder, A on a file picks it); a long text (the log) is read in a `TextView` in
    the pane, the d-pad scrolling it, never in Notepad.
  - The emulator apps never start a game (owner, 29-10-2026): the games are played from Steam, and A on a game is
    its Steam mark.
  - The window fits the Ally's screen: 1280 x 720 logical pixels at 150 %, the size every page is laid out for
    (`portable.px()` scales it to a larger screen). Text that does not fit goes behind an information icon
    (`InfoPill`, at the top right of its pane) that shows it over the window (owner, 28-10-2026). Where space is
    short, an icon at the pane's top right opens a popup with the rest (text or controls), owner 29-10-2026.
  - The wallpaper is the suite's (owner, 29-10-2026): every window shows it behind see-through cards (core's
    `PortableWindow`), on or off for every app at once on the portal's Settings page
    (`%APPDATA%\windows-portable-suite\suite.ini`).
  - Nothing runs before it is asked for: a card that reads the device reads on A (owner, 28-10-2026).
  - **No user name on the screen or in a log** (owner, 29-10-2026: the privacy rule): a path is shown through core's
    `platform.private()` (`%LOCALAPPDATA%\...`, `%USERPROFILE%\...`), and every app logs with
    `applog.setup(..., private=True)`.
  - The header's status line: the battery, the date and the time, `82% | Wednesday 28/10/2026 | 17:04` (owner,
    28-10-2026: no space before %); Windows Portable Test shows the date and the time, and under them
    the temperatures, the power draw, the screen's refresh rate and the battery, `CPU 47° GPU 45° | 18 W | 120 Hz |
    82%` (owner, 29-10-2026). No icon in the
    test app's header (the screen is too small for it).
- **Not limited to the owner's handheld.** The Ally X is one case, not the target: an app reads what Windows
  reports, works on another Windows handheld, and says so where something does not apply (no AMD driver, no Wi-Fi,
  no back buttons).
- **For your own user, never as administrator.** The installers refuse an administrator's window; everything goes
  in `%LOCALAPPDATA%\windows-portable-suite\` (programs, logs, reports, the portal's state) and
  `%APPDATA%\windows-portable-suite\` (one `.ini` per app); nothing in the registry (tests must not write to it
  either). An app the portal installs gets a Start-menu entry in the Windows Portable Suite folder and no Desktop
  shortcut (owner, 28-10-2026); one installed by hand gets both.
- **Personal data is never read out**: no serial numbers, MAC addresses, network names (SSID) or access point
  addresses, no paired Bluetooth devices (they carry their owner's name).
- **Unsigned for now** (code signing and an MSIX for Xbox mode's home app are on hold, MIGRATION.md).

## How an app is built

Every app is built the same way; Windows Portable Test is the model:

- `apps/<name>/<package>/` (`__init__.py` with `APP_NAME`, `APP_ID` = `windows-portable-<name>`, `EXE_NAME`, `SUITE`,
  `__version__` and an `AppInfo` with `settings_org=SUITE, settings_ini=True`; `__main__.py`; `main_window.py` on
  `PortableWindow`), `images/` (`<app id>.webp` and `-128.png`), `tests/` (with a conftest that keeps settings out of
  the registry), `install.ps1`, `run.ps1` (from the checkout, full screen or `--windowed`), `requirements.txt`,
  `requirements-dev.txt`, README.md and the four files.
- Its chapter in the wiki is `docs/apps/<name>.md` with a nav line in `mkdocs.yml`; the release carries it as
  MANUAL.md.
- Its release is `wp-<name>-v<x.y.z>.zip` from `tools/build_release.py`: `program/` (PyInstaller one-folder,
  `<EXE_NAME>.exe` beside `_internal/`), `install.ps1`, LICENSE, THIRD-PARTY-NOTICES.txt and MANUAL.md, with
  SHA256SUMS and notes.md.
- What Windows reports is read through its own APIs (ctypes) or one CIM or PowerShell query that returns JSON, never
  the text of a tool such as netsh or powercfg, which is in Windows' language. Slow reads run off the window's
  thread.
- A new app adds its `portal/apps.toml` entry, its installer test `tools/installer-tests/<name>.ps1`, its entry
  in the suite's CI's `installers` matrix (a job per app: the installer test, the release built and installed) and
  its folder in the CI's pytest matrix (`../tools/tests/test_layout.py` and `tools/tests/` check them);
  `../tools/new_app.py --suite windows-portable` does all of it. The suite's CI runs only for a push that changes
  the suite, core, `tools/` or `dev/nrt/` (owner, 29-10-2026).

## Checks of the suite

From PowerShell at the repository root, as the root's CLAUDE.md lists them:

```powershell
.venv-windows\Scripts\python.exe tools\check_versions.py --suite windows-portable
.venv-windows\Scripts\python.exe windows-portable\tools\check_manifest.py --base origin/main
Get-ChildItem windows-portable\tools\installer-tests\*.ps1 | ForEach-Object { powershell -NoProfile -ExecutionPolicy Bypass -File $_.FullName }
.venv-windows\Scripts\python.exe windows-portable\tools\build_release.py wp-test-v<VERSION> <folder>
powershell -NoProfile -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\test.ps1 -Release <folder>\wp-test-v<VERSION>.zip
.venv-windows\Scripts\mkdocs.exe build --strict -f windows-portable\mkdocs.yml   # then remove windows-portable\site
```

`./test.sh` (Git Bash) runs every test suite of this system, this suite's among them. A window's layout is checked
at 1280 x 720 offscreen (its minimum height at most 720), and looked at on the Ally by the owner.

## Releases

Everything about releases is the owner's (the root's CLAUDE.md): the version bumps, the tags (`wp-` first), the
release zips and the pins in `portal/apps.toml`. When finished work needs a release, the handover says which app
and why.

The manual (`docs/`, built with MkDocs) is called **the wiki** in user-facing text.
