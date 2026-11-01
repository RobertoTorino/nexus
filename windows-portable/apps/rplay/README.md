<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

![Status: Beta](https://img.shields.io/badge/status-Beta-f5a524)
[![CI Windows Portable](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml/badge.svg)](https://github.com/RobertoTorino/nexus/actions/workflows/ci-windows-portable.yml)
[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)

# Remote Play

Plays your PS4 and PS5 on the handheld over the home network: finds them, registers the handheld with them, wakes
them and streams them full screen, the handheld's controls as the console's controller. The BC250 Bazzite Suite's
Console Link made for the handheld.

Made for the handheld in your hands: full screen, the controller moves the amber focus, B goes back, View (⧉) exits
the app, and everything also works by touch. How to install and use it: [Remote Play in the wiki](https://robertotorino.github.io/nexus/windows-portable-suite/apps/rplay/).

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\rplay\run.ps1             # full screen
windows-portable\apps\rplay\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-rplay.ini`, the log, the registered
consoles (`consoles.json`), the history and the streams' statistics in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-rplay\`.

## The native core and SDL3, for the stream

The stream needs the app's native core (`native/`, Console Link's in Rust, with FFmpeg linked in for the video)
and SDL3 (the controllers). Searching, registering and the test session work without them. A release brings both;
from the checkout, once, in Git Bash at the repository's root:

```bash
winget install MSYS2.MSYS2 Rustlang.Rustup                          # MSYS2 in C:\msys64, and rustup
.venv-windows/Scripts/python.exe -m pip install "maturin>=1.5,<2"
PATH="$PWD/.venv-windows/Scripts:$PATH" bash windows-portable/tools/build_native.sh rplay --setup
.venv-windows/Scripts/python.exe windows-portable/tools/build_release.py --binaries rplay   # SDL3.dll
```

`--setup` installs MSYS2's MINGW64 compiler, make, pkg-config and nasm, and Rust's `stable-x86_64-pc-windows-gnu`
toolchain (the GNU one, whose C runtime is MINGW64's); then FFmpeg is built once from its pinned sources
(`native/ffmpeg/build.sh`, into `%LOCALAPPDATA%\windows-portable-suite\build\`), the module with maturin, and its
wheel installed in the venv. Run it again after a change to `native/` (`--setup` only the first time).

## License

AGPL-3.0, see [LICENSE](LICENSE). The protocol code is ported from [chiaki-ng](https://github.com/streetpea/chiaki-ng)
(AGPL-3.0-only with an OpenSSL exception), through the BC250 Bazzite Suite's Console Link; those files keep that
license. They are the files marked `SPDX-License-Identifier: AGPL-3.0-only`, modified from chiaki-ng's code (ported
to Python and Rust from 12-10-2026 on); the code and tests call chiaki-ng "the reference". The app's own files are
AGPL-3.0-or-later. The native core links [FFmpeg](https://ffmpeg.org) statically, LGPL-2.1-or-later (see
[native/ffmpeg/COPYING.LGPLv2.1](native/ffmpeg/COPYING.LGPLv2.1)), built from its own sources by
`native/ffmpeg/build.sh`; the release carries [SDL](https://libsdl.org) 3 (Zlib), pinned in `binaries.toml`.
