<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Console LinkB](../assets/clb/bc250-console-linkb.webp){ .app-logo }

# Console LinkB

Console LinkB brings Xbox games to the **AMD BC-250**. Sign in with your Microsoft account, and the app lists your
Xbox consoles and the games of Xbox Cloud Gaming you may play. Stream your own Xbox to the board (Microsoft calls
this Remote Play), or play a game from the cloud.

The app does not change how the board runs. It talks to Microsoft's Xbox services only when you sign in, refresh,
wake a console or stream.

## What you need

- **A Microsoft account with an Xbox profile.** An account that never signed in to Xbox gets its profile by signing
  in once on [xbox.com](https://www.xbox.com).
- **For your own Xbox (Xbox One or Xbox Series X|S):** remote play switched on, on the console: Settings > Devices &
  connections > Remote features > **Enable remote features**. To wake it from the board, the console's power mode
  must be **Sleep** (Settings > General > Power options); a console that is shut down cannot be woken over the
  network. The console and the board need not be on the same network, but a stream at home is the steadiest.
- **For Xbox Cloud Gaming:** with **Game Pass Ultimate** you can play its cloud games. Without it, the app lists the
  games that are free to play in the cloud, such as Fortnite. Xbox Cloud Gaming is not open in every country.
- **A controller on the board:** connected by USB cable or paired over Bluetooth with the board, not with the Xbox.
  Any controller the system knows will do (an Xbox controller, a DualSense, a Steam Deck's controls). An Xbox
  controller that is paired with the console connects to the console when you press its Xbox button, so pair it
  with the board. The keyboard works as a controller too (see below).
- **A good connection:** for the cloud, Microsoft advises at least 20 Mbit/s; a cable or 5 GHz Wi-Fi is best.

## Using it

The boxes at the top show the account (your gamertag), how many consoles the account has, and which cloud games
it may play (**Game Pass** or **Free to play**).

**1 Microsoft account:**

- **Sign in:** the app asks Microsoft for a code and shows it with the address
  [microsoft.com/link](https://www.microsoft.com/link). Open that address on a phone or any computer, enter the code
  and sign in there. The window goes on by itself once you are signed in. The code is valid for 15 minutes;
  **Cancel** stops waiting. You sign in on Microsoft's own page, so the app never sees your password.
- **Sign out:** forgets the account on this board.

The app stays signed in after it closes, so you sign in once.

**Consoles** (the first tab) lists the account's consoles with their model, their power state (**On**, **Sleep** or
**Off**) and whether remote play is on.

- **Wake:** wakes the selected console from sleep. Give it a few seconds, then **Refresh** or **Stream**.
- **Stream** (or a double-click): streams the console to the board.

**Cloud games** (the second tab) lists the games the account may play from the cloud, by name. Type in **Find a
game** to narrow the list. **Stream** (or a double-click) starts the selected game. When many people play, the
cloud may put you in a queue first: the stream's window shows the expected wait.

**Refresh**, at the top right, asks Xbox Live for the consoles and the cloud games again.

## The stream

The stream opens full screen: the picture scaled to fit, the sound on the board's default output, and the first
controller connected as the Xbox's controller, with its rumble. Only one stream runs at a time.

- **F11** switches between full screen and a window.
- **Leave the stream:** hold **View** and **Menu** on the controller for two seconds, press **Ctrl+Q**, or close
  the window. The session ends with Microsoft too, so the console goes back to its home screen and a cloud server
  is freed.
- **The keyboard as a controller:** the arrow keys are the d-pad, **Enter** is A, **Backspace** B, **X** and **Y**
  their buttons, **Tab** View, **M** Menu and **Home** the Xbox button.
- When a game asks something in a dialog (for example whether to quit), the app shows it and sends your answer.

## Where it keeps what

- `~/.config/bc250-console-linkb/account.json`: the sign-in, so the app stays signed in. Anyone with this file can
  use your account with the Xbox services, so it is readable only by you. **Sign out** removes it.
- `~/.config/bc250-console-linkb/bc250-console-linkb.ini`: the window size.

## Privacy

What the app sends, and to whom:

- **To Microsoft, when you sign in:** the code request and, while you sign in on Microsoft's page, the question
  whether you did. The sign-in itself happens in your browser.
- **To Microsoft's Xbox services, when you refresh, wake or stream:** the account's tokens, to list your consoles
  and the cloud games, to wake a console, and to start and keep a stream. The stream itself carries your
  controller's input to the console or the cloud server, and the picture and sound back.
- **Nobody else.** The app has no statistics and no crash reports.

The app's log masks personal details: the account's tokens are never shown, your gamertag is hidden, a console's
ID shows only its last four characters and a network address only its last part. The consoles' names (Living room)
are not masked: check them before you share a log if you gave a console your own name.

## When it does not work

- **Signing in says the account has no Xbox profile:** sign in once on [xbox.com](https://www.xbox.com), then sign
  in again here. A child account needs an adult to add it to a Microsoft family first.
- **The app says to sign in again:** Microsoft no longer accepts the saved sign-in (after a password change, or a
  long time unused). Sign in again with a new code.
- **No consoles:** the console must be signed in with the same account. Check remote features on the console (see
  [What you need](#what-you-need)), then **Refresh**.
- **Wake does nothing:** the console's power mode must be **Sleep**, not shut down, and remote features must be on.
- **Remote play is off:** switch it on on the console (see [What you need](#what-you-need)).
- **No cloud games:** Xbox Cloud Gaming is not open to the account, or not in its country. The free-to-play games
  need no Game Pass, only the account.
- **The stream ends with "the connection to the stream was lost":** the network between the board and the console
  or the cloud dropped. A cable, or a 5 GHz Wi-Fi close to the router, helps.
- **No sound:** the sound goes to the board's default output; choose the output in the system's sound settings.
- **The controller does nothing:** check that it is connected to the board and not to the Xbox. The keyboard
  works as a controller in the meantime.

## Install and remove

The portal installs it, under Gaming. By hand, from the extracted release folder:

```bash
./install.sh                         # install or update
./install.sh --no-desktop-shortcut   # app menu entry only, no icon on the Desktop
./install.sh --uninstall             # remove the app; keeps its settings and the signed-in account
./install.sh --uninstall --purge     # also remove its settings and forget the account
```

The app has its own Python environment in `~/.local/share/bc250-console-linkb/venv`, with PyQt6, aiortc (the
stream's WebRTC, with PyAV for the video and sound) and pygame-ce (the controllers).

## Disclaimer

Console LinkB is an independent project, not affiliated with or endorsed by Microsoft. Xbox, Xbox Cloud Gaming and
Game Pass are trademarks of their owner.

## License

GPL-3.0-or-later. The protocol code is ported from [Greenlight](https://github.com/unknownskl/greenlight) and
[xal-node](https://github.com/unknownskl/xal-node), both MIT, Copyright (c) 2019 and 2023 UnknownSKL (Jim Kroon);
the files ported from them say so in their header, and the app's README keeps the MIT notice. The stream uses
[aiortc](https://github.com/aiortc/aiortc) (BSD-3-Clause) and [PyAV](https://github.com/PyAV-Org/PyAV)
(BSD-3-Clause, its wheels bring FFmpeg, LGPL-2.1-or-later), installed from PyPI.
