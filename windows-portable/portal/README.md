<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Windows Portable Suite

The portal of the **Windows Portable Suite**: it installs, updates, opens and removes the suite's apps on a Windows
handheld (first the ASUS ROG Xbox Ally X), each from its own GitHub release, checked against the checksum the
portal carries. Windows Portable Test is always installed with the portal and listed first.

Made for the handheld in your hands: full screen, the apps as tiles under tabs (LB and RB change the tab), the
amber focus moved by the d-pad, A to install or open the focused app, Y to update it, X for its details (and Remove
there), Menu for the Suite page (the portal's own update), B to close. Every tile and pill also works by touch.

## Install it

Download `wp-portal-v<x.y.z>.zip` and `SHA256SUMS` from the portal's release (the Nexus index on GitHub's Releases
page points at the newest). Then, in PowerShell, in that folder:

```powershell
(Get-FileHash wp-portal-v<x.y.z>.zip).Hash      # compare with SHA256SUMS
Expand-Archive wp-portal-v<x.y.z>.zip .
cd wp-portal-v<x.y.z>
powershell -ExecutionPolicy Bypass -File install.ps1
```

It installs for your own user, not as administrator: the program in
`%LOCALAPPDATA%\windows-portable-suite\portal\app`, a Start-menu entry in the Windows Portable Suite folder and a
Desktop shortcut, and Windows Portable Test from the bundled release through its own installer. Python and Qt come
with the program, so there is nothing else to install. The program is not signed, so Windows may ask once whether to
run it.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entries only |
| `--uninstall` | remove the portal and Windows Portable Test; the other apps stay (it names them); the settings, the log and the records stay |
| `--uninstall --all` | the whole suite: every app the portal installed too |
| `--uninstall --purge` | also remove the settings, the log, the records and the extracted releases |

The apps the portal installs go through their own installers, each from the release its `apps.toml` pins
(`%LOCALAPPDATA%\windows-portable-suite\portal\releases\<tag>\`, kept for the uninstaller), and are recorded in
`installed.json` beside them. The portal's log is `portal.log` there; its settings are in
`%APPDATA%\windows-portable-suite\portal.ini`.

## Start it from the checkout

From the repository's root, with the Windows venv (`.venv-windows`, see the root CLAUDE.md):

```powershell
windows-portable\portal\run.ps1             # full screen
windows-portable\portal\run.ps1 --windowed  # in a window
```

From the checkout the portal installs the apps its `apps.toml` pins from their GitHub releases, as the installed
portal does; it cannot update itself (there is no installed program to replace).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
