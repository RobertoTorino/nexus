<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BIOS Reader](../images/apps/bios.webp){ .app-logo }

# BIOS Reader

Shows the BIOS's setup screens, the menus with every setting, hidden menus included, from your device's own BIOS or
the BIOS file its maker publishes, with each setting's default and, once you allow it, the value your device has. It
says whether your BIOS is the newest. It only reads: nothing in the file, the BIOS or Windows changes.

BIOS Reader is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **BIOS Reader**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## What you need

- **Nothing, on most devices:** when the maker delivers its BIOS through Windows Update (ASUS does), Windows keeps a
  copy of the BIOS it installed, and the app reads that one.
- **Otherwise the BIOS file of your device**, as its maker publishes it: for the ROG Xbox Ally X, ASUS's download on
  the device's support page, a zip with a file named like `RC73XAAS.319` in it. The app takes the zip itself, that
  file, or a `.cap`, `.bin` or `.rom`. Take the version your device runs: the This device card says which one that is.
- **An administrator's password** (or a yes, when your own user is one) to read your own settings: see This device
  below. Without it the app shows the file's defaults.

The app reads AMI BIOSes (ASUS, MSI and many others): their setup screens and their defaults. Another maker's BIOS
may show its setup screens without their defaults.

## The screen

Three cards on the left, **BIOS file**, **Setup screens** and **This device**; the right side shows what the focused
card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row at the
bottom with what it does on the pane that shows: **A** included. Press the button, or tap the entry. **B** goes
back. **⧉** (View) exits the app. **☰** (Menu) opens the information of the pane that shows; the **information
icon** at a pane's top right does the same by touch. Nothing is read before you press **A**.

## BIOS file

**A This device's BIOS** reads the BIOS your device runs, from the copy Windows keeps of the BIOS it installed (in
Windows' driver store, with no download and no administrator). The app picks the copy of the version Windows says
runs; the card then says **This device's BIOS** with its version. Where Windows keeps no copy (the maker does not
deliver its BIOS through Windows Update, or the BIOS was flashed another way), the pane says so.

**X Pick a file** opens the file browser: your usual folders and every drive. **A** opens a folder or takes the file,
**B** goes a level up; the browser opens where it was left the time before. Once your device's own BIOS is read, **A
Pick another file** opens it. The app reads the file in a few seconds
and shows its name, its version, how many setup screens and settings it has, how many menus the BIOS hides, and its
SHA-256. A file the maker made for another chip (a controller's, a drive's) has no setup screens, and the app says
so.

## Setup screens

The BIOS's pages as its setup screen has them (Main, Advanced, Boot, Security, Save & Exit), then the pages other
parts of the BIOS add (AMD Overclocking, network and storage pages).

- **A** opens a page, and on a line marked **›** the menu it leads to. **B** goes back a menu, from a page to the
  pages, then to the card.
- **LB Page before** and **RB Next page** go to the page before or the next one.
- Each line shows its setting's value. The line under the list says where the value comes from (this device, the
  file, or the default) and the default, in two lines at most; **☰** shows the rest.
- The amber lines are the BIOS's own text between the settings, wrapped to the screen. The d-pad does not stop on
  them: the first setting shows the text above it, the last setting the text after it. A finger drags the list too.
- A line the BIOS names only while it runs (a boot device in **Boot Override**) has no name in the file: a link
  shows the name of the menu it opens, and anything else is left out, as the BIOS leaves its blank spacers empty.
- **!!!! PCI Resource ERROR !!!!** is AMI's page for a boot that runs out of PCI resources. Every BIOS file holds it,
  and the BIOS shows it only in that case. It is not an error on your device, and the line under its title says so.
- **☰** shows the whole of the focused line: its help, why it is hidden, its value and default, its options and where
  the BIOS stores it (for example `AmdSetup + 0x25F, 4 bytes`).
- **Y Show hidden** also lists what the BIOS does not show, dimmed and in italics: settings and menus hidden always,
  hidden by the value of another setting, or menus no menu leads to. Those last ones are on the extra page **Not
  linked**. **Y Hide hidden** hides them again.

Nothing can be changed: **A** on a setting says so.

## This device

**A Read** reads the BIOS your device runs, as Windows reports it: the device, the BIOS version, its date and its
maker, and whether the BIOS file is that version. No administrator is needed for this.

On an ASUS device it also asks ASUS's support site for the newest BIOS of the device. The card then says **BIOS
RC73XA.319, up to date**, or which version is out (**BIOS RC73XA.317: 319 is out**), and the pane shows the newest
version with its date. Only the model the BIOS version starts with (`RC73XA`) goes to the site. Offline, or on
another maker's device, the pane says the newest is not known.

With a BIOS file read, **A Read the settings** reads your device's own settings. Windows keeps them for an
administrator, so it asks (its prompt may open behind the app); this is the app's only step as administrator, and it
only reads. The setup screens then show your device's values where it has them. A BIOS keeps many of its settings to
itself once Windows runs (AMI's main Setup variable, for one): those show the file's default, and the pane says how
many were read and how many the BIOS kept. **A Read again** reads them anew, with another prompt.

The app never reads a variable that may hold personal data: Wi-Fi networks, network and boot entries, keys and
passwords. Values are not written to the log; the log only counts them.

When the file is another version than your device's BIOS, the pane says so: a setting may sit elsewhere in another
version, so a value read may be wrong. Take the file of the version your device runs.

## Install it on its own

The portal installs it. To install it on its own, download `wp-bios-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-bios-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-bios-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-bios-v<x.y.z>\install.ps1
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
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-bios\app\` | The program, `BIOS-Reader.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-bios\windows-portable-bios.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-bios.ini` | The settings |
