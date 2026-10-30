#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Packs what the repository does not hold on this development machine, and puts it back on the next one: Claude
# Code's memory, settings, plugins and sign-in (~/.claude, ~/.claude.json), the git identity (~/.gitconfig), the
# SSH keys (~/.ssh), the GitHub CLI's configuration (~/.config/gh), VS Code's settings, the settings of the
# suite's apps (~/.config/bc250-*, bazzite-*, nexus-release-tool), and lists of what to install again: a Brewfile,
# the Flatpaks, VS Code's extensions, the image's layered packages and kernel arguments, the user timers and the
# Rust toolchain. SETUP.md says when to run it and what to do with the lists.
#
#   tools/dev-backup.sh pack [folder]       # writes nexus-dev-backup-<date>.tar.gz in the folder (default: ~)
#   tools/dev-backup.sh list <archive>      # what the archive holds
#   tools/dev-backup.sh restore <archive>   # puts the files back in the home folder; a file that is already
#                                           # there is kept (--force replaces it); the lists go next to the archive
#
# The archive holds secrets (the SSH private key, Claude Code's sign-in): keep it on a USB stick or a drive of
# your own, never in the repository, and delete it from the new machine once restored. Linux only.
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
export PATH="$PATH:/home/linuxbrew/.linuxbrew/bin"

info() { printf '\033[1;35m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }
usage() { sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'; }

# The files and folders packed, relative to the home folder; the ones that exist are taken. ~/.ssh is taken by
# name (the keys, the hosts, the signers), not whole: the owner keeps other files there.
HOME_PATHS=(
    .claude.json
    .claude/settings.json .claude/settings.local.json .claude/keybindings.json .claude/CLAUDE.md
    .claude/.credentials.json .claude/plugins .claude/skills
    .gitconfig
    .ssh/config .ssh/known_hosts .ssh/allowed_signers .ssh/authorized_keys
    .config/gh
    .config/Code/User/settings.json .config/Code/User/keybindings.json .config/Code/User/snippets
)

# Every memory folder of Claude Code's projects, the SSH keys and the suite's settings: by pattern.
home_globs() {
    local path
    for path in "$HOME"/.claude/projects/*/memory "$HOME"/.ssh/id_* "$HOME"/.config/bc250-* \
                "$HOME"/.config/bazzite-* "$HOME"/.config/nexus-release-tool; do
        [ -e "$path" ] && printf '%s\n' "${path#"$HOME"/}"
    done
    return 0
}

# One list per source into $1; a source whose tool is missing says so in its file.
write_lists() {
    local lists=$1
    mkdir -p "$lists"
    if command -v brew >/dev/null; then
        brew bundle dump --force --file="$lists/Brewfile" >/dev/null 2>&1 || warn "brew bundle dump failed"
    else
        echo "# brew is not installed" >"$lists/Brewfile"
    fi
    if command -v flatpak >/dev/null; then
        flatpak list --app --columns=application,origin >"$lists/flatpaks.txt" 2>/dev/null
    else
        echo "# flatpak is not installed" >"$lists/flatpaks.txt"
    fi
    if command -v code >/dev/null; then
        code --list-extensions >"$lists/vscode-extensions.txt" 2>/dev/null
    else
        echo "# code (VS Code) is not installed" >"$lists/vscode-extensions.txt"
    fi
    if command -v rpm-ostree >/dev/null; then
        rpm-ostree status >"$lists/rpm-ostree-status.txt" 2>/dev/null
        rpm-ostree kargs >"$lists/kargs.txt" 2>/dev/null
    else
        echo "# rpm-ostree is not installed" | tee "$lists/rpm-ostree-status.txt" >"$lists/kargs.txt"
    fi
    if command -v rustup >/dev/null; then
        { rustup toolchain list; rustup component list --installed; } >"$lists/rustup.txt" 2>/dev/null
    else
        echo "# rustup is not installed" >"$lists/rustup.txt"
    fi
    if command -v systemctl >/dev/null; then
        systemctl --user list-timers --all --no-pager >"$lists/user-timers.txt" 2>/dev/null
        ls "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user" >"$lists/user-units.txt" 2>/dev/null
    fi
    if command -v claude >/dev/null; then
        claude --version >"$lists/claude-code.txt" 2>/dev/null
    else
        echo "# claude (Claude Code) is not installed" >"$lists/claude-code.txt"
    fi
    git -C "$ROOT" remote -v >"$lists/git-remote.txt" 2>/dev/null
    git -C "$ROOT" config --local --list >"$lists/git-local-config.txt" 2>/dev/null
    { ls "$HOME/.ssh" 2>/dev/null; } >"$lists/ssh-files.txt"
    { ls -d "$HOME"/.local/share/bc250-* "$HOME"/.local/share/bazzite-* 2>/dev/null; } >"$lists/local-share-not-packed.txt"
    date -Is >"$lists/packed-at.txt"
}

TMP=""
trap '[ -n "$TMP" ] && rm -rf "$TMP"' EXIT

pack() {
    local folder=${1:-$HOME} tmp archive relpath
    [ -d "$folder" ] || die "no such folder: $folder"
    TMP=$(mktemp -d)
    tmp=$TMP
    mkdir -p "$tmp/home"
    local paths=()
    for relpath in "${HOME_PATHS[@]}"; do
        [ -e "$HOME/$relpath" ] && paths+=("$relpath")
    done
    while IFS= read -r relpath; do
        [ -n "$relpath" ] && paths+=("$relpath")
    done < <(home_globs)
    [ "${#paths[@]}" -gt 0 ] || die "nothing to pack in $HOME"
    tar -C "$HOME" -cf - --exclude='*/__pycache__' --exclude='.ssh/agent' "${paths[@]}" | tar -C "$tmp/home" -xf - \
        || die "copying the files failed"
    write_lists "$tmp/lists"
    archive="$folder/nexus-dev-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    (umask 077 && tar -C "$tmp" -czf "$archive" home lists) || die "writing $archive failed"
    chmod 600 "$archive"
    info "Packed ${#paths[@]} paths and the lists: $archive ($(du -h "$archive" | cut -f1))"
    info "It holds secrets: keep it on your own drive, not in the repository."
    printf '%s\n' "${paths[@]}" | sed 's/^/    /'
}

list() {
    local archive=$1
    [ -f "$archive" ] || die "no such archive: $archive"
    tar -tzf "$archive"
}

restore() {
    local archive=$1 force=$2 lists keep=(--skip-old-files --warning=existing-file)
    [ -f "$archive" ] || die "no such archive: $archive"
    $force && keep=(--overwrite)
    tar -C "$HOME" -xzf "$archive" --strip-components=1 "${keep[@]}" home || die "extracting $archive failed"
    chmod 700 "$HOME/.ssh" 2>/dev/null || true
    chmod 600 "$HOME"/.ssh/id_* 2>/dev/null || true
    chmod 644 "$HOME"/.ssh/*.pub 2>/dev/null || true
    chmod 600 "$HOME/.claude/.credentials.json" 2>/dev/null || true
    lists=$(cd "$(dirname "$archive")" && pwd -P)/nexus-dev-backup-lists
    mkdir -p "$lists"
    tar -C "$lists" -xzf "$archive" --strip-components=1 --overwrite lists || die "extracting the lists failed"
    info "The files are back in $HOME; the lists are in $lists:"
    ls "$lists" | sed 's/^/    /'
    info "What to install from them, in this order, is in SETUP.md. In short:"
    cat <<EOT
    brew bundle --file=$lists/Brewfile
    xargs -a <(grep -v '^#' $lists/flatpaks.txt | cut -f1) flatpak install -y flathub
    xargs -a $lists/vscode-extensions.txt -n1 code --install-extension
    rpm-ostree install <the LayeredPackages line of $lists/rpm-ostree-status.txt>, then reboot
EOT
    info "Delete $archive once everything works: it holds the SSH private key and Claude Code's sign-in."
}

case "${1:-}" in
    pack) pack "${2:-}" ;;
    list) [ -n "${2:-}" ] || die "list needs the archive"; list "$2" ;;
    restore)
        [ -n "${2:-}" ] || die "restore needs the archive"
        FORCE=false; [ "${3:-}" = --force ] && FORCE=true
        restore "$2" "$FORCE" ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
