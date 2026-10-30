<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Install

Install the **portal** once: it brings Windows Portable Test along and installs every other app of the suite from its
tiles. It needs Windows 10 or 11 (x64). Python and Qt come with each program, so there is nothing else to install.

## Download and install

1. Open the suite's releases on GitHub: the [Nexus index](https://github.com/RobertoTorino/nexus/releases/latest)
   names the newest portal, `wp-portal-v<x.y.z>`.
2. Download `wp-portal-v<x.y.z>.zip` and `SHA256SUMS` from that release.
3. Open PowerShell in the folder you downloaded them to, and run:

```powershell
(Get-FileHash wp-portal-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-portal-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-portal-v<x.y.z>\install.ps1
```

The first line prints `True` when the download is intact. On `False`, download both files again.

Run it as your own user, not as administrator: the installer refuses an administrator's window, since everything goes
in your own folders. The programs are not signed, so Windows may ask once whether to run them.

The installer puts:

- the portal in `%LOCALAPPDATA%\windows-portable-suite\portal\app`;
- a Start-menu entry in a **Windows Portable Suite** folder, and a Desktop shortcut to the portal;
- Windows Portable Test, from the release inside the portal's zip, with its Start-menu entry. It gets no Desktop
  shortcut: you start it from the portal.

## The Xbox menu

On a first install, with the Xbox app on the device, the installer asks whether to add the suite to the Xbox menu:
the Xbox app's library, so Xbox mode starts the portal from its home. Answer **Y** (or press Enter) to add it; the Xbox
app closes for a moment while its library changes and starts again. An update does not ask again, and the portal's
Settings page adds it any time (**Xbox menu: Add**).

## Remove the download

Once the portal is installed, the installer asks whether to remove the download: the zip, its `SHA256SUMS` and the
unpacked folder. Answer **Y** (or press Enter) unless you want to keep them. Your browser saves a second download of
`SHA256SUMS` as `SHA256SUMS (1)`, so an old one left beside it would make the check above read the wrong file.

## Options

Add them to the last line, after `install.ps1`:

| Option | |
|---|---|
| `--no-desktop-shortcut` | the portal's Start-menu entry only, no Desktop shortcut |
| `--xbox-menu` | also into the Xbox menu, without the question |
| `--no-xbox-menu` | not into the Xbox menu, without the question |
| `--uninstall` | remove the portal and Windows Portable Test; the other apps stay (it names them); the settings, the log and the records stay |
| `--uninstall --all` | the whole suite: every app the portal installed too |
| `--uninstall --purge` | also remove the settings, the log, the records and the downloaded releases |

To uninstall, run the installer of the portal you have with `--uninstall`, from a download of the same release or from
`%LOCALAPPDATA%\windows-portable-suite\portal\portal-update\wp-portal-v<x.y.z>\` when the portal updated itself.

## Updates

The portal updates itself and its apps: a newer portal shows as **Suite x.y.z available** at the top. Open the Suite
page (the ☰ button) and press **A** on **Update to x.y.z**. The portal downloads the release, closes, installs it and
starts again. See [Portal](portal.md#the-settings-page).

## Each app on its own

Every app also has a release of its own, `wp-<app>-v<x.y.z>.zip` with a `SHA256SUMS`, installed the same way with its
own `install.ps1`. Installed on its own, an app gets a Desktop shortcut too. The portal is the easier way: it checks
every download against the checksum it carries.
