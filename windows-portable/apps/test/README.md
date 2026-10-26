<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Windows Portable Test

Gets to know a **Windows handheld** (first the ASUS ROG Xbox Ally X): what Windows reports about the device, and
every button, stick and trigger of its controller as you press them. It reads and shows; it changes nothing on the
device.

Made for the handheld in your hands: full screen, the controller moves the amber focus between the cards (A to run,
X to save the device report, B to close), and every card and button also works by touch.

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
