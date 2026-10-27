<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Development

How the BC250 Bazzite Suite is laid out, how its wiki's pictures and tours are made, and how its versions and
releases fit together. What every suite shares is on the Nexus page: the repository's layout, setting up a venv,
the tests and CI on your own machine, working from Linux and Windows
([Development](https://robertotorino.github.io/nexus/development/)), the repository's settings on GitHub and Dependabot's pull requests
([GitHub settings](https://robertotorino.github.io/nexus/github-settings/)). How every app is built, and how to add one:
[Architecture and consistency](architecture.md). The tools a machine needs to work on it, on Bazzite or Windows,
and how they stay up to date: [The development machine](https://robertotorino.github.io/nexus/machine/) on the Nexus page. The portal's release steps are in
[Portal](../portal.md#appstoml-and-releases).

## Layout

The suite is `bc250-bazzite/` in the repository, laid out as every suite is; the rest of the repository is on the
Nexus page ([Layout](https://robertotorino.github.io/nexus/development/#layout)). Paths in this wiki are written from the root of the repository.

```
bc250-bazzite/                the BC250 Bazzite Suite:
  portal/                       the portal: app, apps.toml (the pinned app releases) and install.sh
  apps/<name>/                  one folder per app, each with its own VERSION and CHANGELOG
  tools/                        the suite's tools: pin_app, check_manifest, sync_icons, the installer tests,
                                the screenshot and tour scripts
  docs/ mkdocs.yml              this wiki (MkDocs Material)
  icons/ install.sh             the category icons; the portal's installer for a checkout
core/bc250_core/              the shared Python package its apps bundle; see bc250_core below
```

Its checks run on Bazzite and in CI (`ci.yml`): its tests with `./test.sh`, every CI job with `tools/ci-local.sh`
([CI on your own machine](https://robertotorino.github.io/nexus/development/#ci-on-your-own-machine)).

## The wiki's pictures and tours

To preview the manual locally, run `mkdocs serve` from the repository root with the development venv active,
then open <http://127.0.0.1:8000/bc250-bazzite-suite/>. Stop the server with Ctrl+C.

The picture of the portal on the home page (`bc250-bazzite/docs/images/home/portal.webp`) is taken from the portal itself:
`bc250-bazzite/tools/portal_screenshot.py` opens its window offscreen on this checkout's `apps.toml` and icons, in a home folder
of its own, with a fixed demo state (one update, the Sustainable tab open), and saves it. The wiki's workflow runs it
before every build, so the published picture always shows the portal as it is on main. Run it yourself to see the
same picture in `mkdocs serve`:

```bash
python bc250-bazzite/tools/portal_screenshot.py          # from the venv; --out FILE to save it elsewhere
```

The video tours are made the same way, frame by frame from the real windows, offscreen. `bc250-bazzite/tools/record-tour.sh`
records the portal's tour, about two minutes, with music under it that fades out over the last two seconds
(`bc250-bazzite/tools/sounds/the_quiet_engine_remix_3min.mp3`, made with generative AI tools; `--no-music` leaves it out).
`bc250-bazzite/tools/record-tour.sh --wiki` also writes the copy on the [Portal Tour](../portal-tour.md) page,
`bc250-bazzite/docs/videos/portal-tour.mp4` (1280 × 720, about 6 MB) and its poster: run it after a change to the portal's window.
`bc250-bazzite/tools/record-app-tour.sh` records one app's, about 40 seconds, the same script for every app, with music under it
that fades out over the last two seconds (`bc250-bazzite/tools/sounds/the_quiet_engine.mp3`, made with generative AI tools):

```bash
bc250-bazzite/tools/record-app-tour.sh fan                          # ~/Videos/bc250-fan-tour-v<version>.mp4
bc250-bazzite/tools/record-app-tour.sh compute --package cu_unlock  # compute and cores have two programs
bc250-bazzite/tools/record-app-tour.sh cec cec.mp4 --seconds 30     # another file, another length
bc250-bazzite/tools/record-app-tour.sh fan --no-music               # without sound; --music FILE for another track
```

The app starts from the checkout in a home folder of its own. The tour points at the controls of its header, with
their tooltips as captions, and opens its tabs or pages; it presses no buttons and nothing runs as root. What the
app reads from the board is real, so watch the video before you publish it.

The controller beside the board on the home page changes with every portal release, in the order of
`bc250-bazzite/docs/images/home/controllers/controllers.toml`. To add one, put its picture in that folder (WebP, 1295 × 1600, with
a transparent background, like the others) and add it at the end of the list with its alt text.

## Where things are installed

- **Root-owned `/opt`:** the portal (`/opt/bc250-bazzite-suite`), Bazzite Test (`check`), cores, oc and
  acpi, whose scripts run as root: a normal user cannot change code that sudo runs.
- **Your home folder:** the shared venv `~/.local/share/bc250-bazzite-suite/venv` (PyQt6, used by all suite
  GUIs and removed with the last of them), plus each app's settings, results and launchers.
- **`bc250_core` per app:** each app's release carries the `bc250_core` it was tested with, next to its own code.
  Apps with different release tags never share a core version they were not tested with.

[Portal](../portal.md#install) has the full table.

## Versions and tags

`core/`, `portal/` and every app have a `VERSION` file; it is the single source of the version. Versions that are
also written in a script or package (`VERSION="…"`, `__version__ = "…"`, pyproject `version`) must match it, which
CI checks with `tools/check_versions.py`. Everything started at 0.1.0 with the suite.

Each app is released on its own tag (`check-v0.1.0`, `gpu-v0.4.0`, …); the release workflow builds
`<tag>.tar.gz` and `SHA256SUMS`. The portal has `portal-vX.Y.Z` and pins one release of every app in
`bc250-bazzite/portal/apps.toml`; a change there since the last portal release needs a portal version bump at least as large as the largest app bump.
The release steps are in [Portal](../portal.md#appstoml-and-releases).

How the releases are titled on GitHub, and why its **Latest** release is the Nexus index and not this suite's
portal: [The releases on GitHub](https://robertotorino.github.io/nexus/releases/#the-releases-on-github) on the Nexus page.

### Upstream releases an app pins or follows

Decky Loader Manager installs one Decky Loader release, pinned in
`bc250-bazzite/apps/decky/decky_manager/loader.py` (`VERSION`, `TAG`, `SHA256`), and writes Decky's service unit
itself (`unit_text()`). `bc250-bazzite/tools/check_upstream.py` compares both with Decky's repository: a newer stable release, the
SHA-256 GitHub publishes for the pinned binary, and Decky's `plugin_loader-release.service` at the pinned tag and on
`main` (Decky's own updater installs `main`'s). It exits with 0 when they match, 1 when Decky moved and 2 when it
could not check. The Upstream workflow (`.github/workflows/upstream.yml`) runs it every Monday and can be started by
hand. What moved goes into the open **Upstream review** issue (a new one when none is open, else its list is
updated with a comment), which notifies everyone who watches the repository. The workflow never closes it: close
it once every item on it is handled on `main`, else next Monday's run opens it again. **Close issues** in Suite
Releases (tab Test on this board) does it, or a command with a gh login:

```bash
gh issue list                                                  # the open issues, with their numbers
gh issue close <number> --comment "Decky pinned at v3.3.0."    # close one, saying how it was handled
```

The run fails only when an upstream could not be checked. A moved pin means a new version of the app is due, with
the new pin tried on the board first.

The shadPS4 Manager installs one shadPS4 release, pinned in `bc250-bazzite/apps/shadps4/shadps4_manager/emulator.py`
(`VERSION`, `TAG`, `ASSET`, `SHA256`). The same tool checks it: a newer stable release, with the Linux zip and the
SHA-256 GitHub publishes for it that a new pin needs, and the SHA-256 of the pinned zip. A new shadPS4 can change
what the app relies on (its `config.json`, the shadNet protocol), so a new pin also needs a look at what changed.

The PPSSPP, PCSX2 (its stable channel) and RPCS3 Managers and Mesh Shaders each pin one release: `VERSION` or
`LANDMARK` in the app's `emulator.py`, and `DIRECTMESH` in `bc250-bazzite/apps/mesh/bc250-mesh-shaders.sh`. RPCS3's `emulator.py`
also holds the size of the pinned AppImage (`SIZE`), by which the app sees that RPCS3 replaced itself with another
build, so a new pin moves it too.
The same tool reports a newer stable release than the pin (for DirectMesh the newest `directmesh-v*` tag); the apps
check the checksum of what they download themselves. The governor has no pin in the repository (its version is the
one COPR built); the GPU Governor Manager compares the installed package with filippor's latest release.

The BC-250 Upscaler Manager pins no HelixSR release: it gets the latest of one major version (`SUPPORTED_MAJOR`), or the
fallback HelixSR's developer names. Its `bc250-bazzite/apps/upscaler/upscaler/acquire.py` holds `SUPPORTED_MAJOR`,
`KNOWN_VERSION`, the newest release the app was checked against, and `FALLBACK_VERSION`. The same tool reports a newer
stable release (users get it at once, so what changed in its setup, its zip and `helixsr.ini` needs a look and a try
on the board; then `KNOWN_VERSION` moves), a newer major version (users do not get it until the app is moved to it), a fallback
named in the latest release's notes that is not `FALLBACK_VERSION`, and a fallback release without its zip.

The Vita3K Manager installs one Vita3K build, pinned in `bc250-bazzite/apps/vita3k/vita3k_manager/emulator.py`
(`BUILD`, `SEMVER`, `COMMIT`, `SHA256`, `SIZE`). Vita3K has no stable releases: every change is a build, kept as a
release of `Vita3K/Vita3K-builds` tagged with its number, with `Vita3K-x86_64.AppImage` and the SHA-256 GitHub
publishes for it. Builds come almost daily, so the tool does not check them; the app itself says when a newer build
is out. A new pin takes the asset's digest and size from that release, and a look at what the app relies on in
Vita3K's source at the new build:

- the command line (`vita3k/config/src/config.cpp`): `-r <title ID>`, `--frontend sdl`, `--firmware`,
  `--pkg` with `--zrif`, and a `.vpk`, `.zip` or folder as the positional argument;
- the folders (`vita3k/app/src/app_init.cpp`, `init_paths`): settings in `$XDG_CONFIG_HOME/Vita3K/config.yml`, the
  storage in `$XDG_DATA_HOME/Vita3K/Vita3K` unless `pref-path` in config.yml moves it, games in its `ux0/app`;
- the firmware's three parts (`vita3k/app/src/app.cpp`, `get_firmware_state`): `vs0`, `sa0` and `pd0` counted as
  installed when they hold anything;
- the SDL frontend (`vita3k/sdl-frontend`): it runs the game given by `-r` and quits with it, and has no full screen
  of its own. `--fullscreen` is not used: Vita3K writes it into config.yml as `boot-apps-full-screen`;
- the AppImage's self-updater (`bin/10-self-updater.hook` in the AppImage): it overwrites the AppImage with the
  newest continuous build unless `DISABLE_AUTO_UPDATES=1`, which the run wrapper sets. `vita3k --version` on the new
  AppImage confirms the build and commit.

The tests hold the `config.yml` the pinned build writes on its first start (`tests/fixtures/config-4186.yml`); a new
pin replaces it with the new build's, renamed for it.

The Xenia Manager installs one Xenia Canary build, pinned in `bc250-bazzite/apps/xenia/xenia_manager/emulator.py` (`BUILD`,
`COMMIT`, `PUBLISHED`, `SHA256`, `SIZE`). Xenia has no stable releases either: every change is a release of
`xenia-canary/xenia-canary`, tagged with its commit, with `xenia_canary_linux.AppImage` and the SHA-256 GitHub
publishes for it. A tag is no number, so the app takes a release published after `PUBLISHED` as a newer build; the
tool does not check them. A new pin takes the asset's digest and size and the release's date, and a look at what the
app relies on in Xenia's source at the new commit: the `--fullscreen` option and the positional path
(`src/xenia/app/xenia_main.cc`), the storage root in `$XDG_DATA_HOME/Xenia` (the same file, and `GetUserFolder` in
`src/xenia/base/filesystem_posix.cc`), the places of the game partition in a disc image
(`src/xenia/vfs/devices/disc_image_device.cc`, which `GAME_PARTITIONS` in the app's `games.py` copies), and GTK on
X11 (`GDK_BACKEND` in `src/xenia/ui/windowed_app_main_posix.cc`).

```bash
python3 bc250-bazzite/tools/check_upstream.py            # all of them
python3 bc250-bazzite/tools/check_upstream.py helixsr    # one: decky, shadps4, helixsr, ppsspp, pcsx2, rpcs3 or directmesh
```

## bc250_core

The shared Python package every app of the suite bundles, its modules and its tests:
[bc250_core](https://robertotorino.github.io/nexus/development/#bc250_core) on the Nexus page.
