<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md (BC250 Bazzite Suite)

The rules of the **BC250 Bazzite Suite**, the suite in this folder of Nexus. The root's [CLAUDE.md](../CLAUDE.md)
holds what is Nexus's (git, releases, the CHANGELOG format and kinds, line endings, the checks) and applies here
too. Status and plans: [MIGRATION.md](../MIGRATION.md). Paths below are written from this folder unless they start
with `../`.

## What this is

The **BC250 Bazzite Suite** (exactly that name): tools for the AMD BC-250 on Bazzite. Its paths and tag names
(`<app>-v<x.y.z>`, `portal-v<x.y.z>`), the app ids, the launchers, the state folder on the board
(`~/.local/share/bc250-bazzite-suite/`) and the wiki's address (robertotorino.github.io/nexus/bc250-bazzite-suite/)
did not change when the suite moved into `bc250-bazzite/` (26-10-2026): nothing installed notices the move. A
**portal** installs and starts the apps listed in its manifest. **check** (BC-250 Bazzite Test) is always installed
and always listed first; every other listed app is an optional tile. Standalone apps may live under `apps/` without
appearing in the portal.

- `apps/<name>/`: check, gpu, upscaler, compute, cores, oc, acpi,
  overlay, ips35, hdcam, hdcontrol, bios, ace, mesh, vram, fan, wdriver, cec, sftp, consoles, clb, shadps4, rpcs3,
  ppsspp, pcsx2, vita3k, xenia, decky, mtool, package, ncgui, datstation. Each has its
  own VERSION, CHANGELOG, LICENSE (acpi is MIT; consoles is AGPL-3.0, its protocol code ported from
  chiaki-ng: those files AGPL-3.0-only, its own AGPL-3.0-or-later; ncgui is GPL-2.0-only, a port of NetcatGUI; clb
  (Console LinkB, Xbox) is GPL-3.0-or-later with protocol code ported from Greenlight and xal-node, MIT, whose notice
  its README keeps; the rest GPL-3.0-or-later), .gitignore. Every app
  has a `category` in `portal/apps.toml`, the same as its icon's in `icons/categories.toml` (sustainable, graphics,
  gaming, utilities, development): the portal shows a tab per category, with the notice of updates above the tabs
  (owner, 18-10-2026) and check as the first tile on Sustainable (owner, 20-10-2026). Media Tool, the Dependency
  Checker and Bazzite NetcatGUI are development apps.
  Nexus Releases (the release front end, `../dev/releases/`, a Nexus app) has `.standalone` and `.checkout-only`:
  it runs from the checkout, is never released, and is listed as `[checkout.releases]` with `nexus = true` and
  `folder`, on the Development tab: a portal from a release finds the checkout on the machine (it asks only when
  there is none) and remembers it, the released apps still come from their releases. The checkout the portal
  records is the repository (Nexus); the suite's folder in it is `bc250-bazzite/` (`SUITE_DIR` in the portal),
  where a `[checkout.<key>]` folder is relative to (a Nexus app's to the repository). Install every app through
  the portal, so what is installed stays in step. BC-250 Installer Tests (`tools/installer-tests/gui`) is
  checkout-only the same way: `.checkout-only` and `[checkout.installer-tests]` with `folder`.
- `../core/bc250_core/`: shared Python code, at the root of the repository, every suite's. It is **bundled per
  app** at release time (`../tools/stage_app.py`), so each app runs on the core it was tested with; the shared venv
  `~/.local/share/bc250-bazzite-suite/venv` holds only PyQt6 and pygame-ce (the portal's controller reader). In a
  checkout an app's `install.sh` and its tests find core at `../../../core` from the app folder.
- `portal/`: the portal, `apps.toml` (one pinned release per app) and its `install.sh`. The repository root keeps a
  copy of `apps.toml` at `../portal/apps.toml` for the portals installed before the move, which read it at a tag for
  their update notice; `tools/check_manifest.py` keeps it identical. The owner removes the copy once the first
  portal release after the move has been out for a while.
- `tools/`: the suite's tools: `pin_app.py`, `check_manifest.py`, `check-release.sh` (the board checks of a
  portal release, run from Nexus Releases' Test on this board), `sync_icons.py`, `portal_screenshot.py`,
  `portal_tour.py`, `record-tour.sh`, `record-app-tour.sh`, `make_portal_sounds.py`, `sounds/`,
  `check_upstream.py`, `mkdocs/` (the wiki's hooks and overrides), their tests in `tools/tests/`, and
  `tools/installer-tests/` (installers on Linux with fakeroot shims). The Nexus tools (release and CI, the design
  panel) are in `../tools/`.
- `docs/` and `mkdocs.yml`: the wiki; `icons/`: the category icons; `install.sh`: the portal's installer from a
  checkout.

## Rules from the owner

- **Warn before board changes.** Apps that change how the board runs (CU/core unlocks, GPU governor, GPU
  overclocking, ACPI override, the patched RADV of ace, the DirectMesh RADV of mesh, the VRAM split of vram, the
  thermal guard of fan, the kernel module of wdriver) are marked `changes_board` and the portal asks first. Frame it
  as standard caution: the apps are software-only and reversible, not "risky".
- **Advice, not reboots.** No app reboots, powers off or logs out the board; when one is needed, the app says so
  (and which command does it). The exception, by design (owner, 15-10-2026): CU Bisect and Cores Bisect, whose
  rounds each need a fresh boot (they ask, or reboot by themselves with `--auto`), and Cores Unlock's boot service,
  which reboots warm once after a cold boot so the cores come up. A second exception (owner, 16-10-2026): the
  thermal guard shuts the board down cleanly at a critical temperature, to protect the hardware; the limits are
  the owner's. A new reboot anywhere else is the owner's decision.
- **The current releases are the baseline.** They were tested extensively on two boards. Moving code must not
  change behavior; a finding in existing code is "a code path to check", not a known failure. Prove "unchanged"
  (diffs, pixel comparisons, the installer tests) rather than assume it.
- **Not limited to the owner's setup.** The owner's board, TV, cable and settings are one case, not the target:
  apps read what the hardware reports and offer every option it supports (a CEC 2.0 TV, another display mode,
  a second adapter), and say so where an option does not apply, rather than leaving out what the owner's setup
  lacks. Recorded data from the owner's board makes good test fixtures; tests also cover other setups.
- **Consistent architecture.** Every app is built the same way, so one that works is the pattern for the next:
  - Layout: `apps/<name>/` holds its Python package(s) directly (`<package>/__main__.py`, no wrapper folder),
    `<name>` a short name and `<package>` the app's name without its BC-250 or Bazzite prefix
    (`apps/ace/ace_queues/`, `apps/ncgui/netcat_gui/`; owner, 17-10-2026, the apps move to it one at a time,
    MIGRATION.md says which did; a renamed app's old key goes in `RENAMED` in the portal's manifest.py),
    `images/`, `tests/`, `install.sh` and the four files; data the package reads (a catalog, tables) sits in
    the package or beside it in the app folder. `../tools/tests/test_layout.py` checks the layout of every suite.
    An app's icons are copies of its category's icon: `icons/categories.toml` assigns them, `tools/sync_icons.py`
    writes them.
  - Code: shared code comes from `bc250_core` (bundled per app); the installer writes a launcher in
    `~/.local/bin` whose exec line names the app's python, a menu entry and an optional Desktop icon; every app has
    its installer test (see Checks in the root's CLAUDE.md).
  - Window: the first line is the app's icon at 96 px on the left, spanning the title (with the version) and a
    second line below it (status boxes or the app's main controls).
  A new app copies the structure of an existing one; any deviation is the owner's decision. The manual's
  [Architecture and consistency](docs/development/architecture.md) describes it all, with the steps for a new app.
- **The Bazzite design** (owner, 25-10-2026: a design per system): this suite keeps the Bazzite design (purple, the
  apps' theme and the wiki's). Never carry another system's design over to it, nor its design to another system.
- **Scope is the suite, not Bazzite.** We answer for the portal and its apps, not for Bazzite itself. A system-wide
  Bazzite package is in scope only where one of our apps uses it (the Dependency Checker lists it then); its
  updates and security fixes are Bazzite's. Our own code, and the Python packages in our apps' environments, are
  ours. One exception (owner, 15-10-2026): the Dependency Checker shows Bazzite's update state (the running image,
  an update waiting for a reboot, uupd's last run) and reminds weekly when one waits; it only reads it, and
  updating stays Bazzite's.
- **chiaki-ng is named only where licensing needs it:** Console Link's LICENSE, the License sections of its README
  and manual chapter, the suite's license overview (README, docs/index.md) and this file. Everywhere else (code,
  comments, tests, vectors, log messages, the manual, CHANGELOGs, MIGRATION.md) it is "the reference" (the reference
  implementation); user-facing text does not mention it at all.
- **KROU4's PS5CameraDriver is never named** (owner, 23-10-2026), only in this file: not in code, comments, tests,
  the wiki, CHANGELOGs or MIGRATION.md. Where its tried firmware patch matters, it is "another project's firmware
  patch".

## Checks of the suite

The root's CLAUDE.md lists every check as CI runs it. Those of this suite alone, from the repository root:

```bash
python3 bc250-bazzite/tools/check_manifest.py --base origin/main   # portal/apps.toml rules, the bump since the last portal release
for t in bc250-bazzite/tools/installer-tests/*.sh; do [ "${t##*/}" = shims.sh ] || bash "$t"; done   # every installer test
mkdocs build --strict -f bc250-bazzite/mkdocs.yml      # the wiki, from the venv
```

Every app (and every `portal/apps.toml` entry) has an installer test, `tools/installer-tests/<name>.sh`, and CI runs
each one in its own step; a new app adds both (`tools/tests/test_installer_tests.py` checks it). BC-250 Installer
Tests lists the scripts in that folder by itself.

## Releases

Everything about releases is the owner's (the root's CLAUDE.md). Decky Loader is pinned in decky (`loader.py`);
`tools/check_upstream.py`, weekly in `../.github/workflows/upstream.yml`, says when Decky moved past the pin (a new
release, a replaced asset, a changed service unit). Moving the pin is code Claude may prepare (with its CHANGELOG
entry); the board test and the decky release are the owner's, and the handover says so.

The manual (`docs/`, built with MkDocs) is called **the wiki** in user-facing text: the header link and the Home
page's footer say Wiki.
