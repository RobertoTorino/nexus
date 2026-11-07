<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![Bazzite SFTP Tools](../assets/sftp/ps5-sftp-tools.webp){ .app-logo }

# Bazzite SFTP Tools

!!! warning "Changes the board"
    Starting or configuring an SSH server changes the local or remote Bazzite host. Starting the local server enables it at boot and may open the firewall for SSH. Review access and firewall rules before enabling it.

This optional utility transfers files over SFTP and manages OpenSSH's `sshd`. On PlayStation 5 hardware running
Bazzite, the local server controls apply to the **PS5 Bazzite host**, not PlayStation firmware or services. The
client can also connect to another SFTP server; the server does not need this app.

## Install

From the checkout or an extracted app release, run `./install.sh` in the app folder. It creates an app-specific
Python environment with PyQt6 and Paramiko, a menu entry and a Desktop shortcut. Use `--no-desktop-shortcut` to
skip the shortcut, `--uninstall` to remove the app, or `--uninstall --purge` to remove its settings and profiles too.

## Transfer files

Enter the host, port, user and password or private key in **SFTP Client**, then connect. Check the first connection's
host-key fingerprint through a trusted channel before accepting it; accepted keys go in `~/.ssh/known_hosts`.
Browse the two sides, select files or folders and use Upload or Download. Transfers run in a queue. The menus also
provide deletion, so check the selected side and paths before confirming. Settings include the transfer speed limit
and behavior when a file exists. Profiles and settings are stored locally; avoid storing credentials on a shared account.

## Manage SSH servers

**This computer as host** manages the Bazzite host where the app runs. Starting requires confirmation and polkit
authorization: it enables and starts `sshd` at boot and, if firewalld is running and SSH is not allowed in its
default zone, permanently adds SSH there and reloads the firewall. This may expose SSH to other computers. Stopping
requires confirmation and authorization; it stops and disables `sshd`, may interrupt connections, and **does not**
remove firewall rules. Review access and firewall rules yourself. If OpenSSH Server is missing, the app shows an
installation hint; installing it changes the system and may require a reboot.

**Server Manager** also connects to a reachable remote Bazzite host. Start and stop ask for confirmation; stopping
may interrupt connections. Remote service and configuration changes use non-interactive `sudo` on that host and fail
if the account is not authorized. Loading and editing `/etc/ssh/sshd_config` does not save it automatically. Saving
asks first, validates the configuration, backs up the old file as `sshd_config.bak`, and offers a separate restart.
An incorrect configuration or firewall change can lock you out; keep another way to access the host.

## License

GPL-3.0-or-later, see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/bazzite-console/apps/sftp/LICENSE).
