#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Optional setup helper for bc250-bazzite-test: installs the tools the tests can use.
# The test script itself never installs anything; everything here is opt-in and idempotent.
#
# Usage:
#   ./development/tools/install-requirements.sh            # interactive: asks per group
#   ./development/tools/install-requirements.sh --rpms     # layer RPM packages (rpm-ostree, needs a reboot)
#   ./development/tools/install-requirements.sh --bins     # vkpeak + memtest_vulkan into ~/.local/bin
#   ./development/tools/install-requirements.sh --speedtest# Ookla speedtest CLI into ~/.local/bin
#   ./development/tools/install-requirements.sh --dev      # development extras (sqlite, to inspect the GUI history DB)
#   ./development/tools/install-requirements.sh --all      # everything above except --dev
set -euo pipefail

BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
RPMS=(stress-ng lm_sensors vkmark nvme-cli fio)
SPEEDTEST_VERSION="${SPEEDTEST_VERSION:-1.2.0}"

GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
say()  { echo -e "${GREEN}==>${NC} $*"; }
warn() { echo -e "${YELLOW}WARNING:${NC} $*" >&2; }
die()  { echo -e "${RED}ERROR:${NC} $*" >&2; exit 1; }

ask() {  # ask "question" -> 0 on yes
    local reply
    read -rp "$1 (y/n): " reply
    [[ $reply == [yY]* ]]
}

# ---------------------------------------------------------------- RPM packages
install_rpms() {
    command -v rpm-ostree >/dev/null 2>&1 || die "rpm-ostree not found: this group is for Bazzite/Fedora Atomic."
    local missing=()
    for pkg in "${RPMS[@]}"; do
        rpm -q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ ${#missing[@]} -eq 0 ]; then
        say "All RPM packages are already installed: ${RPMS[*]}"
        return
    fi
    say "Layering: ${missing[*]} (glmark2, vulkan-tools and smartmontools are usually already on Bazzite)"
    sudo rpm-ostree install "${missing[@]}"
    warn "Layered packages become active after a reboot: systemctl reboot"
}

# ------------------------------------------------- GitHub release binaries
latest_asset_url() {  # latest_asset_url owner/repo name-pattern
    curl -fsSL "https://api.github.com/repos/$1/releases/latest" \
        | grep -o "\"browser_download_url\": *\"[^\"]*$2[^\"]*\"" \
        | head -1 | cut -d'"' -f4
}

install_vkpeak() {
    if command -v vkpeak >/dev/null 2>&1; then
        say "vkpeak is already on PATH: $(command -v vkpeak)"
        return
    fi
    command -v unzip >/dev/null 2>&1 || die "unzip is needed to unpack vkpeak."
    local url tmp
    url=$(latest_asset_url "nihui/vkpeak" "ubuntu") || true
    [ -n "${url:-}" ] || { warn "Could not find a vkpeak release asset; install it manually from https://github.com/nihui/vkpeak/releases"; return; }
    say "Downloading vkpeak: $url"
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/vkpeak.zip" "$url"
    unzip -qo "$tmp/vkpeak.zip" -d "$tmp"
    install -Dm755 "$(find "$tmp" -type f -name vkpeak | head -1)" "$BIN_DIR/vkpeak"
    rm -rf "$tmp"
    say "Installed $BIN_DIR/vkpeak"
}

install_memtest_vulkan() {
    if command -v memtest_vulkan >/dev/null 2>&1; then
        say "memtest_vulkan is already on PATH: $(command -v memtest_vulkan)"
        return
    fi
    local url tmp
    url=$(latest_asset_url "GpuZelenograd/memtest_vulkan" "DesktopLinux_X86_64") || true
    [ -n "${url:-}" ] || { warn "Could not find a memtest_vulkan release asset; install it manually from https://github.com/GpuZelenograd/memtest_vulkan/releases"; return; }
    say "Downloading memtest_vulkan: $url"
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/memtest_vulkan.tar.xz" "$url"
    tar -xf "$tmp/memtest_vulkan.tar.xz" -C "$tmp"
    install -Dm755 "$(find "$tmp" -type f -name memtest_vulkan | head -1)" "$BIN_DIR/memtest_vulkan"
    rm -rf "$tmp"
    say "Installed $BIN_DIR/memtest_vulkan"
}

# ------------------------------------------------------------- Ookla speedtest
install_speedtest() {
    if command -v speedtest >/dev/null 2>&1; then
        say "speedtest is already on PATH: $(command -v speedtest)"
        return
    fi
    say "Downloading Ookla speedtest CLI ${SPEEDTEST_VERSION} (running it accepts Ookla's license and GDPR terms)"
    local tmp
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/speedtest.tgz" \
        "https://install.speedtest.net/app/cli/ookla-speedtest-${SPEEDTEST_VERSION}-linux-x86_64.tgz"
    tar -xzf "$tmp/speedtest.tgz" -C "$tmp" speedtest
    install -Dm755 "$tmp/speedtest" "$BIN_DIR/speedtest"
    rm -rf "$tmp"
    say "Installed $BIN_DIR/speedtest"
}

# --------------------------------------------------------- development extras
install_dev() {
    if command -v sqlite3 >/dev/null 2>&1; then
        say "sqlite3 is already installed (view the GUI history: sqlite3 ~/.local/share/bc250-bazzite-test/history.db)"
        return
    fi
    command -v rpm-ostree >/dev/null 2>&1 || die "rpm-ostree not found."
    say "Layering sqlite (development only: inspect the GUI's history database)"
    sudo rpm-ostree install sqlite
    warn "Active after a reboot: systemctl reboot"
}

# ------------------------------------------------------------------------ main
mkdir -p "$BIN_DIR"
case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) warn "$BIN_DIR is not on PATH; the test script still finds tools there, but your shell will not." ;;
esac

MODE="${1:-interactive}"
case "$MODE" in
    --rpms)      install_rpms ;;
    --bins)      install_vkpeak; install_memtest_vulkan ;;
    --speedtest) install_speedtest ;;
    --dev)       install_dev ;;
    --all)       install_rpms; install_vkpeak; install_memtest_vulkan; install_speedtest ;;
    interactive)
        ask "Layer RPM packages (${RPMS[*]})? Needs a reboot afterwards" && install_rpms
        ask "Install vkpeak and memtest_vulkan into $BIN_DIR?" && { install_vkpeak; install_memtest_vulkan; }
        ask "Install the Ookla speedtest CLI into $BIN_DIR?" && install_speedtest
        ask "Development extras (sqlite, to inspect the GUI history DB)?" && install_dev
        ;;
    *) die "Unknown option: $MODE (use --rpms, --bins, --speedtest, --dev, --all or no option)" ;;
esac
say "Done."
