# SPDX-License-Identifier: GPL-3.0-or-later
"""In-game monitoring wrapper for the Steam launch options (like `mangohud %command%`).

Usage, in the game's Properties > Launch options (the Game details page shows the exact line with a Copy
button — Steam starts this wrapper in the game's folder, so PYTHONPATH must point at the app's folder):

    PYTHONPATH=<app folder> <python> -m bazzite_check.gamemon %command%

It starts the game unchanged and, while the game runs, samples FPS (from MangoHud's log, when MangoHud
is active), the game's CPU and GPU share, total CPU/GPU load, the GPU clocks, temperature, power,
voltage and memory (VRAM and GTT), plus the CPU temperature and clock, the fan and the free system
memory into a CSV in ~/.local/share/bc250-bazzite-test/game-logs/. When the game ends, a small JSON
sidecar is written next to the CSV with the memory budget, the GPU power cap, the real 1%/0.1% lows
from MangoHud's per-frame log and any amdgpu errors the kernel logged during the session; the Game
details page turns those into pass/warn/fail checks (gamecheck.py). The app's Game details page shows
the exact launch line, the per-game settings (on/off, sample interval, overlay) and the recorded
sessions as graphs. With "Show overlay" on, the samples are also shown live in a small translucent box
on screen (see overlay.py), like MangoHud's HUD but in the app's style.

Everything is read from /proc and sysfs as the normal user: no root, no helpers, one sample every few
seconds. If monitoring is disabled for the game (or sampling fails), the game still runs unchanged.
The length of every session is written to games.ini (last session and total playtime), also when
recording is off for the game.
Options before the game command: --interval=<seconds> overrides the per-game setting.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from . import gamecfg, gamecheck
from .monitor import Sampler, _read

FIELDS = ["elapsed_s", "fps", "game_cpu_pct", "game_gpu_pct", "cpu_pct", "gpu_pct",
          "sclk_mhz", "mclk_mhz", "gpu_temp_c", "gpu_power_w", "vram_used_mib", "gtt_used_mib",
          "vddgfx_mv", "fan_rpm", "cpu_temp_c", "cpu_mhz_avg", "mem_avail_mib"]
IDENTIFY_S = 30.0       # how long to wait for the process scan to name the game before using a fallback
SCREENSHOT_S = 45.0     # one screenshot per game, this far into the session (past the loading screens)

# Screenshot tools in order of preference: gamescope (game mode), Spectacle (KDE desktop mode,
# Bazzite's desktop), then wlroots/GNOME, each saving straight to a file without a dialog.
SCREENSHOT_CMDS = [["gamescopectl", "screenshot"], ["spectacle", "-b", "-n", "-o"],
                   ["grim"], ["gnome-screenshot", "-f"]]


def take_screenshot(path: Path) -> None:
    """Best effort, one-time: first available tool wins; silent when none works."""
    for cmd in SCREENSHOT_CMDS:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run([*cmd, str(path)], timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if path.exists() and path.stat().st_size > 0:
            print(f"gamemon: screenshot saved to {path}", file=sys.stderr)
            return
    print("gamemon: no screenshot (no tool worked); it is retried next session", file=sys.stderr)


def start_overlay() -> subprocess.Popen | None:
    """The on-screen overlay as its own process: if Qt is missing or it crashes, the game is untouched.

    On Wayland a normal window cannot be positioned or kept on top (and an unparented tool window may
    not show at all), so the overlay prefers XWayland (xcb); Qt falls back to wayland without it.
    Its stderr is inherited so a start-up problem is visible in Steam's log for the game."""
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "xcb;wayland")
    try:
        proc = subprocess.Popen([sys.executable, "-m", "bazzite_check.overlay"],
                                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                text=True, env=env)
    except OSError as exc:
        print(f"gamemon: overlay did not start ({exc}); recording continues", file=sys.stderr)
        return None
    print(f"gamemon: overlay started (pid {proc.pid})", file=sys.stderr)
    return proc


def _num(path: Path, scale: float = 1.0) -> float | None:
    text = _read(path, 64)
    try:
        return float(text.strip()) * scale if text else None
    except ValueError:
        return None


class GpuTelemetry:
    """GPU clocks, temperature, power, voltage and memory from sysfs (world-readable on amdgpu)."""

    def __init__(self, dev: Path | None):
        self.dev = dev
        self.hwmon = None
        if dev is not None:
            for h in sorted((dev / "hwmon").glob("hwmon*")):
                self.hwmon = h
                break

    @staticmethod
    def _dpm(path: Path) -> float | None:
        """The active level (the one marked "*") of a pp_dpm_* table, in MHz."""
        for line in (_read(path, 4096) or "").splitlines():
            if line.rstrip().endswith("*") and "Mhz" in line:
                try:
                    return float(line.split(":", 1)[1].split("Mhz")[0])
                except (IndexError, ValueError):
                    return None
        return None

    def read(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {k: None for k in
                                        ("sclk_mhz", "mclk_mhz", "gpu_temp_c", "gpu_power_w",
                                         "vram_used_mib", "gtt_used_mib", "vddgfx_mv")}
        if self.dev is None:
            return out
        out["sclk_mhz"] = self._dpm(self.dev / "pp_dpm_sclk")
        out["mclk_mhz"] = self._dpm(self.dev / "pp_dpm_mclk")
        out["vram_used_mib"] = _num(self.dev / "mem_info_vram_used", 1 / (1024 * 1024))
        out["gtt_used_mib"] = _num(self.dev / "mem_info_gtt_used", 1 / (1024 * 1024))
        if self.hwmon is not None:
            out["gpu_temp_c"] = _num(self.hwmon / "temp1_input", 1 / 1000)
            power = _num(self.hwmon / "power1_average", 1 / 1_000_000)
            if power is None:
                power = _num(self.hwmon / "power1_input", 1 / 1_000_000)
            out["gpu_power_w"] = power
            out["vddgfx_mv"] = _num(self.hwmon / "in0_input")
        return out

    def budget(self) -> dict[str, float]:
        """The ceilings a session is judged against; they never change while a game runs, so this is
        read once, at the end, for the session summary."""
        out: dict[str, float] = {}
        if self.dev is not None:
            for key, name in (("vram_total_mib", "mem_info_vram_total"),
                              ("gtt_total_mib", "mem_info_gtt_total")):
                if (v := _num(self.dev / name, 1 / (1024 * 1024))) is not None:
                    out[key] = v
        if self.hwmon is not None and (cap := _num(self.hwmon / "power1_cap", 1 / 1_000_000)):
            out["power_cap_w"] = cap
        if (total := _meminfo("MemTotal:")) is not None:
            out["mem_total_mib"] = total
        return out


def _meminfo(field: str) -> float | None:
    """One /proc/meminfo field in MiB (the file is in kB)."""
    for line in (_read(Path("/proc/meminfo"), 4096) or "").splitlines():
        if line.startswith(field):
            try:
                return int(line.split()[1]) / 1024
            except (IndexError, ValueError):
                return None
    return None


class SystemTelemetry:
    """CPU temperature, average CPU clock, fan speed and free RAM — all without root.

    The BC-250's heat and memory pressure are what spoil long sessions, and neither showed up in the
    game logs before: the GPU hwmon has no fan on most boards (the SuperIO one does) and the CPU
    temperature lives in a different hwmon again, so every hwmon is scanned once at start-up."""

    CPU_HWMON = ("k10temp", "zenpower", "coretemp")

    def __init__(self, sys_root: Path = Path("/sys"), proc: Path = Path("/proc")):
        self.proc = proc
        self.cpu_temp: Path | None = None
        self.fans: list[Path] = []
        for h in sorted((sys_root / "class" / "hwmon").glob("hwmon*")):
            name = (_read(h / "name", 64) or "").strip()
            if self.cpu_temp is None and name in self.CPU_HWMON and (h / "temp1_input").exists():
                self.cpu_temp = h / "temp1_input"
            self.fans += sorted(h.glob("fan*_input"))
        self.freqs = sorted((sys_root / "devices" / "system" / "cpu")
                            .glob("cpu[0-9]*/cpufreq/scaling_cur_freq"))

    def read(self) -> dict[str, float | None]:
        out: dict[str, float | None] = {"cpu_temp_c": None, "cpu_mhz_avg": None,
                                        "fan_rpm": None, "mem_avail_mib": None}
        if self.cpu_temp is not None:
            out["cpu_temp_c"] = _num(self.cpu_temp, 1 / 1000)
        khz = [v for f in self.freqs if (v := _num(f)) is not None]
        if khz:
            out["cpu_mhz_avg"] = sum(khz) / len(khz) / 1000
        rpm = [v for f in self.fans if (v := _num(f)) is not None]
        if rpm:
            out["fan_rpm"] = max(rpm)
        out["mem_avail_mib"] = _meminfo("MemAvailable:")
        return out


def _fmt(v: float | None) -> str:
    return f"{v:.1f}" if v is not None else ""


def _parse_args(argv: list[str]) -> tuple[float | None, list[str]]:
    interval = None
    i = 0
    while i < len(argv) and argv[i].startswith("--"):
        arg = argv[i]
        if arg.startswith("--interval"):
            value = arg.partition("=")[2]
            if not value and i + 1 < len(argv):
                i += 1
                value = argv[i]
            try:
                interval = float(value)
            except ValueError:
                print(f"gamemon: bad --interval value {value!r}", file=sys.stderr)
                return None, []
        else:
            print(f"gamemon: unknown option {arg!r}", file=sys.stderr)
            return None, []
        i += 1
    return interval, argv[i:]


def main(argv: list[str] | None = None) -> int:
    interval_arg, cmd = _parse_args(sys.argv[1:] if argv is None else argv)
    if not cmd:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    # The FPS launch line prefixes the game with mangohud; without it installed the game must still start.
    if cmd[0] == "mangohud" and len(cmd) > 1 and shutil.which("mangohud") is None:
        print("gamemon: mangohud is not installed; starting the game without it (no FPS)", file=sys.stderr)
        cmd = cmd[1:]

    # When the app has written its own MangoHud config ("Set MangoHud overlay style" on the Game details page), hand it
    # to MangoHud directly so distribution defaults and presets cannot mix into the look.
    env = None
    mango_conf = gamecfg.CONFIG_DIR / "MangoHud.conf"
    if cmd[0] == "mangohud" and mango_conf.is_file():
        env = dict(os.environ)
        env.pop("MANGOHUD_CONFIG", None)
        env["MANGOHUD_CONFIGFILE"] = str(mango_conf)

    try:
        game = subprocess.Popen(cmd, env=env)
    except OSError as exc:
        print(f"gamemon: could not start {cmd[0]!r}: {exc}", file=sys.stderr)
        return 127

    # Steam stops the wrapper with SIGTERM; pass it on so the game closes cleanly.
    def forward(signum: int, _frame) -> None:
        try:
            game.send_signal(signum)
        except OSError:
            pass
    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)

    fallback_name = Path(cmd[1] if cmd[0] == "mangohud" and len(cmd) > 1 else cmd[0]).name
    fallback = gamecfg.slug(fallback_name)
    start = time.monotonic()
    start_epoch = time.time()       # wall clock: MangoHud's logs and the journal are timestamped

    def record_runtime(game_key: str, title: str) -> None:
        """Length of this session into games.ini (last + total), also when recording is off."""
        try:
            gamecfg.add_runtime(game_key, title, time.monotonic() - start)
        except Exception:
            pass

    # From here on the game is running; a monitoring problem must never take it down.
    try:
        sampler = Sampler()
        telemetry = GpuTelemetry(sampler._gpu_dev)
        system = SystemTelemetry()
    except Exception as exc:
        print(f"gamemon: monitoring disabled ({exc}); the game runs unmonitored", file=sys.stderr)
        rc = game.wait()
        record_runtime(fallback, fallback_name)
        return rc
    key: str | None = None
    cfg: gamecfg.GameConfig | None = None
    interval = interval_arg or gamecfg.DEFAULT_INTERVAL_S
    rows: list[dict[str, str]] = []
    writer: csv.DictWriter | None = None
    out = None
    overlay: subprocess.Popen | None = None
    shot_started = False
    log_path: Path | None = None

    def open_log(game_key: str) -> None:
        nonlocal writer, out, log_path
        gamecfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        path = gamecfg.LOG_DIR / f"bc250-game-{game_key}-{stamp}.csv"
        out = path.open("w", newline="", encoding="utf-8")
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        rows.clear()
        out.flush()
        log_path = path
        print(f"gamemon: recording to {path}", file=sys.stderr)

    def write_summary() -> None:
        """The session sidecar: the ceilings, the real frametime statistics and the kernel's view of
        the session. The Game details page turns it into pass/warn/fail checks (gamecheck)."""
        end_epoch = time.time()
        summary: dict = {"start_epoch": start_epoch, "end_epoch": end_epoch,
                         "duration_s": end_epoch - start_epoch,
                         "budget": telemetry.budget(),
                         "frametime": None,
                         "kernel_errors": gamecheck.kernel_errors(start_epoch, end_epoch)}
        mango = gamecheck.find_mangohud_log(sampler._mangohud_dirs(), start_epoch, end_epoch)
        if mango is not None and (ft := gamecheck.frametime_stats(mango)):
            summary["frametime"] = asdict(ft)
            summary["frametime_log"] = str(mango)
        gamecheck.write_summary(log_path, summary)
        print(f"gamemon: session checks written to {gamecheck.summary_path(log_path)}", file=sys.stderr)

    try:
        while game.poll() is None:
            time.sleep(interval)
            try:
                s = sampler.sample()
                if key is None:
                    info = s.game
                    if info is not None and (info.appid or info.title):
                        key = gamecfg.game_key(info.appid, info.title)
                        cfg = gamecfg.remember(key, info.title)
                    elif time.monotonic() - start >= IDENTIFY_S:
                        key = fallback
                        cfg = gamecfg.remember(key, fallback_name)
                    if cfg is not None:
                        if not cfg.enabled:
                            print(f"gamemon: monitoring is off for {cfg.title or key} (Game details page)",
                                  file=sys.stderr)
                            break
                        if interval_arg is None:
                            interval = cfg.interval_s
                        open_log(key)
                        if cfg.overlay:
                            overlay = start_overlay()
                g = s.game
                elapsed = time.monotonic() - start
                if (key is not None and elapsed >= SCREENSHOT_S and not shot_started
                        and not gamecfg.shot_path(key).exists()):
                    shot_started = True
                    threading.Thread(target=take_screenshot, args=(gamecfg.shot_path(key),),
                                     daemon=True).start()
                row = {"elapsed_s": f"{elapsed:.1f}",
                       "fps": _fmt(g.fps if g else None),
                       "game_cpu_pct": _fmt(g.cpu if g else None),
                       "game_gpu_pct": _fmt(g.gpu if g else None),
                       "cpu_pct": _fmt(s.cpu), "gpu_pct": _fmt(s.gpu)}
                row.update({k: _fmt(v) for k, v in telemetry.read().items()})
                row.update({k: _fmt(v) for k, v in system.read().items()})
                if writer is not None and out is not None:
                    writer.writerow(row)
                    out.flush()
                else:
                    rows.append(row)
                if overlay is not None and overlay.stdin is not None:
                    try:
                        overlay.stdin.write(json.dumps(row) + "\n")
                        overlay.stdin.flush()
                    except (OSError, ValueError):   # overlay gone; keep recording
                        overlay = None
            except Exception:                      # monitoring must never kill the game
                continue
        return game.wait()
    finally:
        if out is not None:
            out.close()
        if log_path is not None:
            try:
                write_summary()
            except Exception as exc:        # the summary must never break the exit path
                print(f"gamemon: no session summary ({exc})", file=sys.stderr)
        if overlay is not None:
            try:
                if overlay.stdin is not None:
                    overlay.stdin.close()       # EOF makes the overlay quit by itself
                overlay.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                overlay.kill()
        if game.poll() is None:
            game.wait()
        record_runtime(key or fallback, (cfg.title if cfg else "") or fallback_name)


if __name__ == "__main__":
    sys.exit(main())
