<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Windows Portable Test

Gets to know a **Windows handheld** (first the ASUS ROG Xbox Ally X): what Windows reports about the device, and
every button, stick and trigger of its controller as you press them. It reads and shows; it changes nothing on the
device.

Made for the handheld in your hands: full screen, the controller moves the amber focus between the cards (A to run,
X to save the device report, B to close), and every card and button also works by touch.

## Install it

Download `wp-test-v<x.y.z>.zip` and `SHA256SUMS` from the app's release. Then, in PowerShell, in that folder:

```powershell
(Get-FileHash wp-test-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-test-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-test-v<x.y.z>\install.ps1
```

Once it is installed, the installer asks whether to remove the download (the zip, its `SHA256SUMS` and the unpacked
folder): a second download would otherwise be saved as `SHA256SUMS (1)` beside the old one.

It installs for your own user, not as administrator: the program in
`%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\app`, a Start-menu entry in the Windows Portable Suite
folder and a Desktop shortcut. Python and Qt come with the program, so there is nothing else to install. The program
is not signed, so Windows may ask once whether to run it.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and the reports stay |
| `--uninstall --purge` | also remove the settings, the log and the reports |

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\apps\test\run.ps1             # full screen
windows-portable\apps\test\run.ps1 --windowed  # in a window
```

The settings are in `%APPDATA%\windows-portable-suite\windows-portable-test.ini`, the log and the saved device
reports in `%LOCALAPPDATA%\windows-portable-suite\windows-portable-test\`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
