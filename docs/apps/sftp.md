<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Bazzite SFTP Tools](../assets/sftp/bc250-bazzite-sftp-tools.webp){ .app-logo }

# Bazzite SFTP Tools

SFTP Tools moves files between your computer and another one over SSH, and manages the SSH server (`sshd`) of a
**BC-250** running **Bazzite**. It has two tabs:

- **SFTP Client:** your folders on the left, the server's on the right. Upload and download files and whole
  folders, with a transfer queue, a speed limit and a choice of what to do when a file already exists.
- **Server Manager:** connect to a Bazzite host, see whether `sshd` runs, start or stop it, and edit
  `/etc/ssh/sshd_config`.

The app is a client. Install it on the computer you connect **from**. The host you connect **to** only needs a
reachable `sshd`; it does not need the app.

The app does not change how the board runs. The Server Manager changes the SSH server of the host you connect to,
and asks before it saves.

## What it needs

- Python 3.10 or newer. The installer makes the app's own virtual environment with PyQt6 and
  [paramiko](https://www.paramiko.org/) in it, so the suite's shared environment is not touched.
- On the host you connect to: `sshd` running, and the firewall open for it. [Set up the host](#set-up-the-host)
  has the commands.
- Optional: `paplay` (the sound of the beep when a transfer completes). Without it the app uses Qt's beep.

## Using it

1. Fill in the host, the port (22), your user name and either a password or the path of a private key. A key is
   the better choice; with a key, the password field holds the key's passphrase.
2. Press **Connect** in the window's header. The first time, the app shows the server's fingerprint and asks whether you trust it. Yes
   adds it to `~/.ssh/known_hosts`; no makes no connection.
3. Double-click folders to open them, or type a path. Select files or folders and press **Upload →** or
   **← Download**, or use the right-click menu. Ctrl-click and Shift-click select more than one. The right-click
   menu also deletes, after a question.
4. To upload, you can also drag files and folders onto the server's list, from the list on the left or from
   your file manager. They go to the server folder that is open, and are copied, never moved.
5. The lists under the folders show the queued, failed and successful transfers. Closing the app while transfers
   are queued or running asks first, because it cancels them.

The window's header shows three states: your own system, the SFTP connection and the state of `sshd` on the host
the Server Manager is connected to; beside them, **Connect** connects the SFTP Client (and disconnects it again).
The password rules stand at the right of the password field and show, as you type, what is still missing. A red dot at the right of the title appears after an error was logged; click
it to open the log.

**Profiles.** *Save profile* keeps the host, port, user name and key path under a name. Passwords and key
passphrases are never saved. The SFTP Client and the Server Manager each have their own list.

**Passwords.** A password without a key must have at least 8 characters, one capital, one number and one special
character, or the app does not connect. An empty password is fine with a key.

### Server Manager

Connect, and the app asks `sshd` for its state: running or stopped. The button next to it starts or stops it.
*Load sshd_config* reads `/etc/ssh/sshd_config` into the editor. *Save sshd_config* checks the text with
`sshd -t`, keeps the old file as `sshd_config.bak`, installs the new one and offers to restart `sshd`.

These steps need `sudo` without a password on the host (`sudo -n`). When the host asks for one, the app shows
the error and changes nothing.

## Set up the host

On the Bazzite host, once, in a terminal:

```sh
rpm -q openssh-server                       # if it is missing: sudo rpm-ostree install openssh-server, then reboot
sudo systemctl enable --now sshd
systemctl is-active sshd                    # prints "active"
sudo firewall-cmd --list-services           # ssh must be in the list
sudo firewall-cmd --permanent --add-service=ssh && sudo firewall-cmd --reload   # only when it is not
hostname -I                                 # the address to connect to
```

Use the address of the Ethernet or Wi-Fi connection that is in use, and your account name (`whoami`). Keep both
computers on a network you trust, and do not forward port 22 from your router to the internet.

Password logins can be switched off on a recent Fedora-based system. To switch them on, create a file for it, and
restart `sshd`:

```sh
echo "PasswordAuthentication yes" | sudo tee /etc/ssh/sshd_config.d/10-enable-passwords.conf
sudo systemctl restart sshd
```

### Logging in with a key

On the computer you connect from:

```sh
ssh-keygen -t ed25519
ssh-copy-id yourusername@HOST_ADDRESS
```

Then give the key's path in the app (`~/.ssh/id_ed25519`), or leave the field empty to use your SSH agent and the
default keys.

## On Windows

SFTP Tools also comes as a program for Windows, for connecting to the board from a Windows computer. It is not
installed by the portal. On the [releases page](https://github.com/RobertoTorino/nexus/releases),
open the latest `sftp` release and download `bc250-bazzite-sftp-tools-<version>-windows.zip` and its
`.sha256` file. Check the download (`certutil -hashfile <zip> SHA256` must print the number in the `.sha256`
file), unzip it, and start `BC250-SFTP-Tools.exe`. It needs no Python.

The program is not signed, so Windows may show a SmartScreen warning the first time: choose *More info*, then
*Run anyway*. Settings, profiles and the log are in `C:\Users\<you>\.config\bc250-bazzite-sftp-tools\` and
`C:\Users\<you>\.local\share\bc250-bazzite-sftp-tools\`. The beep uses Qt's, not `paplay`. Windows has an
OpenSSH client with `ssh-keygen` but no `ssh-copy-id`: to log in with a key, copy the public key into
`~/.ssh/authorized_keys` on the host by hand.

## Settings

*Edit, Settings…* has these, saved when you press Save:

| Setting | Default | What it does |
|---|---|---|
| Default local folder | home folder | The folder the left list starts in. |
| Connection timeout | 10 s | How long to wait for a connection (1 to 300). |
| TCP keep-alive | 15 s | How often to send a keep-alive on an idle connection (1 to 300). |
| Reconnect attempts, delay | 2, 5 s | Retries after a failed connection (0 to 10), and the pause between them (1 to 60). A host key you have not trusted is never retried. |
| Show hidden files | off | Lists names that start with a dot. |
| If file exists | Ask | Ask, overwrite or skip when the target exists. With more than one file, *Ask* offers to do the same for the others. |
| Speed limit | unlimited | Limit in KB/s per transfer. |
| File size format | Auto, 1 decimal, separator | Auto (1024-based), binary (KiB, MiB) or decimal (KB, MB); decimals 0 to 3; thousands separator. |
| Date format, time format | YYYY-MM-DD, HH:MM:SS | How modification times are shown. |
| Beep when transfer completes | on | The desktop's *complete* sound. |
| Filter invalid Windows filename characters | on | A download replaces `< > : " \| ? *` in names with the replacement character (`_`), so the files can be copied to Windows later. |
| Enable SFTP compression | on | zlib compression on the connection. |
| Auto-clear successful transfers | on | Removes finished transfers from the list. |
| Preserve file modification times | on | Downloaded files get the remote modification time. |
| Log level, max log file size | INFO, 10 MB | What is logged, and the size at which the log rotates (three backups are kept). |

## Files

| What | Where |
|---|---|
| The app | `~/.local/share/bc250-bazzite-sftp-tools/app` and its virtual environment `.../venv` |
| Settings | `~/.config/bc250-bazzite-sftp-tools/settings.json` (delete it to go back to the defaults) |
| Profiles | `~/.config/bc250-bazzite-sftp-tools/profiles.json` (SFTP Client), `server-profiles.json` (Server Manager); readable by you only |
| The log | `~/.local/share/bc250-bazzite-sftp-tools/bc250-bazzite-sftp-tools.log` |
| Trusted hosts | `~/.ssh/known_hosts`, never removed by the app |

## Uninstalling

Use the portal, or run `./install.sh --uninstall` from the app's folder. That removes the app and its
environment and keeps your settings, profiles and log. `./install.sh --uninstall --purge` removes those too.
