<!-- SPDX-License-Identifier: GPL-2.0-only -->

![Bazzite NetcatGUI](../assets/ncgui/bazzite-netcatgui.webp){ .app-logo }

# Bazzite NetcatGUI

NetcatGUI is the network "swiss army knife" netcat (`nc`) with a window instead of a terminal, on a **BC-250**
running **Bazzite** or any other Linux desktop. Every tab is one session: a **Connect** tab talks to a host and
port, a **Listen** tab waits on a port for someone to connect. What you type is sent as bytes, what comes back is
shown in the log. TCP, UDP or TLS, per tab.

Use it to poke at a service (type an HTTP request by hand, talk to a game server's text port), to see what a
device on the network sends, or to pass lines between two machines. The app does not change how the board runs:
nothing is installed system-wide and nothing is layered with `rpm-ostree`.

## What it needs

- Python 3.10 or newer: Bazzite ships `python3`. The installer makes the app's own virtual environment with PyQt6
  in it (the wheel bundles Qt), so nothing else is needed.
- A port the firewall lets through, when another machine is to reach a Listen tab. On Bazzite:
  `sudo firewall-cmd --add-port=4444/tcp` opens one until the next reboot.

## Install

In the [portal](../portal.md), open the **Development** tab and click the Install button beside its icon. Or by hand:
from the suite's [Releases](https://github.com/RobertoTorino/nexus/releases) page, download the
`ncgui-v<version>.tar.gz` release and extract it. Run `install.sh` as your own user, without `sudo`:

```shell
./install.sh
```

It installs:

- `~/.local/share/bazzite-netcatgui/app`: the app, and `venv` next to it with PyQt6.
- `~/.local/bin/bazzite-netcatgui`: starts the window.
- An app menu entry ("Bazzite NetcatGUI", under Network) and an icon on the Desktop.
  `./install.sh --no-desktop-shortcut` leaves the Desktop icon out.

Install it again to update. Uninstall it in the portal, or with `./install.sh --uninstall`: that removes the app,
the venv, the launcher and the menu entry, and keeps your settings; `./install.sh --uninstall --purge` removes
those too.

**Steam Game Mode:** add `~/.local/bin/bazzite-netcatgui` as a non-Steam game (Steam → Games → Add a
Non-Steam Game → Browse) to start it from the Deck UI. The window is resizable and works with touch.

## Using it

The first line shows the app's logo, its name and version, and the four buttons: **New Connect Tab**, **New
Listen Tab**, **Save Log** and **Clear Log**. The window opens with one empty Connect tab. Every tab has the same
three parts: the header with the address, the port, **TCP**, **UDP** or **TLS** and the start button; the log in the
middle; the message box with **Send** at the bottom. The status bar says what the current tab is doing, and the
encoding and line ending it uses.

### A Connect tab

Type the hostname (a name or an IP address) and the port, pick TCP, UDP or TLS, and press **Connect** (or
Ctrl+O). The tab is named after the host and port once connected. **Disconnect** closes the connection; when the
other side closes it, the status bar says "Disconnected by peer". A connection that is refused, or a name that
cannot be looked up, shows a message. With UDP there is no connection to make: the tab is "Connected (UDP)" at
once, and each message goes out as one datagram; a "connection refused" after a send means nothing listens on
that port. **TLS** is TCP with encryption, for an HTTPS, IMAPS or SMTPS port: the certificate is checked, and
when it cannot be verified (self-signed, expired, another name) the app shows why and asks whether to connect
anyway.

**Reconnect Automatically** (Session menu) makes a Connect tab connect again three seconds after the connection
drops or fails, again and again, until you press Disconnect. Use it for a server that restarts, or to wait for
one to come up: the status bar counts down and no message boxes interrupt. The setting is remembered for new
tabs.

### A Listen tab

Pick the interface (`0.0.0.0` is every interface, the default; `127.0.0.1` only this machine), type the port and
press **Listen**. The tab is named after the address and port. With TCP, one client at a time is taken: the
status bar shows its address, **Send** goes to it, and the button turns into **Disconnect**, which drops the
client and keeps listening for the next; a second client that connects while one is there is turned away.
**Stop** (the same button with no client) stops listening. Ctrl+D does the same, one step at a time. With UDP
the tab shows every datagram that arrives; **Send** answers whoever sent the last one, so a message must arrive
before you can send. Ports below 1024 need root, which the app does not have: use a port above it. A Listen tab
has no TLS: that would need a certificate of its own.

### Messages

Type in the message box and press **Enter** (or the Send button, or Ctrl+M from anywhere): the text is sent and
the box empties. **Shift+Enter** makes a new line inside the message. An empty message is not sent. **Up** and
**Down** in the box walk through the messages you sent before in this tab, like a shell's history (on a message
of several lines they move the cursor first; the history takes over on the first and the last line); what you
were typing comes back when you walk down past the last one. The Session menu sets, for the current tab and as
the default for new tabs:

- **End Messages with Newline:** append a line ending to every message, as a terminal would when you press Enter.
  Most text protocols (HTTP, SMTP, IRC, telnet-like consoles) want it. **Line Ending** chooses LF or CRLF; it
  also applies to the line breaks inside a message of several lines.
- **Encoding:** how the text is turned into bytes, and received bytes into text: UTF-8 (the default), Latin-1
  (one byte per character, so it also shows binary-ish data without losing bytes), or the system's locale.
  A character the encoding does not have is sent as `?`; a byte that is not valid text is shown as `�`.
- **Echo Sent Messages in the Log:** show what you send in the log, between what is received. Off by default,
  as in the C++ tool.

Received data is shown as it arrives. The log shows CRLF and CR as a line break; **Save Log** (Ctrl+S) writes the
current tab's log to a text file with a short header, **Clear Log** (Ctrl+K) empties it. The Edit menu's Copy,
Paste and Select All act on the log or, when it has the focus, on the message box.

**Insert Protocol Template** (Edit menu) puts the opening lines of a conversation in the message box: an HTTP
`GET /` or `HEAD /` with the tab's hostname filled in, SMTP `EHLO`, POP3 `CAPA`, IMAP `CAPABILITY`, FTP
`USER anonymous`, IRC `NICK` and `USER`, Redis `PING`, memcached `stats`. The tab is switched to "End Messages
with Newline" and CRLF, which they all expect; press Enter to send. **Highlight Protocol Lines** (Session menu,
on by default) colours the lines text protocols produce: requests and commands green, status and reply lines
orange, error replies (HTTP 4xx and 5xx, SMTP and FTP 4xx and 5xx, `-ERR`, `ERROR`) red, header names blue.
Plain data stays as it is.

### Bytes, not text

**Hex View** (Session menu, Ctrl+H) shows the log as a hexdump instead of text: each chunk as it arrived, with a
`<<` line saying how many bytes, then the offset, the bytes in hex and the printable characters. With Echo on,
sent chunks appear with `>>`. Switching back and forth shows everything received so far the other way; Save Log
writes what is shown. **Hex Input** (Ctrl+Shift+H) makes the message box take bytes as hex digits instead of
text: `48 65 6c 6c 6f 0a`, with or without spaces, colons, `0x` or `\x`. A message that is not valid hex is
refused and stays in the box for correction. Both are per tab and off when a tab opens.

### Pipes: to a file, from a file, to another tab

- **Save Received Data to File…** (File menu) appends every byte the tab receives from then on to a file you
  choose, as it is, without the text conversion of the log: what `nc > file` does. The status bar shows the file
  name; untick the menu entry to stop. The file keeps what it had; a second run appends.
- **Send File…** (File menu, Ctrl+Shift+F) sends a file's bytes through the connection, as they are: what
  `nc < file` does. The status bar reports the byte count. The file is not shown in the log, even with Echo on.
- **Pipe Received Data To** (Session menu) sends everything this tab receives from then on out through another
  tab's connection, as it is: what `nc A | nc B` does, between two tabs. Pick the other tab in the submenu, or
  None to stop; the status bar shows the pipe. The receiving tab keeps showing the data in its own log. For both
  directions, set the pipe on both tabs: data that arrives on tab B is piped to tab A and the other way round.
  When the other tab has no connection at that moment, the data is shown but not passed on. Closing a tab
  removes the pipes that point to it.

### Recording and replay

Every message a tab sends is recorded with the time it went out. **Save Session Recording…** (File menu) writes
these to a `.ncrec.json` file: the bytes as hex and the pause before each message. **Replay Recording…** sends
such a file through the current tab's connection with the original pauses; the status bar counts the messages,
and Disconnect stops a replay. Use it to repeat a login sequence, a handshake or a test script against another
host. Files sent with Send File are part of the recording.

### Tabs

Right-click a tab handle for **New Connect Tab**, **New Listen Tab**, **Rename Tab…**, **Tab Color**, **Close
Tab**, **Close Other Tabs** and **Close All Tabs**; the empty part of the tab bar offers the two New entries. The
same lives in the Tabs menu. **Rename Tab…** (F2) gives a tab a title of your own that stays while the session
connects and disconnects; an empty title brings the session's own name back. **Tab Color** colours the title, to
group tabs by eye; None removes it. Titles and colours are not saved between runs.

### Keyboard shortcuts

| Keys | What |
| --- | --- |
| Ctrl+T | new Connect tab |
| Ctrl+L | new Listen tab |
| F2 | rename the tab |
| Ctrl+W, Ctrl+Shift+W | close the tab, close all tabs |
| Ctrl+Tab, Ctrl+Shift+Tab | next tab, previous tab |
| Ctrl+O | connect, or listen, on the current tab |
| Ctrl+D | disconnect; on a Listen tab drop the client, then stop listening |
| Enter, Shift+Enter | send the message, new line in the message |
| Up, Down | earlier, later message in the message box |
| Ctrl+M | send the message from anywhere in the window |
| Ctrl+Shift+F | send a file |
| Ctrl+H, Ctrl+Shift+H | hex view, hex input |
| Ctrl+S, Ctrl+K | save the log, clear the log |
| Ctrl+A, Ctrl+C, Ctrl+V | select all, copy, paste |
| Ctrl+Q | quit |

Help → Keyboard Shortcuts shows the same list in the app.

## Examples

### Fetch a web page by hand

See exactly what a web server answers, headers and all.

1. Press Ctrl+T for a Connect tab. Hostname `example.org`, port `443`, protocol **TLS** (for a plain HTTP site:
   port `80`, **TCP**). Press **Connect**; the status bar says "Connected (TLS)".
2. Edit → Insert Protocol Template → **HTTP GET /**. The message box now holds the request with
   `Host: example.org`; the tab is set to end messages with CRLF.
3. Press Enter. The log shows `HTTP/1.1 200 OK`, the headers (names in blue) and the page. The server closes
   the connection when it is done: "Disconnected by peer".
4. Ctrl+S saves the whole exchange to a text file; Ctrl+H shows it as bytes.

Change the first line of the template to `GET /robots.txt HTTP/1.1` before pressing Enter to ask for another
page; Up brings the request back after it was sent.

### Send a file from the BC-250 to a PC

No shared folder, no SSH set up: a Listen tab on the PC and a Connect tab on the board, or the other way round.
Any netcat on the other side works too (`nc -l 4444 > file` on Linux).

1. On the receiving machine, Ctrl+L for a Listen tab, interface `0.0.0.0`, port `4444`, **Listen**. Open the
   port in the firewall when the machine has one (`sudo firewall-cmd --add-port=4444/tcp` on Bazzite). Then
   File → **Save Received Data to File…** and pick where the file should go; the status bar shows its name.
2. On the sending machine, Ctrl+T, the receiver's IP address, port `4444`, **Connect**. The receiver's status
   bar shows "Connected (client …)".
3. File → **Send File…** (Ctrl+Shift+F) and pick the file. The status bar reports the byte count.
4. On the receiver, untick Save Received Data to File, then press **Disconnect**: the file is complete.

With a Listen tab on each side and a Connect tab on each side, the two machines also chat: type on one, read on
the other, in both directions.

### Watch a device that talks on the network

A printer, a sensor or a game console that sends status lines, or a service you want to see talking to a client.

- To see what a device sends to a port: Ctrl+L, the port it sends to, **UDP** when it sends datagrams,
  **Listen**. Every line shows up as it arrives; **Send** answers the last sender. Switch on Reconnect
  Automatically for a Connect tab to a device that reboots: the tab reconnects by itself.
- To sit between a client and a server and see both sides: a Listen tab on the port the client uses, a Connect
  tab to the real server, and a pipe each way (Session → Pipe Received Data To, on both tabs). Point the client
  at this machine. Each tab's log shows one direction; Hex View shows the bytes when the protocol is not text.
- To repeat a login or a handshake later: do it once by hand, File → Save Session Recording, and Replay
  Recording on a fresh connection sends it again with the same pauses.

## From the terminal

```bash
bazzite-netcatgui                      # the window with an empty Connect tab
bazzite-netcatgui example.org 80       # a Connect tab to example.org port 80, connected
bazzite-netcatgui -l 4444              # a Listen tab on port 4444, listening
bazzite-netcatgui -u -l 4444           # the same with UDP
```

The arguments follow `nc`: `host port` connects, `-l port` listens, `-u` makes that tab UDP. Everything else
happens in the window. The window opens once: when it is already open, the command opens its tab there, beside
the others.

## Files

- `~/.config/bazzite-netcatgui/bazzite-netcatgui.ini`: the Session menu's last state (the defaults
  for new tabs: newline, line ending, encoding, echo, reconnect, highlighting), the last twenty hosts and ports
  typed in Connect tabs and ports in Listen tabs (the drop-down lists), the folders of the last saved log,
  file and recording, and the window size.

Nothing else is written unless you save a log, a recording, or received data to a file.

## When something does not work

- **"Connection refused":** nothing listens on that host and port, or a firewall answered for it. With UDP the
  message comes after a send, when the port unreachable answer arrives; some hosts never send one.
- **"Hostname fail":** the name could not be looked up. Try the IP address.
- **"Cannot start listen":** the port is taken by another program, is below 1024, or the interface has no such
  address. Pick another port or `0.0.0.0`.
- **Another machine cannot reach a Listen tab:** the tab listens on `0.0.0.0` (or the machine's own address, not
  `127.0.0.1`), and the port is open in the firewall (see [What it needs](#what-it-needs)).
- **Text comes out wrong:** both sides must use the same encoding. Latin-1 shows every byte as a character and
  loses nothing; Hex View shows the bytes themselves.
- **"TLS handshake failed":** the port does not speak TLS (plain TCP, or STARTTLS, which the app does not do),
  or you answered No to the certificate question.
- **A replay or a pipe sends nothing:** the tab it sends through has no connection at that moment. The status
  bar shows the tab's state; connect first.
- **No window on an X11 session:** PyQt6's X11 plugin needs `libxcb-cursor`; Bazzite's Wayland sessions do not.
  `QT_QPA_PLATFORM=xcb bazzite-netcatgui` or `=wayland` picks the backend by hand.

## How it works

Each tab owns one Qt socket: a `QTcpSocket` or `QSslSocket` (Connect, TCP or TLS), a `QTcpServer` with the one
accepted `QTcpSocket` (Listen, TCP), or a `QUdpSocket` (UDP, connected to the peer on a Connect tab, bound to the
port on a Listen tab). The sockets run in the window's event loop, so nothing blocks and no threads are needed:
data is read when it arrives and appended to the log, and what you send is written straight to the socket. The
code is a port of NetcatGUI's C++ sources (`src/netcatgui.cpp`, `src/widgets/ncsession*.cpp`), with the same
messages where it does the same thing.

## License

GPL-2.0 (the app's `LICENSE`): the license of NetcatGUI by Shinnok (Teodor Mircea Ionita), which this app is a
port of. The icons are from the Silk icon set 1.3 by Mark James, [famfamfam.com](http://www.famfamfam.com/lab/icons/silk/)
(CC BY 2.5).
