<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![sFTP Tools](../images/apps/sftp.webp){ .app-logo }

# sFTP Tools

Moves files between the handheld and another computer over **SFTP**, the file transfer of SSH, and starts or stops
that computer's SSH server. It is the BC250 Bazzite Suite's
[SFTP Tools](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/sftp/) made for the handheld: a BC-250
on Bazzite is the obvious other side, but any computer with an SSH server will do (a NAS, a Linux PC, a Raspberry
Pi). Uploads and downloads wait their turn in a queue, while you go on browsing.

sFTP Tools is on the [portal](../portal.md)'s **Utilities** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **sFTP Tools**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## What you need

- **The other computer's SSH server** (`sshd`) running, and its firewall open for it. On a Bazzite host, once, in a
  terminal: `sudo systemctl enable --now sshd`, and `hostname -I` prints the address to connect to. The BC250
  suite's wiki has the [whole setup](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/sftp/#set-up-the-host),
  password logins included.
- **Your account on it**: its user name, and its password or a key.
- Both on a network you trust. Do not forward port 22 from your router to the internet.

The app is the client; nothing is installed on the other computer.

## The screen

Six cards on the left, **Connection**, **Server's files**, **This device**, **Transfers**, **SSH server** and
**Settings**; the right side shows what the focused card does. The d-pad or the left stick moves the amber focus.
Every action is a button, listed in the row at the bottom with what it does where the focus is: **A** included.
Press the button, or tap the entry. **B** goes back: a folder up, or from a list to its card. **⧉** (View) exits
the app; while a transfer runs or waits, it asks for a second press. **☰** (Menu) opens the information of the pane
that shows; the **information icon** at a pane's top right does the same by touch. Nothing is grayed out: when a
button cannot do its job now, pressing it says why on the pane's status line. Nothing connects before you press
**X**.

## Connection

A row per field, as the BC250 app's form has them: **Host**, **Port** (22), **User**, **Password** and **Key**.

- **A Change** on the host, the port, the user name or the password opens a page with its field. **R3** (the right
  stick pressed) opens Windows' touch keyboard, or closes it; **X Paste** puts in what you copied on the handheld.
  **A Keep** keeps it, **B** goes back without.
- **A Next key** on the Key row steps through the private keys in `%USERPROFILE%\.ssh` (an `id_ed25519`, or a file
  with a `.pub` beside it). With none chosen, the default keys and the SSH agent are used. With a key, the password
  is its passphrase.
- **X Connect** connects, and **X Disconnect** disconnects again (on a second press while transfers run: they stop).

The first time, the app shows the server's key, such as `ED25519 SHA256:…`. Compare it with the server's own:
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` on the server. When it is the same, **X Trust and connect**
adds it to `%USERPROFILE%\.ssh\known_hosts`, which Windows' own `ssh` uses too, and connects. The app never removes
a key from it.

A server you connected to is remembered under the fields, with its host, port, user name and key: **A Fill in**
puts it in the fields, **Y Forget** forgets it on a second press. A password is kept until the app closes and is never
saved. As in the BC250 app, a password without a key needs at least 8 characters, a capital, a number and a special
character, or the app does not connect.

## Server's files

The server's folders, from your home there, which the app shows as `~` (`~/Games`). Folders come first, with a
**›**; files show their size.

- **A Open** opens a folder; **A Download** on a file downloads it.
- **X Download** downloads the folder the focus is on, with everything in it.
- **Y Delete** deletes the file or folder on the server, on a second press within five seconds.
- **B** goes a folder up, and from your home back to the card. The **‹** row at the top goes above your home.

A download goes to the folder open on the **This device** card, and to your Downloads folder while that card shows
the places. The characters Windows does not allow in a name (`< > : " | ? *`) become `_`.

## This device

Your Downloads, Documents and Desktop folders (those that are there, and Games when you have one), then every
drive: an SD card, a USB stick.

- **A Open** opens a folder; **A Upload** on a file uploads it to the folder open on the Server's files card.
- **X Upload** uploads the folder the focus is on, with everything in it.
- **Y Delete** deletes the file or folder from the handheld, on a second press within five seconds.
- **B** goes a folder up, and from the places back to the card.

The places themselves are only opened: a whole place or drive is not uploaded or deleted. The app remembers the
folder you were in.

## Transfers

Every upload (**↑**) and download (**↓**), one at a time, in the order you asked for them: how far the running one
is, in percent, and its speed. Browsing and the SSH server card work meanwhile.

- **A Try again** on a failed one queues it again.
- **X Clear finished** takes the done and the failed ones off the list.
- **Y Stop all** stops the running one and the waiting ones, on a second press. A file half moved stays as it is.

Transfers also stop when the connection ends or the app closes. With **Sound when a transfer is done** on, Windows'
own sound plays when one is done.

## SSH server

The SSH server (`sshd`) of the computer you are connected to: a Linux with systemd, such as Bazzite on a BC-250.

- **A Read the state** asks whether it runs.
- **X Start sshd** starts it; **X Stop sshd** stops it, on a second press. The connection you are on stays, but no new
  one can be made until `sshd` is started again on that computer.
- **Y sshd_config** shows `/etc/ssh/sshd_config` to scroll through with the d-pad; **B** goes back. Change it on the
  computer itself (or with the BC250 app's Server Manager).

Starting and stopping need `sudo` without a password on that computer (`sudo -n`). When it asks for one, the app
shows the error and nothing changes.

## Settings

**A** steps a setting to its next value. It counts from the next transfer, compression from the next connection.

| Setting | Default | What it does |
|---|---|---|
| If a file is there already | Skip it | Skip it, or overwrite it. |
| Hidden files | Not shown | Names that start with a dot, and Windows' hidden and system files. |
| Speed limit | None | 1, 5, 10 or 50 MB/s for each transfer. |
| Downloaded files | The server's times | A downloaded file keeps the time the server has for it, or gets the time of the download. |
| Compression | On | zlib compression on the connection: faster for text, no help for pictures or videos. |
| Sound when a transfer is done | On | Windows' own sound. |

The last row, **The app's log**, shows the log in the pane: the d-pad scrolls it, **B** goes back. The log never
holds a password, a host or a user name.

## Install it on its own

The portal installs it. To install it on its own, download `wp-sftp-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-sftp-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-sftp-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-sftp-v<x.y.z>\install.ps1
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
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-sftp\app\` | The program, `sFTP-Tools.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-sftp\windows-portable-sftp.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-sftp.ini` | The settings, the fields and the servers remembered (never a password) |
| `%USERPROFILE%\.ssh\known_hosts` | The servers' keys you trusted, shared with Windows' own `ssh`; never removed by the app |
