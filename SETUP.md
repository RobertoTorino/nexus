<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Setting up the development machine

What to take from the old drive, and what to install on the new one, before the repository can be worked on
again. The development machine on the Bazzite side is the BC-250 board itself (ASRock AMD BC-250, Bazzite
stable with the KDE desktop), so the list covers the board's setup as well as the repository's tools. The tools'
table and the update timer are on the wiki's
[The development machine](nexus/docs/machine.md) page; this file is the order to do things
in. The Windows machine is not touched by a drive change on the board: its tools are in the same table.

## Before the old drive goes

1. Commit and push everything in the checkout (`git status` clean, `git log origin/main..` empty).
2. Pack what the repository does not hold, onto a USB stick or another drive:

   ```bash
   tools/dev-backup.sh pack /run/media/$USER/<stick>
   ```

   The archive holds Claude Code's memory, settings, plugins and sign-in, the git identity and signing setup,
   the SSH keys, the GitHub CLI's configuration, VS Code's settings, the suite's app settings (`~/.config/bc250-*`
   and the like), and lists of what was installed: a Brewfile, the Flatpaks, VS Code's extensions, the image's
   layered packages and kernel arguments, the user timers and the Rust toolchain. It holds secrets: keep it off
   the repository and delete it once the new machine works.
3. Copy by hand what the script leaves out, if you want it back:
   - the other files in `~/.ssh` (the archive takes the keys, `known_hosts`, `allowed_signers` and `config`
     only; `lists/ssh-files.txt` names the rest);
   - the apps' data under `~/.local/share/bc250-*` and `~/.local/share/bazzite-*` (the apps and their venvs
     install again from the portal; `lists/local-share-not-packed.txt` names the folders, look inside the ones
     whose results or history you want);
   - the Flatpak emulators' saves, BIOS files and settings in `~/.var/app/` (net.pcsx2.PCSX2, net.rpcs3.RPCS3);
   - Steam's library in `~/.local/share/Steam/` (large; the games download again, the saves are in the cloud
     for most of them).

## On the new drive

Bazzite stable with the KDE desktop, the same user name (`admin`) and the checkout at the same path,
`/var/home/admin/Projects/Nexus`: Claude Code's memory is keyed on that path, and the user timer's unit file
points into it.

1. **Bazzite's own tools** come with the image: `git`, `python3` (without PyQt6), `podman`, `distrobox`,
   `flatpak`, `brew`, `ffmpeg` (with libx264, for the tours), `jq`, `notify-send`, `zip`, `tar`, `sha256sum`.
   Let the first update run (`ujust update`) and reboot.
2. **The layered packages**, then reboot:

   ```bash
   rpm-ostree install cyan-skillfish-governor-smu dkms fio git glmark2 stress umr vkmark
   ```

   `cyan-skillfish-governor-smu` is the governor BC-250 Governor Manager drives, `umr` is what the CU unlock
   and bisect apps read the chip with, and `fio`, `stress`, `glmark2` and `vkmark` are the load tools of BC-250
   Bazzite Test's checks. `lists/rpm-ostree-status.txt` in the archive shows the line as it was.
3. **The kernel arguments** the old drive had, for comparison (`lists/kargs.txt`): `ttm.pages_limit=3014656`
   (BC-250 Memory Manager sets it), `mitigations=off` (Bazzite Test's CPU Mitigations check wants it),
   `bluetooth.disable_ertm=1` and `zswap.enabled=0`. Set an argument again with `rpm-ostree kargs --append=...`
   and reboot, or let the app that owns it set it.
4. **Homebrew's packages** (Homebrew is on the image; its folder is `/home/linuxbrew/.linuxbrew/bin`):

   ```bash
   brew install shellcheck fakeroot node gh imagemagick
   brew install --cask visual-studio-code-linux jetbrains-toolbox-linux
   ```

   Or everything at once from the archive's list: `brew bundle --file=<lists>/Brewfile`. The wiki's table says
   what each tool is for; `imagemagick` and JetBrains Toolbox are not used by the repository's tools.
5. **The Flatpaks**: `flatpak install flathub <ids>` with the ids from `lists/flatpaks.txt`. On the old drive:
   com.brave.Browser, com.github.Matoking.protontricks, com.github.tchx84.Flatseal, com.google.Chrome,
   com.heroicgameslauncher.hgl, com.obsproject.Studio, com.vysp3r.ProtonPlus, io.github.DenysMb.Kontainer,
   io.github.flattool.Warehouse, io.github.radiolamp.mangojuice, net.pcsx2.PCSX2, net.rpcs3.RPCS3,
   no.mifi.losslesscut, org.gimp.GIMP, org.gnome.Firmware, org.kde.gwenview, org.kde.haruna, org.kde.kcalc,
   org.kde.okular. None of them is needed by the repository's checks.
6. **Rust**, for Console Link's native core on the machine itself (the CI container has its own):
   `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` (stable, with `clippy` and `rustfmt`), then
   `brew install nasm` for the decoder. `~/.cargo/env` goes into `~/.bashrc` and `~/.profile`; the installer
   adds it.
7. **Restore the archive**, before anything signs in or writes settings:

   ```bash
   tools/dev-backup.sh restore /run/media/$USER/<stick>/nexus-dev-backup-<date>.tar.gz
   ```

   It keeps a file that already exists (`--force` replaces it) and puts the lists next to the archive. Then
   check the identity and the sign-ins: `git config --global --list` (name, email, SSH signing: the wiki's
   [Git identity and signing](nexus/docs/machine.md#git-identity-and-signing)),
   `ssh -T git@github.com`, `gh auth status` (`gh auth login` and `gh auth setup-git` when the keyring did not
   come along: the token lives in the desktop's keyring, not in `~/.config/gh`).
8. **The checkout**:

   ```bash
   git clone https://github.com/RobertoTorino/nexus.git /var/home/admin/Projects/Nexus
   cd /var/home/admin/Projects/Nexus
   git config core.hooksPath tools/hooks        # the pre-push hook, once per checkout
   python3 -m venv .venv-linux && .venv-linux/bin/python -m pip install -r requirements-dev.txt
   ./test.sh                                    # every test suite of this system
   tools/ci-local.sh                            # CI's jobs in a container; the first run builds the image
   tools/dev-updates.sh --install               # the hourly timer that says what has a newer version
   ```

9. **Claude Code**: `curl -fsSL https://claude.ai/install.sh | bash` (it lives in `~/.local/share/claude`, with
   `~/.local/bin/claude` on `PATH`); the restored `~/.claude` brings the memory, the settings, the plugins and
   the sign-in, and `claude` asks to sign in again when the sign-in has expired.
10. **VS Code** from the cask above, its settings restored; the extensions:

    ```bash
    xargs -a <lists>/vscode-extensions.txt -n1 code --install-extension
    ```

    On the old drive: anthropic.claude-code, davidanson.vscode-markdownlint, github.vscode-github-actions,
    ms-azuretools.vscode-containers, ms-python.debugpy, ms-python.python, ms-python.vscode-pylance,
    ms-python.vscode-python-envs, ms-vscode.cmake-tools, ms-vscode.cpp-devtools, ms-vscode.cpptools,
    ms-vscode.cpptools-extension-pack, ms-vscode.cpptools-themes, rust-lang.rust-analyzer, timonwong.shellcheck.
11. **The suite on the board**, for testing the apps: `bc250-bazzite/install.sh` installs the portal and BC-250
    Bazzite Test from the checkout, and the portal installs the other apps from it. The apps that change the board
    (Persistent ACPI, Fan Control, Governor Manager, Memory Manager) do so again when they are installed and
    set; their settings came back with the archive. The suite's user units (`bc250-bazzite-update-reminder.timer`,
    `bc250-usb-hdcam-load.service`, `bc250-usb-hdcontrol-idle.service`) are written by the apps that own them.
12. **Check the time zone**: `timedatectl` says Europe/Amsterdam; the CHANGELOG times depend on it.

## What is where

| Kept by | What |
|---|---|
| the repository | the code, the tools, the wikis, the designs and icons, `requirements-dev.txt` (the venv) |
| the archive (`tools/dev-backup.sh`) | `~/.claude` (memory, settings, plugins, skills, sign-in), `~/.claude.json`, `~/.gitconfig`, the SSH keys, `~/.config/gh`, VS Code's settings, the suite's app settings, the lists |
| the lists in the archive | the Brewfile, the Flatpaks, VS Code's extensions, the layered packages, the kernel arguments, the user timers and units, the Rust toolchain, Claude Code's version |
| nowhere, by hand | the other files in `~/.ssh`, the apps' data in `~/.local/share`, the Flatpak emulators' data in `~/.var/app`, Steam's library |
