<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The development machine

What a machine needs to work on the repository, on Bazzite or on Windows, and how it stays up to date. The
checks before a push are in [Development](index.md#development); the release commands in
[GitHub settings](github-settings.md#the-github-cli).

## Tools

| Tool | What uses it | Bazzite | Windows |
|---|---|---|---|
| Git | everything; `tools/hooks/pre-push` as the pre-push hook | comes with Bazzite | Git for Windows (`winget install Git.Git`); Git Bash runs the `.sh` scripts |
| Python 3.11 or newer (CI runs 3.12) | the venvs, every tool in `tools/` | comes with Bazzite (`python3`, without PyQt6) | python.org or `winget install Python.Python.3.12`, with the `py` launcher |
| The development venv (`requirements-dev.txt`) | `./test.sh`, `mkdocs`, the tools; it brings pytest, PyQt6, MkDocs Material and Pillow | `.venv-linux/`, see [Development](index.md#development) | `.venv-windows/` |
| podman (or docker) | `tools/ci-local.sh`: CI's jobs in a container, with Python 3.12, shellcheck, fakeroot, Rust and Console Link's build tools inside | comes with Bazzite | not used; CI's Windows job runs only on GitHub |
| shellcheck | the shell checks of CI | `brew install shellcheck` | `winget install koalaman.shellcheck` |
| fakeroot | the installer tests (`bc250-bazzite/tools/installer-tests/`) | `brew install fakeroot` | Linux only |
| Node.js | the design panel's test (`tools/tests/test_design_panel.py`, skipped without it) | `brew install node` | `winget install OpenJS.NodeJS.LTS` |
| GitHub CLI (`gh`) | the runs and releases from a terminal, Nexus Releases' sign-in | `brew install gh` | `winget install GitHub.cli` |
| ffmpeg | the video tours (`bc250-bazzite/tools/record-tour.sh`, `bc250-bazzite/tools/record-app-tour.sh`) | `brew install ffmpeg` | `winget install Gyan.FFmpeg` |
| Rust (rustup with cargo and clippy), maturin, nasm, the libva headers | Console Link's native core, only to run `cargo test` or `maturin build` on the machine itself; the container of `tools/ci-local.sh` has them all | rustup from rustup.rs, `brew install nasm`, maturin with pip in the venv | `winget install Rustlang.Rustup`; the decoder builds on Linux only |
| PyInstaller and Pillow | `tools/build_windows_exe.py`, the Windows executable of Bazzite SFTP | not used | in `.venv-windows/`, `pip install pyinstaller pillow` |
| notify-send | `tools/dev-updates.sh --notify` (below) | comes with Bazzite | not used |
| zip, tar, sha256sum | `tools/build_release.py` | come with Bazzite | come with Git Bash |

Homebrew on Bazzite installs to `/home/linuxbrew/.linuxbrew/bin`; a shell that is not interactive (a timer, an IDE's
terminal) may need it on `PATH`.

## Moving to a new drive

`SETUP.md` at the root of the repository is the order of things when the machine gets a new drive or a fresh
Bazzite: what to pack first, then the layered packages, Homebrew's packages, the Flatpaks, Rust, the checkout,
Claude Code, VS Code and the suite. `tools/dev-backup.sh` packs what the repository does not hold and restores it:

```bash
tools/dev-backup.sh pack /run/media/$USER/<stick>            # the archive: home files and the lists of what is installed
tools/dev-backup.sh list <archive>                          # what it holds
tools/dev-backup.sh restore <archive>                       # into the new home folder; existing files are kept
```

The archive holds Claude Code's memory and sign-in, the git identity, the SSH keys, the GitHub CLI's and the
suite's settings and VS Code's settings, with a Brewfile, the Flatpak and extension lists, the image's layered
packages and kernel arguments and the user timers; it holds secrets, so it stays on a drive of your own and is
deleted once the new machine works.

## Staying up to date

Bazzite keeps itself current: its updater (`uupd.timer`) runs every day at 04:00, or at the next boot when the
machine was off, and updates the image, the Flatpaks and Homebrew's packages. `ujust update` runs the same now; a
new image is used after a reboot. The venv is pip's and the Rust toolchain rustup's; nothing updates them for you.

`tools/dev-updates.sh` looks at every source at once and says what has a newer version: Bazzite's image, the
Flatpaks, Homebrew's packages (`gh`, shellcheck, fakeroot, node, ffmpeg, ...), the Rust toolchain and the packages
of `.venv-linux`. It only looks; with each source it says how it gets installed. `--install` makes a user timer
of it that runs every hour and shows a desktop notification when something is new, so an update never comes as a
surprise:

```bash
tools/dev-updates.sh              # what is outdated, per source; exit 10 when something is
tools/dev-updates.sh --install    # nexus-dev-updates.timer: every hour, a notification when something is new
tools/dev-updates.sh --uninstall  # removes the timer
systemctl --user list-timers nexus-dev-updates.timer
```

The venv's packages are upgraded within what `requirements-dev.txt` allows (it keeps MkDocs below 2 and Pillow
below 13 on purpose): `.venv-linux/bin/python -m pip install -U <package>`, or the whole venv again with
`-r requirements-dev.txt --upgrade`. The toolchain: `rustup update`.

On Windows, `winget upgrade` lists every program with a newer version and `winget upgrade --all` installs them;
the venv is `.venv-windows\Scripts\python.exe -m pip list --outdated`.

The board has its own reminder: the Dependency Checker's weekly look at Bazzite's update state, for the people who
run the suite. The timer above is for the machine the suite is developed on.

## Git identity and signing

Git takes the name and email from the global configuration; without them it makes some up from the user and host
name and warns at every commit. GitHub links a commit to an account by its email, so use the account's noreply
address (*Settings, Emails* on GitHub shows it), and sign commits with the SSH key the account has as a signing
key (*Settings, SSH and GPG keys*):

```bash
git config --global user.name "Your Name"
git config --global user.email "<id>+<user>@users.noreply.github.com"
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
# so that git log --show-signature can verify your own commits
echo "$(git config --global user.email) $(cat ~/.ssh/id_ed25519.pub)" > ~/.ssh/allowed_signers
git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
```

Leave tag signing off: the release tags are plain tags (`tools/tag-release.sh`), and a signed tag needs a message,
which breaks `git tag <name>` in the tools' tests. This is per machine and per user account on it: a new system, or
a new home folder, starts without it. Check with
`git config --global --list`, and with `git log -3 --format='%an <%ae> %G?'` after a commit (`G` is a good
signature).
