# SPDX-License-Identifier: GPL-3.0-or-later
"""The root part: Decky Loader's binary, its system service and the /home/deck link. Decky runs as root from a system
service, so installing, removing and restarting it need root; everything else in the app runs as your own user.

This file runs as root and needs only the standard library. The app runs it through pkexec with the system python3 in
isolated mode (-I), so nothing from the user's environment or the current folder is imported into the root process.
The user is the one pkexec names (PKEXEC_UID), never one given on the command line.

The layout is Decky's own, as its installer makes it, so Decky's updater (in its settings in Game Mode), Bazzite's
`ujust setup-decky` and the plugins all find what they expect:
 * ~/homebrew/services/PluginLoader: the binary, from the pinned release, checked against its SHA-256 here, as root,
   whatever the app checked before. Labeled bin_t for SELinux, as Decky's installer does, or systemd may not start
   it from a home folder.
 * ~/homebrew/services/.loader.version: the release tag, which Decky's updater also writes.
 * ~/homebrew/plugins: the plugins, and ~/homebrew/settings, logs and data, which Decky makes itself.
 * /etc/systemd/system/plugin_loader.service: Decky's release unit with the folder filled in, enabled and started.
One change to Decky's layout: services/ is root's. Decky's installer leaves it to the user, so anything running as
the user could replace the binary that root starts at boot. Decky's own updater runs as root and still writes there.

The pin: the release this version of the app was tried with. A newer Decky comes with a new version of the app."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

VERSION = "3.3.0"
TAG = "v3.3.0"
ASSET = "PluginLoader"
SHA256 = "e80d03e641d1766a33a817cb27ab8d2e0a4633685e5d27e4de948a6687526181"
SIZE_MB = 33
REPO = "SteamDeckHomebrew/decky-loader"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
RELEASE_PAGE = f"https://github.com/{REPO}/releases/tag/{TAG}"
UNIT = "plugin_loader.service"
SERVICE = "plugin_loader"
DECK_HOME = "/home/deck"

Runner = Callable[[list[str]], "Result"]
Chown = Callable[[Path, int, int], None]


@dataclass(frozen=True)
class Result:
    code: int
    out: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def run(argv: list[str]) -> Result:
    try:
        done = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Result(127, str(exc))
    return Result(done.returncode, done.stdout)


def chown(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid, follow_symlinks=False)


class LoaderError(Exception):
    pass


# --- The files ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Paths:
    home: Path
    etc: Path = Path("/etc")
    deck: Path = Path(DECK_HOME)
    selinux: Path = Path("/sys/fs/selinux")

    @property
    def homebrew(self) -> Path:
        return self.home / "homebrew"

    @property
    def services(self) -> Path:
        return self.homebrew / "services"

    @property
    def plugins(self) -> Path:
        return self.homebrew / "plugins"

    @property
    def binary(self) -> Path:
        return self.services / "PluginLoader"

    @property
    def version_file(self) -> Path:
        return self.services / ".loader.version"

    @property
    def loader_settings(self) -> Path:
        return self.homebrew / "settings" / "loader.json"

    @property
    def unit(self) -> Path:
        return self.etc / "systemd/system" / UNIT

    @property
    def user_unit(self) -> Path:
        """Where very old Decky installers put a user service; their uninstaller removes it too."""
        return self.home / ".config/systemd/user" / UNIT


@dataclass(frozen=True)
class User:
    name: str
    uid: int
    gid: int
    home: Path

    @classmethod
    def from_uid(cls, uid: int) -> User:
        entry = pwd.getpwuid(uid)
        return cls(entry.pw_name, entry.pw_uid, entry.pw_gid, Path(entry.pw_dir))


def unit_text(homebrew: Path) -> str:
    """Decky's dist/plugin_loader-release.service, with ${HOMEBREW_FOLDER} filled in. Bazzite's `ujust setup-decky
    status` reads LOG_LEVEL: INFO is a release, DEBUG a prerelease."""
    return "\n".join([
        "[Unit]",
        "Description=SteamDeck Plugin Loader",
        "After=network.target",
        "[Service]",
        "Type=simple",
        "User=root",
        "Restart=always",
        "KillMode=process",
        "TimeoutStopSec=15",
        f"ExecStart={homebrew}/services/PluginLoader",
        f"WorkingDirectory={homebrew}/services",
        f"Environment=UNPRIVILEGED_PATH={homebrew}",
        f"Environment=PRIVILEGED_PATH={homebrew}",
        "Environment=LOG_LEVEL=INFO",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ])


def deck_state(home: Path, deck: Path = Path(DECK_HOME)) -> str:
    """The /home/deck link that plugins written for the Steam Deck look in: "own" (your home is /home/deck), "linked"
    (a link to your home), "missing", "elsewhere" (a link to another folder) or "taken" (a folder of its own: another
    user's home)."""
    if os.path.realpath(home) == os.path.realpath(deck) and not deck.is_symlink():
        return "own"
    if deck.is_symlink():
        return "linked" if os.path.realpath(deck) == os.path.realpath(home) else "elsewhere"
    return "taken" if deck.exists() else "missing"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes, mode: int, chown: Chown) -> None:
    """Root-owned, written whole."""
    temp = path.with_name(f".{path.name}.new")
    temp.unlink(missing_ok=True)
    temp.write_bytes(data)
    temp.chmod(mode)
    chown(temp, 0, 0)
    temp.replace(path)


def _checked(run: Runner, argv: list[str]) -> None:
    result = run(argv)
    if not result.ok:
        raise LoaderError(f"{' '.join(argv)} failed (exit code {result.code}): {result.out.strip()[-300:]}")


# --- What the app asks for, as root ------------------------------------------------------------------------------

def install(user: User, paths: Paths, source: Path, run: Runner = run, chown: Chown = chown) -> str:
    """Installs or updates Decky from *source* (the downloaded PluginLoader) and starts its service."""
    data = source.read_bytes()
    if sha256(data) != SHA256:
        raise LoaderError(f"{source} is not Decky Loader {VERSION} as this app was tried with (its SHA-256 "
                          "differs); nothing was changed.")
    # Root writes in your home here: a link in place of a folder could send that anywhere.
    for folder in (paths.homebrew, paths.services):
        if folder.is_symlink():
            raise LoaderError(f"{folder} is a link, not a folder; nothing was changed.")
    for folder in (paths.homebrew, paths.plugins):
        if not folder.is_dir():
            folder.mkdir(parents=True)
            chown(folder, user.uid, user.gid)
    paths.services.mkdir(exist_ok=True)
    chown(paths.services, 0, 0)
    paths.services.chmod(0o755)
    _write(paths.binary, data, 0o755, chown)
    if (paths.selinux / "enforce").exists() and shutil.which("chcon"):
        _checked(run, ["chcon", "-t", "bin_t", str(paths.binary)])
    _write(paths.version_file, f"{TAG}\n".encode(), 0o644, chown)

    paths.user_unit.unlink(missing_ok=True)
    paths.unit.parent.mkdir(parents=True, exist_ok=True)
    _write(paths.unit, unit_text(paths.homebrew).encode(), 0o644, chown)
    if shutil.which("restorecon"):
        run(["restorecon", str(paths.unit)])
    _checked(run, ["systemctl", "daemon-reload"])
    _checked(run, ["systemctl", "enable", SERVICE])
    _checked(run, ["systemctl", "restart", SERVICE])
    return f"Decky Loader {VERSION} is installed and running."


def remove(user: User, paths: Paths, wipe: bool = False, unlink: bool = False, run: Runner = run) -> str:
    """Stops Decky and removes its service and binary. The plugins and their settings stay, unless *wipe*: then all
    of ~/homebrew goes. With *unlink*, the /home/deck link goes too (only when it points to this home)."""
    run(["systemctl", "disable", "--now", SERVICE])
    paths.unit.unlink(missing_ok=True)
    paths.user_unit.unlink(missing_ok=True)
    run(["systemctl", "daemon-reload"])
    if wipe:
        shutil.rmtree(paths.homebrew, ignore_errors=True)
    else:
        for name in (paths.binary, paths.version_file):
            name.unlink(missing_ok=True)
        shutil.rmtree(paths.services / ".systemd", ignore_errors=True)
        try:
            paths.services.rmdir()
        except OSError:
            pass                                # something else in it: left as it is
    text = "Decky Loader is removed" + (", with its plugins and their settings." if wipe else
                                        "; its plugins and their settings stay in ~/homebrew.")
    if unlink and deck_state(user.home, paths.deck) == "linked":
        unlink_deck(user, paths)
        text += f" {paths.deck} is no longer linked."
    return text


def restart(run: Runner = run) -> str:
    _checked(run, ["systemctl", "restart", SERVICE])
    return "Decky Loader was restarted."


def link_deck(user: User, paths: Paths, run: Runner = run) -> str:
    state = deck_state(user.home, paths.deck)
    if state == "own":
        return f"Your home is {paths.deck} already: no link is needed."
    if state == "linked":
        return f"{paths.deck} points to your home already."
    if state == "elsewhere":
        raise LoaderError(f"{paths.deck} is a link to {os.path.realpath(paths.deck)}; it was left as it is.")
    if state == "taken":
        raise LoaderError(f"{paths.deck} is a folder of its own (another user's home); it was left as it is.")
    paths.deck.symlink_to(user.home)
    if shutil.which("restorecon"):
        run(["restorecon", str(paths.deck)])
    return f"{paths.deck} points to your home now."


def unlink_deck(user: User, paths: Paths) -> str:
    if deck_state(user.home, paths.deck) != "linked":
        raise LoaderError(f"{paths.deck} is not a link to your home; it was left as it is.")
    paths.deck.unlink()
    return f"{paths.deck} is no longer linked."


# --- Command line (as root, through pkexec) -------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loader.py", description="Decky Loader's root part (Decky Loader "
                                                                    "Manager runs it through pkexec)")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("install").add_argument("file", type=Path, help="the downloaded PluginLoader")
    remove_parser = actions.add_parser("remove")
    remove_parser.add_argument("--wipe", action="store_true", help="also remove ~/homebrew: plugins and settings")
    remove_parser.add_argument("--unlink", action="store_true", help="also remove the /home/deck link")
    for name in ("restart", "link", "unlink"):
        actions.add_parser(name)
    args = parser.parse_args(argv)

    def answer(ok: bool, text: str) -> int:
        print(json.dumps({"ok": ok, "message": text} if ok else {"ok": ok, "error": text}), flush=True)
        return 0 if ok else 1

    if os.geteuid() != 0:
        return answer(False, "This needs root: the app runs it through pkexec.")
    try:
        uid = int(os.environ["PKEXEC_UID"])
    except (KeyError, ValueError):
        return answer(False, "PKEXEC_UID is not set: run this through pkexec from your own account.")
    if uid == 0:
        return answer(False, "Run the app as your own user, not as root.")
    user = User.from_uid(uid)
    paths = Paths(user.home)
    try:
        if args.action == "install":
            return answer(True, install(user, paths, args.file))
        if args.action == "remove":
            return answer(True, remove(user, paths, args.wipe, args.unlink))
        if args.action == "restart":
            return answer(True, restart())
        if args.action == "link":
            return answer(True, link_deck(user, paths))
        return answer(True, unlink_deck(user, paths))
    except (LoaderError, OSError) as error:
        return answer(False, str(error))


if __name__ == "__main__":
    sys.exit(main())
