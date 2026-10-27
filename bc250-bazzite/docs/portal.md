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
top, on every tab. Below it is a tab for each [category](apps/categories.md): Sustainable, Graphics, Gaming and
Utilities. Each app is a tile on its category's tab, left to right in the order of `apps.toml` and as many to a
row as the window fits; Bazzite Test is always the first tile on Sustainable:

- **The name**, without the suite's "BC-250" prefix.
- **The icon.** Click it to open the app; an app with two windows (CU Bisect, Cores Bisect) asks which one. The
  icon is gray while the app is not installed, and dims a little under the mouse while it opens the app. Hover over
  it to see what the app does, its state and the release this portal pins.
- **A red dot** in the icon: an update is available.
- **A red circular arrow** in the icon: reinstall the app. It is installed, but not by this portal (by hand, or
  under an earlier name of the app), so the portal does not know its version. Its red button reinstalls the version
  this portal pins. An app installed from a checkout of the repository without its version recorded shows it too.
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

The tools for working on the suite are not in the portal: [Nexus Releases](https://robertotorino.github.io/nexus/releases/)
and BC-250 Installer Tests (`bc250-bazzite/tools/installer-tests/gui`, a window that runs the installer tests one at
a time) run from a checkout of the repository and have no release. Start them there, or give them a menu entry with
their own `install.sh`.

- `apps/` may also contain standalone tools (with a `.standalone` marker) that do not appear in `apps.toml`
  and that the portal does not install or open.
- Install, update and uninstall run **the app's own installer** in a terminal window, because installers may ask
  for the sudo password and print what they do. The portal watches for the result and refreshes. A terminal whose
  installer ended well closes by itself; one that failed stays open with what happened until you press Enter.
- Apps that change how the board runs (CU/core unlocks, the GPU governor, GPU overclocking, the ACPI override, the VRAM
  split, a patched GPU driver) are marked **changes the board**. The portal warns before installing or opening them.
- Each portal release pins one tested release of every app in [`apps.toml`](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/portal/apps.toml). The portal downloads
  exactly those tarballs from the suite's GitHub releases and checks each against the SHA-256 pinned there, or
  against the release's `SHA256SUMS` until one is pinned. Then it unpacks the tarball without ever writing
  outside its folder.
- **Updates:** a red dot marks every app whose installed version differs from the one this portal pins; its red
  Install button installs the pinned version. An app installed from a checkout of the repository counts as well:
  the portal records the checkout's version of it and compares that with the one it pins. A portal that runs from a
  checkout shows what it installed from there as installed, whatever it pins. The notice beside Bazzite Test counts
  them and the apps that need a reinstall, and names each one with its tab and versions. Click a name to go to its
  tile. A tab with such an app
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
  disabled once every app of the category is installed. A portal installed for the first time fills a category with
  one click.
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

From the [Nexus index](https://github.com/RobertoTorino/nexus/releases/latest), under BC250 Bazzite Suite,
download `portal-v<version>.tar.gz` and `SHA256SUMS`, then:

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
The list has every app this portal lists and the apps an earlier portal installed that this one no longer lists (an app dropped from the suite), each removed
with its own uninstaller. Those apps keep their own settings, also with `--purge`. Of the portal's own records,
only those of the apps you kept stay, with the release each one's uninstaller needs; with no app left, that folder
goes too. To remove the whole suite at once, `--uninstall --all` asks one question instead of one per app, after a
warning that names every app it will remove; with `--purge` the apps' own settings, history and results go as
well.

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
development venv from [Development](https://robertotorino.github.io/nexus/development/#set-up-and-test) on the Nexus page (Bazzite's own `python3` has no PyQt6):

```shell
cd portal
PYTHONPATH=../core ../.venv-linux/bin/python -m bc250_portal    # --source release: the pinned GitHub releases
```

To install from the checkout, run `./install.sh` in the repository root (or here in `portal/`). It bundles
`../core` and installs `../apps/check`. The installed portal then installs the other apps from the
checkout too, so keep the checkout where it is.

## apps.toml and releases

The comment at the top of [`apps.toml`](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/portal/apps.toml) describes its fields. The rules, checked in CI by
[`bc250-bazzite/tools/check_manifest.py`](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/tools/check_manifest.py):

- **Pinned tags.** Every pinned tag must exist when the portal is released. On `main`, a tag may also be the
  next release, which means its version equals that app's `VERSION`.
- **Version bumps.** A change to `apps.toml` needs a `bc250-bazzite/portal/VERSION` bump at least as large as the largest app
  bump it pins: an app patch release needs at least a portal patch release, an app minor release at least a
  portal minor release, and so on. An added, removed or withdrawn app needs at least a minor portal release.
- **Withdrawn releases.** `withdrawn = "<reason>"` in an app's entry withdraws its pinned release (see
  [Withdrawing a release](#withdrawing-a-release)). Not for Bazzite Test, which is always installed.

Releasing an app and pinning it in the portal:

1. Bump `bc250-bazzite/apps/<app>/VERSION` (and the copies that `tools/check_versions.py` lists), and update its CHANGELOG.
2. Commit and push, then tag with `tools/tag-release.sh <app>-v<x.y.z>` (it waits until CI passed on that
   commit); [`release.yml`](https://github.com/RobertoTorino/nexus/blob/main/.github/workflows/release.yml) builds
   `<tag>.tar.gz` and `SHA256SUMS` with [`tools/build_release.py`](https://github.com/RobertoTorino/nexus/blob/main/tools/build_release.py).
   An app with a Windows executable (SFTP Tools) also gets a Windows job on its tag, which adds
   `<app-id>-<version>-windows.zip` and its `.sha256` to the release; the portal ignores them.
3. `python3 bc250-bazzite/tools/pin_app.py <tag>`: this sets the tag and checksum in `apps.toml`.
4. Bump `bc250-bazzite/portal/VERSION` as `bc250-bazzite/tools/check_manifest.py` asks, and list the app release in the portal CHANGELOG.
5. Once the pinned app releases are tested together on a BC-250 (see
   [Testing a portal release before its tag](#testing-a-portal-release-before-its-tag)), commit steps 3 and 4,
   push, and tag with `tools/tag-release.sh portal-v<x.y.z>`. That release bundles the pinned Bazzite Test release (`check-v…`).
6. Once `release.yml` has published it, the Nexus index (GitHub's **Latest** release) shows it under BC250 Bazzite
   Suite, where users download the portal: [The releases on GitHub](https://robertotorino.github.io/nexus/releases/#the-releases-on-github) on the Nexus page.

### The release front end

**Nexus Releases**, Nexus's release front end, makes these file edits for you and runs the board tests below. How to
start and use it: [Releases](https://robertotorino.github.io/nexus/releases/) on the Nexus page.

### Testing a portal release before its tag

A portal release promises one set of app releases, each with its checksum. Once its tag is out, every installed
portal offers those releases as updates. So before the tag, check on a BC-250 that exactly those pinned releases
install and run:

1. Bump the portal (step 4) and commit. Pushing is not needed for this test.
2. Click **Test app updates** on the release front end's **Test on this board** tab, or run `bc250-bazzite/tools/check-release.sh local`. It installs the portal
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
(`bc250-bazzite/tools/check_manifest.py --require-tags`, and the bundled Bazzite Test against its pin). The next section tests
it on the board.

### Testing a portal release after its tag

Once GitHub's release workflow has built the portal release, click **Test Portal release** (tab **Test on this
board**), or run:

```bash
bc250-bazzite/tools/check-release.sh release              # the release of bc250-bazzite/portal/VERSION
bc250-bazzite/tools/check-release.sh release portal-v0.9.2
```

It downloads the release tarball and its `SHA256SUMS` from GitHub into `~/.cache/bc250-release-check/`, checks
the checksum, installs it and starts it. The board then runs the official release, as a user's board does: check
that the portal starts, that its version is the new one, and that the apps install. To go back to the checkout,
run `./install.sh` in the repository root (or Test app updates). A portal from the checkout shows an orange
banner at the top, "Local build"; the published release has none.

### Withdrawing a release

A release that must not be used any more, because of a privacy, security or any other problem, is withdrawn.
The release stays on GitHub, so its history is kept, but nothing installs it any more:

1. In Nexus Releases, tab **3. Retract app**: choose the app's pinned release, write why, and press
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

Create bc250-bazzite/apps/<name>/ with VERSION 0.1.0, a CHANGELOG, a LICENSE and a .gitignore. For an app that stays outside the
portal, add `.standalone` instead of adding it to `bc250-bazzite/portal/apps.toml`. An app that runs from the checkout and is
never released also gets `.checkout-only` and stays out of `apps.toml`: the portal lists only released apps.
Add an install.sh that supports --uninstall and puts a launcher in ~/.local/bin/, plus tests under tests/.        
Add the app to ./test.sh, the CI shellcheck list and an installer test in bc250-bazzite/tools/installer-tests/.       
Add its [apps.<name>] card to bc250-bazzite/portal/apps.toml: name, summary, changes_board, category (the same as its icon's in
bc250-bazzite/icons/categories.toml: it is the app's tab in the portal), install/uninstall/detect/launch,          
and tag = "<name>-v<VERSION>" with sha256 left empty. CI accepts a tag that doesn't exist yet as long as it matches the app's VERSION.        
Run all the checks and hand over.

#### Release:
5. Commit and push. CI asks for a portal version bump: minor for a new app; for an app update, at least as big as the app's bump.             
6. Tag <name>-v0.1.0. release.yml builds the tarball and SHA256SUMS and publishes the release.              
7. Run python3 bc250-bazzite/tools/pin_app.py <name>-v0.1.0, which fills in the sha256.             
8. Tag portal-v<x.y.z>. The portal release checks with --require-tags that every pinned tag exists, then publishes.             

Users then see the new card, and installed apps whose version differs from the pinned one get the red update dot.                 

#### New Version
- Change bc250-bazzite/portal/VERSION from 0.1.0 to 0.2.0.
- Change __version__ in bc250-bazzite/portal/bc250_portal/init.py:6 to the same number.
