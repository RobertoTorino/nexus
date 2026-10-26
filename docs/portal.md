<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC250 Bazzite Suite](assets/portal/bc250-bazzite-suite.webp){ .app-logo }

# Portal

The BC250 Bazzite Suite's front door: one window that installs, opens, updates and removes the suite's apps.
The [Portal Tour](portal-tour.md) shows it in a two-minute video.
**The header**: the portal's icon (click it to open this wiki), its name and version, where the apps install from,
and nine pills of the same width: **Refresh** (look again at which apps are installed), **Installed apps**,
**Install all updates**, **Icons on Desktop**, **Sound**, **Theme switcher**, **Wallpaper**, **Suite mode** and
**Sys info**, each described below. The pills are in one row when the window is wide enough; on a narrower
window, such as the 1280 px screen of a Steam Deck or an ROG Xbox Ally X, they wrap into two rows of about equal
length.

**Bazzite Test** is always installed with the portal; every other app is optional. The notice of updates is at the
top, on every tab. Below it is a tab for each [category](apps/categories.md): Sustainable, Graphics, Gaming, Utilities
and Development. Each app is a tile on its category's tab, left to right in the order of `apps.toml` and as many to a
row as the window fits; Bazzite Test is always the first tile on Sustainable:

- **The name**, without the suite's "BC-250" prefix.
- **The icon.** Click it to open the app; an app with two windows (CU Bisect, Cores Bisect) asks which one. The
  icon is gray while the app is not installed, and dims a little under the mouse while it opens the app. Hover over
  it to see what the app does, its state and the release this portal pins.
- **A red dot** in the icon: an update is available.
- **A red circular arrow** in the icon: reinstall the app. It is installed, but not by this portal (by hand, or
  under an earlier name of the app), so the portal does not know its version. Its red button reinstalls the version
  this portal pins.
- **changes the board**, in orange under the icon, for apps that change how the board runs.
- **App not available**, in red under the icon: the release of this app was withdrawn because of a problem
  (privacy, security or another reason; hover over it to read which). It cannot be installed or opened. When it is
  installed, the portal says so at start and removes it with the app's own uninstaller in a terminal. If that
  fails, the Uninstall button stays, to try again.
- **The buttons beside the icon:** Install (an arrow into a tray) and Uninstall (a bin). For an installed app,
  Install reinstalls it, or updates it when the arrow is red; hover over it to see the version it installs. Bazzite
  Test has only Install, which reinstalls it: it is removed together with the portal.

**The tabs.** Each tab says at its top what its apps are for; [The apps](apps/index.md) lists them by tab. The portal
always opens on the first tab, Sustainable.

**Development**, the last tab, holds the tools for working on the suite:
[Media Tool](other-tools/media-tool.md), [Dependency Checker](apps/package.md),
[Bazzite NetcatGUI](apps/ncgui.md), the
release front end
[BC250 Suite Releases](#the-release-front-end) and BC-250 Installer Tests (`tools/installer-tests/gui`), a window
that runs the installer tests one at a time. You do not need them to use
the board. The last two run from a checkout of the repository and have no release. A portal installed from a
release installs them too, from the checkout it finds on this machine: the one an installed tool of the checkout
runs from, or the first in your home folder, up to three folders deep (`~/IdeaProjects/bc250-bazzite-suite`, for
example). Only when it finds none does it ask for the folder. It remembers the checkout. The other apps still install from their releases. A portal installed from the
checkout uses its own checkout.

- `apps/` may also contain standalone tools (with a `.standalone` marker) that do not appear in `apps.toml`
  and that the portal does not install or open.
- Install, update and uninstall run **the app's own installer** in a terminal window, because installers may ask
  for the sudo password and print what they do. The portal watches for the result and refreshes. A terminal whose
  installer ended well closes by itself; one that failed stays open with what happened until you press Enter.
- Apps that change how the board runs (CU/core unlocks, the GPU governor, GPU overclocking, the ACPI override, the VRAM
  split, a patched GPU driver) are marked **changes the board**. The portal warns before installing or opening them.
- Each portal release pins one tested release of every app in [`apps.toml`](https://github.com/RobertoTorino/nexus/blob/main/portal/apps.toml). The portal downloads
  exactly those tarballs from the suite's GitHub releases and checks each against the SHA-256 pinned there, or
  against the release's `SHA256SUMS` until one is pinned. Then it unpacks the tarball without ever writing
  outside its folder.
- **Updates:** a red dot marks every app whose installed version differs from the one this portal pins; its red
  Install button installs the pinned version. The notice beside Bazzite Test counts them and the apps that need a
  reinstall, and names each one with its tab and versions. Click a name to go to its tile. A tab with such an app
  shows their number in red after its name, so none goes unseen on a tab that is not open. Newer app versions come with a newer portal
  release: at start the portal looks for one on GitHub and, when there is one, shows a red button that opens its
  release page. The button names what that release brings, for example **Portal 0.9.1: updates ACE Queues and
  Memory Manager**, and its tooltip lists each app with its old and new version. After the portal update, the
  installed apps among them show the red dot. When the new pins cannot be read (offline, for example), the button
  says **Portal x.y.z available**.
- **Outside the suite**, in orange below the updates: a newer release of a program that an installed app installs
  in its newest version, so the app can install it now, for example **BC-250 Upscaler Manager (Graphics): HelixSR 1.9.3
  is out**, with what to do in the app. Today this is HelixSR (the BC-250 Upscaler Manager). The portal shows what
  the app found the last time it looked, so open
  the app now and then; when you come back to the portal, the notice follows. Programs an app pins (Decky Loader,
  shadPS4, PPSSPP, RPCS3, Vita3K, PCSX2's stable release, Xenia, DirectMesh) are not listed: a newer one
  comes with a new version of the app, as an update above.
- **Restart: portal x.y.z is installed:** a portal window that is open while you install a newer portal keeps
  running the old one, with its old app versions, and starting the portal again only brings that window to the
  front. When you come back to the window, it sees the newer portal and shows this red button: click it to restart
  into the new portal, which then shows the red dot on the apps it updates. While an app installs or uninstalls,
  the button waits for it to end.
- **Installed apps**, a pill at the top: how many of the portal's apps are installed, for example **12/27**. An app
  that is not available any more is not counted.
- **Install all updates**, a pill at the top: the number of apps the notice names, updates and reinstalls. Click it
  to install them all, one after the other. The portal asks once, with the list, and warns when one of them changes
  the board. Each app's installer runs in its own terminal, as a single install does. When one asks for your
  password, type it in that terminal: the next one waits until it has ended. While it runs, the pill shows which one
  of how many it is at, for example **2/5**. An install that fails does not stop the others; at the end the portal
  names those that failed, and the Install button on their tiles tries again. **Refresh**, while it waits for a
  terminal that was closed, can stop waiting, and then stops the rest too.
- **Install all apps**, the last tab: a button that looks like a tab. It installs every app of the open category
  that is not installed yet, one after the other, the same way as **Install all updates**: one question with the
  list and the board warning, each installer in its own terminal, the tab showing which one of how many. It is
  disabled once every app of the category is installed, and on **Development**: those apps are tools for working on
  the suite, installed from their tiles. A portal installed for the first time fills a category with one click.
- **Icons on Desktop**, a pill at the top (Yes or No; click it to switch): on, every installed app has an icon on the Desktop; off, only the
  portal's icon is there and you start the apps from the portal. The apps stay in the app menu either way, so KDE's
  search and Steam's **Add a Non-Steam Game** still find them. The first time the portal starts with app icons on
  the Desktop, it asks whether to keep them. While the switch is off, the portal removes the icons the apps'
  installers put there, at start and after each install. It only touches the icons of the suite's apps, never its
  own or anything else on the Desktop.
- **Sound**, a pill at the top (Yes or No; click it to switch): a short swoosh plays when the portal opens, and
  [Suite Big Picture Mode](#suite-big-picture-mode) has its own sound when it opens. No switches all of them off. The swoosh plays again
  when you switch back from Suite Big Picture Mode to Suite Desktop Mode.
  The portal remembers the choice. When the board has no audio output, the pill says No and is disabled, and the
  portal stays silent.
- **Theme switcher**, a pill at the top showing the theme; click it for the next one: the look of every app in the
  suite. **Gunmetal** (dark, cool blue-gray, the default), **Silver** (light) or **Warm** (dark warm gray with a
  bronze accent). It is one choice for all the apps, kept in `~/.config/bc250-bazzite-suite/theme`; each app takes
  it the next time it starts, the portal too.
- **Wallpaper**, a pill at the top: a picture behind the portal, none until you choose one. Click the pill, then
  **Choose a picture…** for your own (**Custom**), **Example wallpaper** to see how one looks with the picture that
  comes with the portal (**Example**), or **No wallpaper** for none. Your picture must be a PNG, JPEG or WebP of at least 1920 x 1080 pixels, in 16:9 (1920 x
  1080, 2560 x 1440, 3840 x 2160); the portal refuses another and says why. It fills the window, under a veil of the
  theme's color so the text stays readable. **Transparency**, a slider in the same menu, sets that veil from 0 to
  90 % (60 % at first): move it up for a dark or busy picture, so the icons stand out, down to see more of the
  picture. The window changes while you move it, and the portal remembers it. The portal keeps a copy in
  `~/.local/share/bc250-bazzite-suite/portal/`, so the original may be moved or deleted; the portal's `--purge`
  removes it. The menu also lists the last 10 wallpapers you chose, newest first, under **Used before**: click one to
  use it again. The portal remembers only where each picture was (in `wallpapers.json` in the same folder), so one
  moved or deleted since shows as not found until it is back.
- **Suite mode**, a pill at the top: the portal is in **Suite Desktop Mode** (this window, **Desktop**) or in
  **Suite Big Picture Mode** (**Big Picture**). Click it, or press **F11**, to switch to the other one. The portal
  remembers the last mode and opens in it.
- **Sys info**, a pill at the top: a small window with what the system reports about the board: the board, the BIOS
  (with UEFI and Secure Boot), the CPU (model, cores and threads online, top clock, microcode), each GPU (name,
  driver, VRAM, shared memory, clock levels, VBIOS, PCIe link), the memory, the drives with the free space in your
  home folder, the displays (each output, the monitor's name and its preferred mode), the sound cards, the network
  adapters and Bluetooth controllers (driver and link), the USB devices, the input devices (keyboards, mice and
  controllers, each with the bus it is on: USB, Bluetooth, PS/2), the sensors (temperatures, fan speeds and
  the GPU's power at that moment) and the OS (version, Bazzite image, kernel, desktop). It is read each time the
  window opens; what a system does not report is left out. **Copy** puts it all on the clipboard as text, for an
  issue or a forum post. It holds nothing personal: no host or user name, no serial numbers, no MAC or IP
  addresses.
- The **Dependency Checker** is a separate app in `apps/`. It lists declared runtime Python packages and
  app-specific external tools, plus the apps and features that use them. It compares Python package versions with
  PyPI and checks whether external tools are available; tool links open the relevant app guide. Some apps use
  separate virtual environments. The checker does not install or update anything.

## Install

From the [latest portal release](https://github.com/RobertoTorino/nexus/releases/latest), download
`portal-v<version>.tar.gz` and `SHA256SUMS`, then:

```shell
sha256sum --check --ignore-missing SHA256SUMS
tar -xzf portal-v*.tar.gz
cd portal-v*/
./install.sh                 # as your own user; asks for the sudo password only for the copies to /opt
```

What it installs:

| What | Where | Why there |
|---|---|---|
| The portal, its `apps.toml` and the `bc250_core` it was tested with | `/opt/bc250-bazzite-suite-v<version>`, root-owned, with `/opt/bc250-bazzite-suite` pointing at it | Same as bazzite-test's engine: code that starts root-run installers is not writable by a normal user |
| BC-250 Bazzite Test (bundled in the portal release) | `/opt/bc250-bazzite-test`, through its own installer | Its test engine runs as root and must be root-owned |
| The suite's shared venv with PyQt6 | `~/.local/share/bc250-bazzite-suite/venv` | One copy of the ~100 MB of Qt for all suite apps; removed with the last app that uses it (`venv-users/`) |
| What the portal installed, and the release each app was installed from | `~/.local/share/bc250-bazzite-suite/portal/` | So each app's matching uninstaller is at hand; an update removes the previous release |
| What the apps found outside the suite, one file per app | `~/.local/share/bc250-bazzite-suite/upstream/` | For **Outside the suite** in the notice; written by the apps, read by the portal |
| Launcher, menu entry, Desktop icon | `~/.local/bin/bc250-bazzite-suite`, `~/.local/share/applications/`, the Desktop | The portal's icon is the one way in; the apps' own icons are optional (**Icons on Desktop**) |

Uninstall: `/opt/bc250-bazzite-suite/install.sh --uninstall`. This removes the portal and Bazzite Test and
keeps settings; add `--purge` to remove those too. First it asks about each other suite app that is installed:
`y` uninstalls it, `s` skips it (it stays installed), `c` cancels the whole uninstall before anything is removed.
Those apps keep their own settings, also with `--purge`. Of the portal's own records, only those of the apps you
kept stay, with the release each one's uninstaller needs; with no app left, that folder goes too.

### Suite Big Picture Mode

For a TV and a controller, as Steam has its Big Picture. The portal goes fullscreen and shows the apps as large
icons with large type: the category names across the top, the apps of the open category below, and what the keys do
at the bottom. It opens with a short animated intro, about three seconds, with its own sound; press any key, click or
press any button on the controller to skip it. The header has the same pills as Suite Desktop Mode, under the title (the mode pill reads **BPM mode** here; click
it to go back to Suite Desktop Mode), and, in a portal that runs from a checkout, the orange local-build banner. Press
up on the top row of icons to reach the pills, and A or Enter to press one. The wallpaper and its transparency are the
same. The line under the title says in a few words what the open category is
for. The icons are drawn from a 512 px picture, so they stay sharp on a 4K screen.

| Keyboard | Controller | Does |
|---|---|---|
| Arrow keys | D-pad or left stick | Move between the icons |
| Enter | A | Open the app; an app with two windows asks which one |
| Page Up, Page Down | LB, RB | The category before and after |
| F11 | Y or Start | Back to Suite Desktop Mode |
| Escape | B | Back, in a menu or a question |

An app that is not installed is gray. Installing runs the app's installer in a terminal, so the portal asks, and
then goes back to Suite Desktop Mode to do it. A red dot or a red circular arrow marks an update or a reinstall as in
Suite Desktop Mode; to update, switch back to it.

**Handhelds.** Suite Big Picture Mode is made for the Steam Deck (1280 x 800) and the ROG Xbox Ally X (1920 x 1080,
shown at 1280 x 720 with the desktop's scaling): below 1000 px of height the icons, the type and the header are
drawn smaller, down to about two thirds, so two rows of icons and the bar of keys fit on the screen. You can also
swipe a page with a finger on the touch screen. The built-in controls are controllers like any other. Where Steam
Input already turns them into keys (the Deck's desktop layout does: d-pad to the arrow keys, A to Enter, B to
Escape), the keyboard column above applies and works as it is.

The controller is read with [pygame-ce](https://pypi.org/project/pygame-ce/), which the portal's installer adds to
the suite's venv; it takes any controller SDL knows (Xbox, PlayStation, Switch Pro and most others). The portal
listens to the controller only while its own window has the focus, so a game's input never moves it. Without a
controller, the keyboard and the mouse work as always.

### What stays after an uninstall

Uninstalling an app removes the app. Two things stay on purpose: **changes it made to the board**, which you undo
in the app (or with its script) before you uninstall it, and **your settings and results**, which `--purge`
removes.

| App | Still active on the board after its uninstall | Undo it with |
|---|---|---|
| CU Bisect / Unlock | A persisted CU unlock: `bc250-cu-unlock.service` at every boot | **Uninstall** in the Unlock app, or `sudo /usr/local/sbin/bc250-cu-unlock.sh --uninstall`; stock CUs after the next reboot |
| Cores Bisect / Unlock | A persisted core unlock: its boot service | **Uninstall** in the Unlock app, or `sudo /usr/local/sbin/bc250-cores-unlock.sh --uninstall`; stock cores after the next full power off |
| GPU OC Bisect | The installed overclock in the governor's `config.toml` | **Uninstall** in the app, or `bc250-gpu-oc-bisect.sh --uninstall`: restores the backup |
| Persistent ACPI | The ACPI override (`/boot/acpi_override.cpio` and its GRUB line) | **Uninstall** in the app, or `sudo ./bc250-acpi-override.sh --uninstall`; then reboot |
| ACE Queues | An installed patched driver | **Remove** in the app |
| Memory Manager | The VRAM split in CMOS | Set the split back in the app (or **Undo**) and reboot |

The GPU Governor Manager changes nothing of its own: the governor and its `config.toml` belong to the governor
package, which stays installed. HelixSR keeps the imported payload (`~/.local/share/bc250-upscaler`) and
leaves the games it deployed to as they are; **Remove** each deployment in the app first.

Settings live in `~/.config/bc250-*`, results and logs in `~/.local/share/bc250-*` (Bazzite Test also writes its
reports to `~/Desktop/bc250-bazzite-test`). Each app's `install.sh --uninstall --purge` removes them; the
portal's `--purge` does so for the portal and Bazzite Test.

## Development

Run the portal straight from the checkout. Apps then install from the local source, staged exactly as the
release workflow stages them, so everything can be tried before anything is released. It needs PyQt6, so use the
development venv from [Development](development/index.md#development) (Bazzite's own `python3` has no PyQt6):

```shell
cd portal
PYTHONPATH=../core ../.venv-linux/bin/python -m bc250_portal    # --source release: the pinned GitHub releases
```

To install from the checkout, run `./install.sh` in the repository root (or here in `portal/`). It bundles
`../core` and installs `../apps/check`. The installed portal then installs the other apps from the
checkout too, so keep the checkout where it is.

## apps.toml and releases

The comment at the top of [`apps.toml`](https://github.com/RobertoTorino/nexus/blob/main/portal/apps.toml) describes its fields. The rules, checked in CI by
[`tools/check_manifest.py`](https://github.com/RobertoTorino/nexus/blob/main/tools/check_manifest.py):

- **Pinned tags.** Every pinned tag must exist when the portal is released. On `main`, a tag may also be the
  next release, which means its version equals that app's `VERSION`.
- **Version bumps.** A change to `apps.toml` needs a `portal/VERSION` bump at least as large as the largest app
  bump it pins: an app patch release needs at least a portal patch release, an app minor release at least a
  portal minor release, and so on. An added, removed or withdrawn app needs at least a minor portal release.
- **Withdrawn releases.** `withdrawn = "<reason>"` in an app's entry withdraws its pinned release (see
  [Withdrawing a release](#withdrawing-a-release)). Not for Bazzite Test, which is always installed.

Releasing an app and pinning it in the portal:

1. Bump `apps/<app>/VERSION` (and the copies that `tools/check_versions.py` lists), and update its CHANGELOG.
2. Commit and push, then tag with `tools/tag-release.sh <app>-v<x.y.z>` (it waits until CI passed on that
   commit); [`release.yml`](https://github.com/RobertoTorino/nexus/blob/main/.github/workflows/release.yml) builds
   `<tag>.tar.gz` and `SHA256SUMS` with [`tools/build_release.py`](https://github.com/RobertoTorino/nexus/blob/main/tools/build_release.py).
   An app with a Windows executable (SFTP Tools) also gets a Windows job on its tag, which adds
   `<app-id>-<version>-windows.zip` and its `.sha256` to the release; the portal ignores them.
3. `python3 tools/pin_app.py <tag>`: this sets the tag and checksum in `apps.toml`.
4. Bump `portal/VERSION` as `tools/check_manifest.py` asks, and list the app release in the portal CHANGELOG.
5. Once the pinned app releases are tested together on a BC-250 (see
   [Testing a portal release before its tag](#testing-a-portal-release-before-its-tag)), commit steps 3 and 4,
   push, and tag with `tools/tag-release.sh portal-v<x.y.z>`. That release bundles the pinned Bazzite Test release (`check-v…`).

![BC250 Suite Releases](assets/suite/bc250-release-128.png){ .app-logo }

### The release front end

**BC250 Suite Releases** (`apps/suite/`) is a window that makes these file edits for you. It commits, tags and
pushes only when you press its git buttons: after each step it shows the git commands to run. It edits the checkout it lives in, so it is not
in the portal and has no releases of its own. Start it from the repository root:

```bash
tools/release.sh            # or apps/suite/run.sh
tools/release.sh --list     # the same overview in the terminal, with the system python3
```

To start it from the app menu instead, install it once on Linux. Nothing is copied: the entry always starts the app
of the checkout you installed it from.

```bash
apps/suite/install.sh                         # app menu entry and Desktop icon
apps/suite/install.sh --no-desktop-shortcut   # app menu entry only
apps/suite/install.sh --uninstall             # remove them; the checkout stays
```

`tools/release.sh --install` and `--uninstall` do the same. It runs with the checkout's `.venv-linux` (see
[Development](development/index.md)). After moving the checkout, run `install.sh` again. On Windows, run
`tools/release.sh` from Git Bash.

- **1. Release apps:** the **Needs release** column marks in orange every app that ships something new since its last
  tag: a changed file in its folder (tests and `requirements-dev.txt` do not count), in the core it bundles, or in
  its manual chapter, committed or not. Hover it for the files. Step 2 says the same for the portal. Those apps are
  ticked when the window opens; untick what waits (**Tick what needs a release** ticks them all again) and enter the
  versions. The version offered first follows [semantic versioning](development/architecture.md#versions-changelogs-and-releases) from the CHANGELOG
  entries since the last tag (`Breaking.` major, `Added.` minor, `Fixed.` patch); its tooltip says why. A version
  that was never tagged (the first release) can be released as it is. **Apply** writes `VERSION`, every copy `tools/check_versions.py` checks and a
  `Release x.y.z.` CHANGELOG entry with your notes, which become the release notes on GitHub. The release notes
  of an app that bundles the core also name the core version. When `apps.toml`
  pins a tag of that app that was never released, the pin moves to the new version. When `apps.toml` changed since
  the last portal release, for that or another reason (an app added or removed), CI wants a portal bump in the same push:
  Apply makes it too (the lowest portal version CI accepts, with a CHANGELOG entry that lists the changed pins) and
  says so; the portal release itself stays step 2. It runs `tools/check_manifest.py`. Then commit, push, and push the app tags (steps 1 and 2 above),
  with **git add**, **git commit**, **git push** and **git tag** at the bottom: on Linux the push runs
  `tools/ci-local.sh` first and pushes only when CI's jobs pass.
- **2. Pin and release Portal:** once GitHub has built the app releases, **Pin** reads each release's `SHA256SUMS` and
  pins its tag and checksum in `apps.toml` (step 3). The window shows the lowest portal version CI accepts against
  the last portal release (its tag; the last push, `origin/main`, while there is none), and offers the higher of that and what semantic versioning gives since the last
  portal tag (its CHANGELOG entries, and the apps added, removed or moved in `apps.toml`); **Bump portal** writes it with a CHANGELOG entry that lists the pinned app
  releases, and runs `tools/check_manifest.py` (step 4). Then commit, test on a BC-250 (below), and only then push
  and tag the portal (step 5). The window lists these commands in that order. While step 1's releases are
  not tagged yet, Bump portal lists step 1's commands with the bump in them instead (amending the release commit
  when it is already made and not pushed), and the portal release follows once the apps are pinned.
- **3. Retract app:** withdraws a release (see [Withdrawing a release](#withdrawing-a-release)).
- **Test on this board** holds the tests of a release on a BC-250. **Test app updates** and **Test Portal
  release** run the two board tests below in a terminal, with `apps/suite/check-release.sh`: the portal from the
  checkout before the push, and the published portal release after GitHub has built it. **Test withdrawal** does
  the first on a board with a withdrawn app installed. **Installer tests** opens BC-250 Installer Tests from the
  checkout. **Record portal tour** records the portal's video tour from the checkout as it is now, for the wiki and
  YouTube (`tools/record-tour.sh`, about a minute, its output in Logs), into
  `~/Videos/bc250-portal-tour-v<portal version>.mp4`, and opens it in your video player. Linux only, except
  **Close issues**: it lists the open issues on GitHub, such as the weekly Upstream review, each with a tick box.
  **Run** closes the ticked ones with `gh issue close` in the Commands tab, with a comment when you write one; it
  needs a gh login (`gh auth login`). A double click opens an issue on GitHub.
- **Test local apps**, on the same tab: the portal and every app window in the checkout, as an icon (the portal first).
  When the portal is already open, its icon warns instead of starting: a second portal never opens (starting it only
  brings the open window to the front), so close it first. A click starts that app from the checkout,
  to try a change before its release: `python -m <package>` with the checkout's venv and its `core`, as `run.sh`
  starts Suite Releases. An app that changes how the board runs asks first, as in the portal; started from the
  checkout it uses the scripts in the checkout. Each app writes its output to
  `~/.cache/bc250-release/run/<package>.log`. When an app stops with an error, the end of its log shows on the page.
  The apps keep running when you close the window. The last icons are the wikis in the checkout, one for each
  `mkdocs.yml`: **BC250 Bazzite Suite wiki (local)** serves this wiki from the checkout with `mkdocs serve` (the
  development venv has MkDocs) and opens it in the browser at `http://127.0.0.1:8765/nexus/bc250-bazzite-suite/`, with
  its design panel open; **Nexus wiki (local)** does the same for the Nexus page, at port 8766. Each rebuilds on
  every save; its log is `mkdocs-<wiki>-local.log` there. When one is already running, a click only opens the page
  again. The wikis, like the apps, keep running when you close the window, and Suite Releases has no button that
  stops them. A wiki started before the checkout changed (after a pull, or a change to its `mkdocs.yml` or the
  design panel) can still show the old setup: stop it, then click its icon again. `pkill -f "mkdocs serve"` stops
  every wiki on Linux; on Windows, in PowerShell:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*mkdocs serve*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`.
  With **Wikis on the network** ticked, the icons serve the wikis on every address of the computer, at
  ports 8785 and 8786, so a handheld, a laptop or the TV opens them too: the addresses for those devices show on
  the page once a wiki started. The computer's firewall has to let them in (see the Nexus page's
  [Design](https://robertotorino.github.io/nexus/design/) chapter).
- **Logs** shows the log of the step last open, the whole window wide: what Apply, Pin, Bump portal, Retract
  or a test on this board wrote. A step that writes its log opens Logs; open the step again to go on.
- **git add**, **git commit**, **git push** and **git tag**, under the tabs, commit, push and tag without typing a command, with
  the checks in between. **git add** stages every change and new file and runs `tools/fix-modes.sh`, which sets
  the exec bits CI checks. **git commit** runs `tools/check_versions.py` and `tools/check_manifest.py` first and
  commits only when they pass; Apply and Bump portal fill in its message, and tick **Amend** when their commands
  add to the last commit (only a commit that is not pushed yet). **git push** runs `tools/ci-local.sh` first on
  Linux and pushes only when CI's jobs pass. **git tag** runs `tools/tag-release.sh` (below) with the tags of the
  step open: on tab 2 the portal's release, on the other tabs step 1's app releases that have no tag yet; it
  works once HEAD is pushed. **git push** and **git tag** ask first, with the commits or tags they send and
  the command. When the GitHub token on the machine is a `gh` login or a classic token, which reach every
  repository of your account, they say so: a fine-grained token for this repository only is safer. Each button
  works only when it has something to do, and none while a command runs; their output appears in **Commands**.
- **The command line** in **Commands** runs a command in the checkout, so you need no separate terminal for the
  commands the steps show. Type it and press Enter; its output appears above the line as it runs. **Commands**
  lists the commands the last step showed (Apply, Bump portal or Retract), one per line: pick one to put it on
  the line, then check it and press Enter. Up and Down bring back earlier commands, also from earlier sessions.
  **Stop** or Ctrl+C interrupts a command, along with anything it started in the background; `clear` or **Clear**
  empties the output.
  Each command runs with `bash -lc` in the folder the last `cd` left; variables you set do not carry over to the
  next command. A command cannot read input, so nothing can ask you something: git does not prompt for a password,
  opens no editor (commit with `-m`) and pages nothing. For a command that must ask, use a terminal. After each
  command the window reads the checkout again, as **Refresh** does. On Windows it needs Git Bash's `bash` on the
  PATH.

**GitHub** in the header shows whether GitHub built your last push: every workflow run (CI, Release, Manual) on
its commit, tags included. It reads **building** while one runs, then **passed** or **failed**; hover for each
run, click to open the run that failed (or still runs) on GitHub. It looks every 30 seconds while a build runs and
every 5 minutes otherwise, and **Refresh** looks at once. When a run it saw running finishes, a desktop
notification says whether it passed. It needs no GitHub token: answers that did not change do not count against
GitHub's limit of 60 requests an hour.

**GitHub status** beside it says whether GitHub itself works, as [githubstatus.com](https://www.githubstatus.com/)
reports it: a green dot while every part of GitHub is up, a red dot while the page reports a problem (an incident,
or a part such as Actions or Pages degraded or down). A build that waits in *queued* for long is often such a
problem. Hover for the incident and the parts affected; click to open the status page. It looks every 5 minutes,
and **Refresh** looks at once.

**Claude tokens today** says how many tokens Claude Code on this computer used since midnight, read from its own
transcripts (`~/.claude`, or the folder `CLAUDE_CONFIG_DIR` names). Hover for the last 5 hours, the input, output and
cache tokens, and each model; click to open [Claude's usage page](https://claude.ai/settings/usage), which shows
your plan's limits. Other computers and claude.ai are not counted. Without Claude Code the pill is not shown. It
looks every 5 minutes, and **Refresh** looks at once.

The releases step 2 waits for are followed from the same runs. The **GitHub** column of the pin table says where
each release to pin stands: *no run seen* (is the tag pushed?), *building…*, *ready* or *failed*; **Pin** waits
for a release that is still building, or says that its workflow failed, instead of failing on a checksum that is
not there yet. When the release of an app to pin is ready, a desktop notification says so (*ready to pin*), also
when the run started and ended between two looks, or before the window opened; each release is told once. Under
the portal version, a line says where the portal's own release stands: *not tagged yet* after Bump portal and the
commit (nothing reaches the users until `tools/tag-release.sh portal-v<x.y.z>` is run, after the test on a
board), then *building*, *released* (Test release installs it) or *failed*; its notification says *ready* when
GitHub built it.

Only portal releases are marked **Latest** on GitHub (`release.yml` passes `--latest=false` for app releases), so
`/releases/latest`, which the README and the manual link to, always opens the newest portal. App release notes
start by pointing to it.

A red line at the top of the window means a release tag points at a commit whose `VERSION` is not the tag's
version: the tag was made before the version bump was committed, and `release.yml` cannot build it. Delete the tag
(the line shows how), commit and push the bump, and tag again with `tools/tag-release.sh`.

`tools/tag-release.sh <tag> [...]` tags HEAD and pushes the tags, but refuses while HEAD does not hold each tag's
version (the bump is not committed yet), while that folder has uncommitted changes, while HEAD is not pushed to
`origin/main`, or when CI did not pass on HEAD: it asks GitHub (`tools/ci_state.py`) and waits while CI still runs,
up to an hour. A portal tag also waits for the app releases it pins: each one tagged on GitHub and pinned with its
sha256 (step 2), as the portal's release needs them. A plain `git tag` tags whatever HEAD is at that moment, also the commit from before the bump or one
CI failed. `release.yml` asks the same before it builds anything: a tag on a commit CI did not pass gives no
release. It then builds and publishes the release without an approval on GitHub (see
[GitHub settings](development/github-settings.md#environments)).

`python3 tools/release_plan.py` lists every app with its version, its last tag and its pin, without Qt.

### Testing a portal release before its tag

A portal release promises one set of app releases, each with its checksum. Once its tag is out, every installed
portal offers those releases as updates. So before the tag, check on a BC-250 that exactly those pinned releases
install and run:

1. Bump the portal (step 4) and commit. Pushing is not needed for this test.
2. Click **Test app updates** on the release front end's **Test on this board** tab, or run `apps/suite/check-release.sh local`. It installs the portal
   from the checkout (`./install.sh` in the repository root: this portal version, with its new pins in
   `apps.toml`) and starts it with the pinned releases instead of the checkout:

    ```bash
    bc250-bazzite-suite --source release
    ```

    Apps then install as on a user's board: the portal downloads each pinned tarball from GitHub and refuses it
    unless its checksum matches the pin. Without `--source release`, a portal installed from a checkout installs
    the apps from the checkout.
4. The apps whose pin changed show a red dot and a red Install button. Update them, open each one and check that
   it starts and works; afterwards the red dots and the update count in the header are gone.
5. All good: tag the portal (step 5). Something wrong: fix the app and release a new patch version of it (steps 1
   to 4). Nothing has reached users yet.

This does not test the portal tarball itself, which GitHub builds from the tag; the release workflow checks it
(`tools/check_manifest.py --require-tags`, and the bundled Bazzite Test against its pin). The next section tests
it on the board.

### Testing a portal release after its tag

Once GitHub's release workflow has built the portal release, click **Test Portal release** (tab **Test on this
board**), or run:

```bash
apps/suite/check-release.sh release              # the release of portal/VERSION
apps/suite/check-release.sh release portal-v0.9.2
```

It downloads the release tarball and its `SHA256SUMS` from GitHub into `~/.cache/bc250-release-check/`, checks
the checksum, installs it and starts it. The board then runs the official release, as a user's board does: check
that the portal starts, that its version is the new one, and that the apps install. To go back to the checkout,
run `./install.sh` in the repository root (or Test app updates). A portal from the checkout shows an orange
banner at the top, "Local build"; the published release has none.

### Withdrawing a release

A release that must not be used any more, because of a privacy, security or any other problem, is withdrawn.
The release stays on GitHub, so its history is kept, but nothing installs it any more:

1. In BC250 Suite Releases, tab **3. Retract app**: choose the app's pinned release, write why, and press
   **Retract**. This adds `withdrawn = "<reason>"` to its entry in `apps.toml` and a CHANGELOG entry to the app.
   **Take back** removes it again.
2. **Test withdrawal** (tab **Test on this board**) on a BC-250 with the app installed: it installs the portal from the checkout and starts it
   (`check-release.sh local`). The portal must say the app is not available any more, remove it, and then show
   **App not available** on its tile.
3. Mark the release on GitHub with the command the tab shows: `gh release edit <tag> --prerelease --title
   "Withdrawn: <tag>" --notes "..."`. A pre-release is skipped by every update check, so no app offers it.
4. Release the portal (tab **2**, at least a minor version): its CHANGELOG entry names the withdrawal. A board
   that updates to it removes the app; the portal update button says so beforehand ("withdraws ...").

### Checking a release

A release tarball has the same content when you build its tag yourself, but usually not the same checksum: the
gzip compression differs between zlib builds (Fedora uses zlib-ng, GitHub's Ubuntu runners zlib), so compare the
unpacked files, not the `.tar.gz`. Bazzite Test's build time in `bazzite_check/_build_info.py` is the commit time too;
older Bazzite Test releases recorded the clock, and there only that line differs:

```bash
git archive <tag> | tar -x -C /tmp/src
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct <tag>) python3 /tmp/src/tools/build_release.py <tag> /tmp/local
curl -LO https://github.com/RobertoTorino/nexus/releases/download/<tag>/<tag>.tar.gz
mkdir -p /tmp/a /tmp/b && tar -xzf <tag>.tar.gz -C /tmp/a && tar -xzf /tmp/local/<tag>.tar.gz -C /tmp/b
diff -r /tmp/a /tmp/b
```

The checksum pinned in `apps.toml` is always the one of the published tarball. That is also why the release
tests pin their own local builds instead of the published ones.

---

### a new app gets into the portal
#### Code

Create apps/<name>/ with VERSION 0.1.0, a CHANGELOG, a LICENSE and a .gitignore. For an app that stays outside the
portal, add `.standalone` instead of adding it to `portal/apps.toml`. An app that runs from the checkout and is
never released also gets `.checkout-only`, and a `[checkout.<name>]` table in `apps.toml` (no tag) when the portal
should list it on its Development tab. Such a tool outside `apps/` (like
`tools/installer-tests/gui`) names its folder with `folder = "..."` and has the marker there.
Add an install.sh that supports --uninstall and puts a launcher in ~/.local/bin/, plus tests under tests/.        
Add the app to ./test.sh, the CI shellcheck list and an installer test in tools/installer-tests/.       
Add its [apps.<name>] card to portal/apps.toml: name, summary, changes_board, category (the same as its icon's in
icons/categories.toml: it is the app's tab in the portal), install/uninstall/detect/launch,          
and tag = "<name>-v<VERSION>" with sha256 left empty. CI accepts a tag that doesn't exist yet as long as it matches the app's VERSION.        
Run all the checks and hand over.

#### Release:
5. Commit and push. CI asks for a portal version bump: minor for a new app; for an app update, at least as big as the app's bump.             
6. Tag <name>-v0.1.0. release.yml builds the tarball and SHA256SUMS and publishes the release.              
7. Run python3 tools/pin_app.py <name>-v0.1.0, which fills in the sha256.             
8. Tag portal-v<x.y.z>. The portal release checks with --require-tags that every pinned tag exists, then publishes.             

Users then see the new card, and installed apps whose version differs from the pinned one get the red update dot.                 

#### New Version
- Change portal/VERSION from 0.1.0 to 0.2.0.
- Change __version__ in portal/bc250_portal/init.py:6 to the same number.
