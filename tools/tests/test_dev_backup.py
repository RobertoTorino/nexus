# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/dev-backup.sh: packs what the repository does not hold on the development machine (Claude Code's memory
and settings, the git identity, the SSH keys, the GitHub CLI's and the suite's settings) with lists of what to
install again, and restores it into a home folder, keeping the files already there."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "dev-backup.sh"

pytestmark = pytest.mark.skipif(os.name != "posix" or shutil.which("bash") is None or shutil.which("tar") is None,
                                reason="needs bash and tar")


def run(home: Path, *args: str, path: str = "/usr/bin:/bin") -> subprocess.CompletedProcess[str]:
    env = {"HOME": str(home), "PATH": path, "LANG": "C.UTF-8"}
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=120,
                          check=False)


def make_home(home: Path) -> None:
    memory = home / ".claude" / "projects" / "-var-home-admin-Projects-Nexus" / "memory"
    memory.mkdir(parents=True)
    (memory / "MEMORY.md").write_text("- [A fact](fact.md)\n", encoding="utf-8")
    (home / ".claude" / "settings.json").write_text('{"theme": "dark"}\n', encoding="utf-8")
    (home / ".claude" / ".credentials.json").write_text("{}\n", encoding="utf-8")
    (home / ".claude" / "sessions").mkdir()
    (home / ".claude" / "sessions" / "transient.json").write_text("{}\n", encoding="utf-8")
    (home / ".claude.json").write_text("{}\n", encoding="utf-8")
    (home / ".gitconfig").write_text("[user]\n\tname = Someone\n", encoding="utf-8")
    ssh = home / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519").write_text("private\n", encoding="utf-8")
    (ssh / "id_ed25519.pub").write_text("public\n", encoding="utf-8")
    (ssh / "allowed_signers").write_text("a b\n", encoding="utf-8")
    (ssh / "ps2-bios").write_bytes(b"\0" * 16)
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".config" / "gh" / "config.yml").write_text("git_protocol: https\n", encoding="utf-8")
    (home / ".config" / "bc250-upscaler").mkdir()
    (home / ".config" / "bc250-upscaler" / "settings.ini").write_text("[a]\nb=1\n", encoding="utf-8")


def test_help_prints_the_header_comment():
    result = run(Path("/nonexistent"), "--help")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("Packs what the repository does not hold")
    assert "SPDX" not in result.stdout and "tools/dev-backup.sh pack" in result.stdout


def test_no_command_is_an_error():
    assert run(Path("/nonexistent")).returncode == 2
    assert run(Path("/nonexistent"), "nonsense").returncode == 2


def test_pack_takes_the_files_and_writes_the_lists(tmp_path: Path):
    home = tmp_path / "home"
    make_home(home)
    out = tmp_path / "stick"
    out.mkdir()
    result = run(home, "pack", str(out))
    assert result.returncode == 0, result.stderr + result.stdout
    archives = list(out.glob("nexus-dev-backup-*.tar.gz"))
    assert len(archives) == 1
    assert oct(archives[0].stat().st_mode & 0o777) == "0o600"
    with tarfile.open(archives[0]) as tar:
        names = set(tar.getnames())
    assert "home/.claude/projects/-var-home-admin-Projects-Nexus/memory/MEMORY.md" in names
    assert "home/.claude/settings.json" in names and "home/.claude/.credentials.json" in names
    assert "home/.claude.json" in names and "home/.gitconfig" in names
    assert "home/.ssh/id_ed25519" in names and "home/.ssh/id_ed25519.pub" in names
    assert "home/.ssh/allowed_signers" in names
    assert "home/.config/gh/config.yml" in names
    assert "home/.config/bc250-upscaler/settings.ini" in names
    assert "home/.claude/sessions/transient.json" not in names, "sessions are transient"
    assert "home/.ssh/ps2-bios" not in names, "other files in ~/.ssh stay with the owner"
    for name in ("Brewfile", "flatpaks.txt", "vscode-extensions.txt", "rpm-ostree-status.txt", "kargs.txt",
                 "rustup.txt", "claude-code.txt", "ssh-files.txt", "packed-at.txt"):
        assert f"lists/{name}" in names, name
    listed = run(home, "list", str(archives[0]))
    assert listed.returncode == 0 and "home/.gitconfig" in listed.stdout


def test_lists_say_which_tool_is_missing(tmp_path: Path):
    home = tmp_path / "home"
    make_home(home)
    result = run(home, "pack", str(tmp_path))
    assert result.returncode == 0, result.stderr
    archive = next(tmp_path.glob("nexus-dev-backup-*.tar.gz"))
    with tarfile.open(archive) as tar:
        brewfile = tar.extractfile("lists/Brewfile").read().decode()
        ssh_files = tar.extractfile("lists/ssh-files.txt").read().decode()
    if shutil.which("brew", path="/usr/bin:/bin:/home/linuxbrew/.linuxbrew/bin") is None:  # the script adds brew's folder
        assert "brew is not installed" in brewfile
    else:                       # brew bundle dump wrote it: empty where brew installed nothing (GitHub's runner)
        assert "brew is not installed" not in brewfile
    assert "ps2-bios" in ssh_files, "the files not packed are listed so the owner can copy them by hand"


def test_restore_puts_the_files_back_and_keeps_existing_ones(tmp_path: Path):
    old = tmp_path / "old"
    make_home(old)
    stick = tmp_path / "stick"
    stick.mkdir()
    assert run(old, "pack", str(stick)).returncode == 0
    archive = next(stick.glob("nexus-dev-backup-*.tar.gz"))

    new = tmp_path / "new"
    new.mkdir()
    (new / ".gitconfig").write_text("[user]\n\tname = Fresh\n", encoding="utf-8")
    result = run(new, "restore", str(archive))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (new / ".claude" / "projects" / "-var-home-admin-Projects-Nexus" / "memory" / "MEMORY.md").read_text(
        encoding="utf-8") == "- [A fact](fact.md)\n"
    assert (new / ".ssh" / "id_ed25519").read_text(encoding="utf-8") == "private\n"
    assert oct((new / ".ssh").stat().st_mode & 0o777) == "0o700"
    assert oct((new / ".ssh" / "id_ed25519").stat().st_mode & 0o777) == "0o600"
    assert (new / ".gitconfig").read_text(encoding="utf-8") == "[user]\n\tname = Fresh\n", "an existing file is kept"
    lists = stick / "nexus-dev-backup-lists"
    assert (lists / "Brewfile").is_file() and (lists / "kargs.txt").is_file()
    assert "SETUP.md" in result.stdout

    forced = run(new, "restore", str(archive), "--force")
    assert forced.returncode == 0, forced.stderr
    assert (new / ".gitconfig").read_text(encoding="utf-8") == "[user]\n\tname = Someone\n"


def test_restore_without_an_archive_fails(tmp_path: Path):
    assert run(tmp_path, "restore").returncode == 1
    assert run(tmp_path, "restore", str(tmp_path / "none.tar.gz")).returncode == 1
    assert run(tmp_path, "pack", str(tmp_path / "missing")).returncode == 1
