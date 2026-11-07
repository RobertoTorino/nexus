<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Support Checker](../images/apps/support.webp){ .app-logo }

# Support Checker

Support Checker shows what the suite's apps need on this handheld besides themselves: whether Windows is up to date,
whether the tools and runtimes the apps use are there, and whether each app is the version the portal brings. It
only looks: it installs and changes nothing.

Support Checker is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **Support Checker**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## The screen

Three cards on the left, each with its pane on the right: **Windows**, **Tools** and **Apps**. The card with the
focus shows its pane; **A** on Tools or Apps goes into its list, where the row with the focus says more under the
list. **Y Check again** runs every check again (it takes a few seconds: Windows lists its updates slowly). **☰**
(Menu) opens the information of the pane that shows.

## Windows

Windows' name, version and build, whether an update waits for a restart, and the newest update Windows installed.
The card says:

| Status | Meaning |
|---|---|
| **Up to date** | No update waits, and Windows installed one within the last 40 days. |
| **Restart to update** | An update is installed and takes effect at the next restart: restart the handheld. |
| **Update late** | The newest update is more than 40 days old (Windows brings one every month): open Settings, Windows Update. |
| **Unknown** | Windows did not say which updates it installed. |

The app reads this from the registry and from Windows' list of installed updates; installing updates stays Windows'.

## Tools

What the installed apps need besides themselves, and which of them uses each:

| Tool | Used by |
|---|---|
| **Windows PowerShell** | The portal: it runs every app's installer. |
| **Microsoft Visual C++ runtime** | RPCS3, shadPS4, Vita3K and Xenia: the emulators do not start without it. |
| **Windows' tar (with 7z)** | The managers of PCSX2, RPCS3, Vita3K and Xenia: it unpacks the emulator's archive; a `.7z` needs Windows 11's. |
| **Steam** | The game managers, Remote Play and the portal's RT; without it a game manager starts a game itself. |
| **XBOX app** | The XBOX menu, which the portal's installer adds the suite to. |

| Status | Meaning |
|---|---|
| **Available** | Found; the line under the list says where. |
| **Missing** | An installed app needs it, and it is not there. The line says how to get it. |
| **Not installed** | Not there, but the installed apps that use it work without it. |
| **Unsupported build** | There, in a form the apps cannot use: a tar that cannot unpack a `.7z` (Windows 10's). |
| **Not needed** | No installed app uses it. |

## Apps

Every app the portal lists, with the version installed against the one the portal brings: **Up to date**, **Update
in the portal** (an older one: the portal's **Y** updates it), **Version unknown** (there, but not installed by the
portal) or **Not installed**. Each app is a program with what it needs inside, tested with it, so an app is brought
up to date as a whole, by the portal.

## Install it on its own

The portal installs it. To install it on its own, download `wp-support-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-support-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-support-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-support-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings and the log stay |
| `--uninstall --purge` | also remove the settings and the log |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-support\app\` | The program, `Support-Checker.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-support\windows-portable-support.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-support.ini` | The settings |
