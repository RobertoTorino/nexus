<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

![Remote Play](../images/apps/rplay.webp){ .app-logo }

# Remote Play

Finds your **PS4** and **PS5** on the network, registers the handheld with them, wakes them from rest mode and tests
a Remote Play session with them. It is the BC250 Bazzite Suite's
[Console Link](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/consoles/) made for the handheld: its
search, registration, wake-up, test session and rest mode, with the same protocol code.

Remote Play is on the [portal](../portal.md)'s **Gaming** tab: **A** on its tile installs it, and once it
is installed, **A** opens it. It is also in the Start menu (**Windows Portable Suite**, **Remote Play**). It opens full
screen; **B** goes back and **⧉** (View) exits it.

## What you need

- **Remote Play on the console:** Settings > System > Remote Play > Enable Remote Play.
- **To wake it from rest mode:** on a PS5, Settings > System > Power Saving > Features Available in Rest Mode:
  switch on **Stay Connected to the Internet** and **Enable Turning On PS5 from Network**. A PS4 has the same two
  switches under Settings > Power Saving Settings > Set Features Available in Rest Mode.
- **The same network:** the handheld and the console in one local network. Remote Play over the internet is not
  part of this app.
- **Your PSN account ID:** the number of your PlayStation Network account, not your online name. PlayStation does
  not show it anywhere; the sign-in on the Register card reads it (see below). The app also takes the number itself
  (for example `4782394583276428394`) or the 12-character code that ends with `=`, as other Remote Play apps show
  it. It is the same for every console you register with this account.

The first search may make Windows ask whether Remote Play may use the network: allow it for **private networks**,
the kind your home network is.

## The screen

Four cards on the left, **Consoles**, **Register**, **My consoles** and **Settings**; the right side shows what the
focused card does. The d-pad or the left stick moves the amber focus. Every action is a button, listed in the row at
the bottom with what it does where the focus is: **A** included. Press the button, or tap the entry. **B** goes
back, from a list to its card. **☰** (Menu) opens the information of the pane that shows; the **information icon**
at a pane's top right does the same by touch. Nothing is grayed out: when a button cannot do its job now, pressing
it says why on the pane's status line. Nothing searches before you press **X**.

## Consoles

The consoles that answered the search, each with its name, model, address, state (**On** or **Rest mode**) and
whether the handheld is registered with it.

- **X Search the network** asks every PS4 and PS5 on the network. A console that is on, or in rest mode with
  Remote Play on, answers within two seconds.
- **A Change** on the **Search an address** row opens a page with its field, for a console the search does not find
  (in another part of the network). The console shows its address under Settings > Network, View Connection Status.
  **Y Search the address** asks that address only; the consoles found before stay on the list.
- **A Register** on a console chooses it on the Register card. **A My consoles** on a console the handheld is
  registered with goes to it there.

When a registered console answers at another address (the router gave it a new one), the app keeps the new one.

## Register

Registering lets the handheld wake the console and start Remote Play with it, as the PSN account it is registered
for. A row per thing it needs:

- **Console:** the console chosen on the Consoles card; **A Next console** steps through the ones found that the
  handheld is not registered with yet.
- **Account ID from the PlayStation sign-in:** **A Sign in** opens the official PlayStation sign-in in your browser.
  Sign in with the PSN account you use on the console. The sign-in then shows a page that only says "redirect":
  copy that page's address from the browser's address bar, and the app takes it from there by itself. It sends the
  code in that address to PSN once, keeps only the account ID, and fills it in. The code works for a few minutes.
  Go back to the app (it may already show the account ID).
- **Account ID:** **A Change** opens a page with its field, to type the ID or paste it.
- **PIN:** on a PS5, open Settings > System > Remote Play > **Link Device**; on a PS4, Settings > Remote Play
  Connection Settings > **Add Device**. The console shows an 8-digit PIN for a few minutes. **A Change** opens the
  page to type it.

On a field's page, **R3** (the right stick pressed) opens Windows' touch keyboard, or closes it; **X Paste** puts in
what you copied on the handheld. **A Keep** keeps it, **B** goes back without.

**X Register** registers the handheld with the console while the console shows the PIN. The PIN is used once and
never saved; the console then lists the handheld under Link Device (PS5) or Add Device (PS4).

## My consoles

The consoles the handheld is registered with, each with its name, model, its state at the last search and whether a
login passcode is set. The line under the heading tells more about the console the focus is on: its model (a PS4
Pro shows as one after a session), a PS4's system software, what runs on it, and its Remote Play version.

- **A Wake** wakes the console from rest mode. It takes about 20 seconds; a search then shows it as On.
- **X Test session** starts a session with the console and closes it again after three seconds: it proves the
  registration and the connection.
- **RB Rest mode** puts the console in rest mode through a short session, on a second press within five seconds: a
  game on it stops.
- **LB Login passcode:** when the PSN account on the console has a 4-digit login passcode, the console asks for it
  when a session starts. Type it on the page that opens; leave the field empty to remove it.
- **Y Remove** forgets the console, on a second press within five seconds. To use it again, register again. A PS5
  still lists the handheld under Link Device: remove it there too.

## Settings

**A** changes a setting.

| Setting | Default | What it does |
|---|---|---|
| Personal details | Hidden | Your PSN account ID, your online ID and the consoles' addresses, masked on the screen: the account ID shows only its last four characters, an address only its last part (`•••.•••.•••.20`), the online ID nothing at all. **Shown** shows them in full. |

The last row, **The app's log**, shows the log in the pane: the d-pad scrolls it, **B** goes back. The log always
masks the personal details, whatever the setting.

## Privacy

What the app sends, and to whom:

- **To your consoles, on your own network:** the account ID once, when you register; after that the keys from
  registration, to wake the console and start a session.
- **To PlayStation (PSN), only with the sign-in:** the one-time code from the sign-in, once, to read your account ID
  and online ID. The sign-in itself happens in your browser; the app never sees your password.
- **Nobody else.** The app has no statistics, no crash reports and no connection to anything but your consoles and,
  on that one row, PSN.

The consoles' names (PS4-728, Living room PS5) are not masked: check them before you share a log if you gave a
console your own name. The online ID is not kept.

## When it does not work

- **The search finds nothing:** check that Remote Play is on, and that the console is on or in rest mode with the
  two rest-mode switches on. Try **Search an address** with the console's address. When Windows asked whether the
  app may use the network and it was not allowed, allow it in Windows Security > Firewall & network protection >
  Allow an app through firewall.
- **Registration: no answer:** the PIN screen (Link Device on a PS5, Add Device on a PS4) must be open on the
  console while you register, and the PIN is only valid for a few minutes.
- **The console was switched off completely:** Wake and the test session only reach a console that is on or in rest
  mode with the two rest-mode switches on (see [What you need](#what-you-need)).
- **Remote Play is already in use:** another device has a session with the console. Close it there.
- **The console asks for the login passcode:** set it with **LB Login passcode** on My consoles.

## Install it on its own

The portal installs it. To install it on its own, download `wp-rplay-v<x.y.z>.zip` and `SHA256SUMS` from its release,
then in PowerShell, in that folder:

```powershell
(Get-FileHash wp-rplay-v<x.y.z>.zip).Hash -eq (-split (Get-Content SHA256SUMS))[0]   # True: the download is intact
Expand-Archive wp-rplay-v<x.y.z>.zip . -Force
powershell -ExecutionPolicy Bypass -File wp-rplay-v<x.y.z>\install.ps1
```

Installed on its own, it gets a Start-menu entry and a Desktop shortcut. Afterwards the installer asks whether to
remove the download.

| Option | |
|---|---|
| `--no-desktop-shortcut` | the Start-menu entry only |
| `--uninstall` | remove the app; the settings, the log and the registered consoles stay |
| `--uninstall --purge` | also remove the settings, the log and the registered consoles with their keys |

## Files

| Where | What |
|---|---|
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rplay\app\` | The program, `Remote-Play.exe` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rplay\consoles.json` | The registered consoles and their keys: with them anyone on your network could start a session as your account, so share it with nobody. Kept on this device only, not in the roaming `%APPDATA%` |
| `%LOCALAPPDATA%\windows-portable-suite\windows-portable-rplay\windows-portable-rplay.log` | The log |
| `%APPDATA%\windows-portable-suite\windows-portable-rplay.ini` | The settings, the account ID and the address searched last |

## License

AGPL-3.0. The protocol code is ported from [chiaki-ng](https://github.com/streetpea/chiaki-ng) (AGPL-3.0-only with an
OpenSSL exception), through Console Link; the README in the app's folder says which files.
