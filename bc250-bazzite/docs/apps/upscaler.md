<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Upscaler Manager](../assets/upscaler/bc250-upscaler.webp){ .app-logo }

# BC-250 Upscaler Manager

PyQt6 front-end that deploys **[HelixSR](https://github.com/lonewolf0622/HelixSR)** – the FSR 3.1 drop-in
upscaler with DLSS-style neural networks – into games on an **AMD BC-250** board running **Bazzite**
(Fedora Atomic / rpm-ostree), and keeps track of where it was put.

HelixSR is not an injector: it is a replacement for the `amd_fidelityfx_upscaler_dx12.dll` /
`amd_fidelityfx_dx12.dll` a game ships with. Deploying it means renaming the game's DLL to `*.original.dll`
and dropping HelixSR's DLL, its two network files and an optional `helixsr.ini` in the same folder. This
app does exactly that, reversibly, and nothing else on the system is touched. No launch options, no
`WINEDLLOVERRIDES`, no Proton tweaks are needed. Only OptiScaler, for games without FSR 3.1, needs a launch
option; the app sets that one too (see below).

---

## What it manages

- **Setup in one click** – *Download and build* fetches the latest HelixSR release from GitHub (checked against
  the SHA-256 GitHub publishes for it), reads the exact
  URLs and SHA-256 sums its setup scripts pin, downloads what the PC still needs **in parallel** and verified
  (NVIDIA's DLSS 310.7.0 DLL, 59 MB; Microsoft's DirectX Shader Compiler, 25 MB; on Bazzite a portable Python,
  67 MB), runs `helixsr-setup.sh --yes` with live output and imports the result as the payload. The DLSS DLL is
  deleted afterwards. A DLSS 310.7.0 DLL from a game you own can be used instead (*Find in Steam* compares
  checksums), which skips NVIDIA's download. The build itself is HelixSR's own script, unchanged: about 5–6 minutes on a
  BC-250, because it compiles the network's shaders for both wave sizes through Proton. The Setup page shows the
  elapsed time. From HelixSR 1.7.0 on, the script ends with its own game installer, which asks about each Steam
  game; the app gives it no input, so it stops there and only the network files are built. From HelixSR 1.8.0
  on, the network is built into HelixSR's DLL instead of two separate files. From HelixSR 1.9.0 on, the script
  can also build frame generation for HelixSR Scaler (about 400 MB from NVIDIA); the app does not deploy that, so
  it skips this step (`--no-fg`). HelixSR 2.x keeps its DLL in the release's `HelixSR-fsrfg` folder, and its
  `helixsr-setup.sh --yes` would install HelixSR Scaler into every game it finds. For 2.x the app therefore runs what
  that script runs before its game installer: HelixSR's own builder (`setup/helixsr_setup.py`, unchanged) on
  `HelixSR-fsrfg`, with the same Python, shader compiler and Proton, and without frame generation (`--no-fg`). It
  then checks that the DLL carries the network. Your games are only changed from the Deploy and Games pages. When
  a later major version is out that the app does not support yet, the Setup page says so and the app keeps getting
  the newest release it supports.
- **Version choice** – *Version* on the Setup page picks the latest HelixSR release (the default) or HelixSR
  1.8.1, the version HelixSR's developer recommends when the latest one does not work for you (please then open
  an issue at [HelixSR](https://github.com/lonewolf0622/HelixSR/issues) with the game's `helixsr.log`).
  Switching builds the network files for that version and replaces the payload; deploy again per game
  afterwards.
- **Update checks** – at start (can be turned off) or on demand: the payload against the latest HelixSR release
  on GitHub. The app itself is updated through the BC250 Bazzite Suite portal. A newer HelixSR is flagged on the Overview; building again
  updates the payload and deployed games show *Older build* (*Newer build* after switching back to 1.8.1). After
  a build the app offers to update them; *Update older games* on the Overview does the same, for older builds and
  for games whose own DLL is back, keeping their `helixsr.ini`. *Download and build* needs about 1.5 GB free.
- **Games** – every Steam game, each looked through in the background for an AMD FSR 3.1 DLL: the games that have
  one first, with HelixSR's state in each; the others grayed out (*Open on Deploy page* still takes them to
  OptiScaler). *Run with HelixSR* (or a double-click) puts HelixSR in when it is missing, older, or replaced by
  the game's own DLL after an update, then starts the game through Steam (`steam://rungameid/<AppID>`). It
  asks before the first install into a game and does nothing while the game runs.
- **Payload** – one imported HelixSR release, kept under `~/.local/share/bc250-upscaler/payload`.
  Filled by the Setup page, or by hand: run the release's `helixsr-setup.sh` yourself and import the folder or
  the zip. It builds `helixsr_weights.bin` and `helixsr_kernels.pak` from NVIDIA's DLSS DLL – those files are
  NVIDIA's property, so this app never ships them. Only the known HelixSR files are copied; the payload survives
  updates and `./install.sh --uninstall`.
- **Deployments** – every place HelixSR was put, with a live status (in place, older or newer build, network
  files missing, original restored when a game update or Steam put the game's own DLL back, folder gone), in `~/.config/bc250-upscaler/deployments.json`.
- **Two deploy modes**
  - *Replace the game's DLL* – for games with native FSR 3.1: pick the game folder (Steam libraries are
    scanned, including `libraryfolders.vdf` and the Flatpak Steam), the app finds every upscaler DLL (Unreal
    games bury it under `Engine/Plugins/.../ThirdParty/Win64`), backs it up and deploys. *Remove* restores
    the original. Re-deploying a newer build never overwrites the real original.
  - *Stand-alone folder for OptiScaler* – for games without FSR 3.1: writes a folder with the DLL under both
    FidelityFX names, the network files and the ini. With a payload from HelixSR 1.7.0 to 1.8.1, which ship the
    official OptiScaler (1.9.0 and newer do not; the fallback on the Setup page brings it, and the payload keeps
    it when you switch back to the latest), it also installs OptiScaler next to the game's `.exe` (Scan finds that folder): as
    `dxgi.dll`, or under the name of an OptiScaler the game already has, with `fakenvapi`, and its
    `OptiScaler.ini` pointed at the HelixSR folder. Select DLSS in the game. What it replaces is kept in the
    HelixSR folder's `backup`; *Remove* puts it back. Under Proton OptiScaler only loads with
    `WINEDLLOVERRIDES="dxgi=n,b"` in the game's Steam launch options, so for a Steam game the app adds that too:
    to the launch options already there (`WINEDLLOVERRIDES="dxgi=n,b" %command%` when there are none), for every
    Steam user. Steam writes its settings again when it closes, so it has to be closed for this: the app asks, closes
    Steam, sets them and starts Steam again. In Game Mode Steam stays open; the line is then copied to the clipboard
    to paste into the game's *Properties* in Steam. *Remove* puts the launch options back as they were, unless you
    changed them since. Untick it to install OptiScaler
    yourself: the page then gives you the `OptiScaler.ini` lines (`Dx12Upscaler=fsr31`, `FfxDx12Path`,
    `FfxDx12SRPath` as `Z:\` paths) to paste.
    Optionally it adds a second upscaler, for example AMD's `amd_fidelityfx_upscaler_dx12.dll` with FSR 4: it
    goes into the folder as `amd_fidelityfx_upscaler_dx12.amd.dll` with `UpscalerDll` pointing at it, and
    OptiScaler's FFX Upscaler menu lists its upscalers after HelixSR.
- **helixsr.ini** – a form over every key HelixSR reads (`[Sharpening]`, `[ModelE]`, `[Log]`, `[Forwarding]`)
  with validation and a live preview that keeps the upstream comments. Save it as the default for new
  deployments or push it to an existing one. The page grays out what the payload's HelixSR version does not
  read: HelixSR 1.7 ignores `[Sharpening]` and `[ModelE] Network`; 1.8 reads sharpening again through
  `Sharpener` (`off`, `nvidia` or `rcas`), `Sharpness` and `UseGameSlider` instead of `Mode`.

## Privilege model

Everything runs as your normal desktop user: game folders under Steam are yours, the payload and the
deployment list live in your XDG directories. No `pkexec`, no root, no `rpm-ostree` layering. With OptiScaler
the app also changes the game's launch options in your Steam settings (`userdata/<user>/config/localconfig.vdf`),
and only that line.

## Requirements

```text
Python 3.11+
PyQt6>=6.11,<7
```

The PyQt6 wheels bundle Qt. HelixSR itself needs a game with an FSR 3.1 DX12 upscaler (or OptiScaler) and
the network files built by its `helixsr-setup.sh`; see the
[HelixSR README](https://github.com/lonewolf0622/HelixSR#readme) for the game side.

## Install on Bazzite

Install it from the BC250 Bazzite Suite portal, where it is under Gaming. Or download
`upscaler-v<version>.tar.gz` from the suite's
[releases](https://github.com/RobertoTorino/nexus/releases), unpack it and run the installer:

```shell
tar -xzf upscaler-v*.tar.gz
cd upscaler-v*/
./install.sh
```

It installs the app for your user only: a private venv with PyQt6 and the app under
`~/.local/share/bc250-upscaler`, the launcher `~/.local/bin/bc250-upscaler`, a
desktop entry, the icon and a Desktop icon (`./install.sh --no-desktop-shortcut` leaves the Desktop icon out).
**BC-250 Upscaler Manager** then appears in the application menu (and in Steam's
Game Mode via *Add a Non-Steam Game* if you want it there). Run `./install.sh` again from a newer release to
update, `./install.sh --uninstall` to remove it; the imported payload and the deployed games are left alone.
`./install.sh --uninstall --purge` also removes the payload and the settings. The list of deployed games stays, so
a reinstalled app can still restore them. An installed copy under the app's former name, HelixSR Manager, is taken
over: its payload, settings and list of deployed games move to the new folders, its launcher and menu entry go.

## Run from the repository

```shell
git clone https://github.com/RobertoTorino/nexus.git
cd bc250-bazzite-suite/apps/upscaler
python3 -m venv python && python/bin/pip install -r requirements.txt
PYTHONPATH=../../core python/bin/python -m upscaler
```

`--payload DIR`, `--deployments FILE` and `--work DIR` point the app at another payload folder, deployment
list and download folder, for development on a machine without Steam. `--no-update-check` skips the release
lookup at start. `--version` prints the version.

## Pages

- **Overview** – payload status (version from the release's README, DLL, weights, kernels, ini) with
  *Import folder* / *Import zip* / *Open payload folder*, and the deployment table with *Open folder*,
  *Remove* (restores the original or deletes the stand-alone folder), *Forget* and *Update older games*.
- **Setup** – release status for HelixSR with *Check now*; the version to get (latest or 1.8.1);
  *Download and build* with progress, the script's output, *Cancel*, *Import built release* and *Open work
  folder*; optional local `nvngx_dlss.dll`.
- **Games** – every Steam game with its FSR 3.1 DLL and HelixSR state; *Run with HelixSR*, *Open on Deploy page*,
  *Rescan*.
- **Deploy** – choose a Steam game or browse to any folder, scan for upscaler DLLs, pick the mode, decide
  whether to write the current `helixsr.ini`, deploy or remove. In folder mode the OptiScaler snippet is
  shown with a *Copy* button.
- **helixsr.ini** – the settings form, validation, preview, *Save as default* and *Apply to deployment*.
- **Help** – the workflow, where the files live, and links to HelixSR and OptiScaler.

The header shows the payload version, network-file status, deployments (ok / total) and the number of Steam
games found; it refreshes every 5 seconds.

## Development

```
upscaler/
  __init__.py       app name, version, XDG paths
  __main__.py       entry point (python -m upscaler)
  backend.py        pure file logic: payload import, DLL discovery, deploy/remove (both modes),
                    helixsr.ini parse/render/validate, deployment store, Steam library discovery
  acquire.py        GitHub release lookup, pinned-source parsing, verified parallel downloads,
                    the build (QThread: helixsr-setup.sh for 1.x, HelixSR's builder for 2.x) and the
                    update checker
  setup_page.py     Setup page
  main_window.py    header, navigation, polling, confirmations, wiring of page signals to the backend
  pages.py          Overview, Deploy and helixsr.ini pages
  help.py           Help page
  widgets.py        status pills, metric boxes, rounded tooltip (shared with bc250-governor-manager)
bc250_core/         the suite's shared code (its steam.py closes and starts Steam), bundled by install.sh and
                    the release
  fonts/            Inter (SIL OFL), used for the header on Linux
install.sh          per-user installer (venv, launcher, desktop entry, icon); --uninstall removes it, keeps the payload
bc250-upscaler.desktop  desktop entry template, Exec is filled in by install.sh
tests/              pytest suite (offscreen Qt, temporary payload and game folders, no real HelixSR needed)
test.sh             runs it with the project venv
```

Tests: `./test.sh` in the suite's root runs every test suite, this one included (extra arguments go to pytest,
e.g. `./test.sh -k ini`). For this app alone: `pip install -r requirements-dev.txt` then
`QT_QPA_PLATFORM=offscreen python -m pytest -q tests`. They cover the `helixsr.ini` round-trip against the
upstream file, payload import from folders and zips, DLL discovery, deploy/remove in both modes (including
re-deploy over an older build and refusing foreign DLLs), the deployment store, Steam library parsing, the
release lookup and the whole Setup run (downloads over `file://` URLs against a fake `helixsr-setup.sh` and a fake
2.x builder, checksum and script failures, a local DLSS DLL), the main window driven through its page signals and the translations
(compiler round-trip through `QTranslator`, completeness of every shipped language). The suite's CI
(`.github/workflows/ci.yml`) runs them on every push and pull request. Releases are tagged `upscaler-v<x.y.z>` in
the suite repository; `.github/workflows/release.yml` then builds the tarball and publishes it on GitHub.

The backend has no Qt dependency so it can be exercised from the command line or reused.

## License

GPL-3.0-or-later, see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bc250-bazzite/apps/upscaler/LICENSE). The bundled Inter font is under the SIL Open Font License
(`upscaler/fonts/Inter-LICENSE.txt`). HelixSR is a separate project under its own license; its
network files are derived from NVIDIA's DLSS and are never distributed by this app.
