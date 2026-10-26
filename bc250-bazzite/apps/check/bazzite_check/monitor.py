# SPDX-License-Identifier: GPL-3.0-or-later
"""Live CPU/GPU load and the running game, for the status bar.

Built to cost next to nothing, so it can stay on during gameplay:
- only plain file reads from /proc and sysfs, no helper programs;
- one sample every 2 s, and none while the window is minimized;
- the full process scan (which processes hold the GPU, which one is the game) runs every 10 s,
  the samples in between only re-read the handful of files that scan found;
- a sample that takes too long doubles the interval; the cost is shown in the tooltip.

GPU load, in order of preference:
1. gpu_busy_percent, the kernel load sensor (fails with EOPNOTSUPP on a stock Cyan Skillfish kernel);
2. gpu_metrics, when the governor's fix-metrics has mounted its patched copy (as MangoHud reads it);
3. gfx/compute engine time per client from /proc/<pid>/fdinfo, as nvtop and the stress test do.
   Only this user's processes are readable, which includes the games and the compositor.
Network speed: the byte counters of the physical interfaces (Ethernet, Wi-Fi) in /proc/net/dev, one
small file; the interface list is refreshed with the process scan.
Per-game GPU load always comes from (3). FPS comes from MangoHud's CSV log, which it writes and
flushes a row at a time, when logging is on.
"""

from __future__ import annotations

import os
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

RESCAN_S = 10.0
FPS_FRESH_S = 5.0
_AMDGPU = re.compile(r"^drm-driver:\s*amdgpu\s*$", re.M)
WINE_HELPERS = {"services.exe", "explorer.exe", "winedevice.exe", "plugplay.exe", "rpcss.exe",
                "svchost.exe", "conhost.exe", "start.exe", "wineboot.exe", "winemenubuilder.exe",
                "tabtip.exe", "steam.exe", "steamwebhelper.exe", "crashpad_handler.exe",
                "unitycrashhandler64.exe", "easyanticheat_eos_setup.exe", "cmd.exe"}


@dataclass
class GameInfo:
    title: str
    appid: str | None = None
    cpu: float | None = None
    gpu: float | None = None
    fps: float | None = None


@dataclass
class LiveSample:
    cpu: float | None = None
    gpu: float | None = None
    gpu_source: str = ""
    game: GameInfo | None = None
    cost_ms: float = 0.0
    scan_ms: float = 0.0
    net_down: float | None = None       # bit/s over all physical interfaces
    net_up: float | None = None
    net_ifaces: tuple[str, ...] = ()


@dataclass
class _Scan:
    drm_fds: list[tuple[int, str]] = field(default_factory=list)   # (pid, fd) of /dev/dri handles
    game_pids: set[int] = field(default_factory=set)
    title: str | None = None
    appid: str | None = None


def _read(path: Path, limit: int = 65536) -> str | None:
    try:
        with open(path, "rb") as fh:
            return fh.read(limit).decode(errors="replace")
    except OSError:
        return None


class Sampler:
    """Pure-Python sampler (no Qt), so it can be tested against a fake /proc tree."""

    def __init__(self, proc: Path = Path("/proc"), sys: Path = Path("/sys"), home: Path = Path.home()):
        self.proc, self.sys, self.home = proc, sys, home
        self.available = (proc / "stat").exists()
        self.ncpu = os.cpu_count() or 1
        self.clk_tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        self._cpu_prev: tuple[int, int] | None = None
        self._pid_prev: dict[int, int] = {}
        self._client_prev: dict[str, tuple[int, int]] = {}
        self._prev_t: float | None = None
        self._scan = _Scan()
        self._scan_t = -RESCAN_S
        self._scan_ms = 0.0
        self._titles: dict[str, str | None] = {}
        self._gpu_dev = self._find_gpu()
        self._mango_dirs: list[Path] = []
        self._net_ifaces: tuple[str, ...] = ()
        self._net_prev: tuple[int, int] | None = None

    # ------------------------------------------------------------ discovery
    def _find_gpu(self) -> Path | None:
        for dev in sorted((self.sys / "class" / "drm").glob("card*/device")):
            if (dev / "pp_dpm_sclk").exists():
                return dev
        return None

    def _gpu_sensor(self) -> tuple[float | None, str]:
        dev = self._gpu_dev
        if dev is None:
            return None, ""
        v = _read(dev / "gpu_busy_percent", 16)
        if v is not None and v.strip().isdigit():
            return float(v.strip()), "sensor"
        # Without fix-metrics a stock kernel's gpu_metrics holds 0 or 0xFFFF (the "0%" / "655%" overlay bug).
        mounts = _read(self.proc / "self" / "mountinfo") or ""
        if "gpu_metrics" in mounts:
            try:
                raw = (dev / "gpu_metrics").read_bytes()[:32]
                # APU layout v2.x: header(4) temp_gfx temp_soc temp_core[8] temp_l3[2] average_gfx_activity
                if len(raw) >= 30 and raw[2] == 2:
                    (activity,) = struct.unpack_from("<H", raw, 28)
                    if activity <= 100:
                        return float(activity), "gpu_metrics"
            except OSError:
                pass
        return None, "fdinfo"

    def _mangohud_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        for conf in (self.home / ".config" / "bc250-bazzite-test" / "MangoHud.conf",
                     self.home / ".config" / "MangoHud" / "MangoHud.conf",
                     self.home / ".var" / "app" / "com.valvesoftware.Steam" / "config" / "MangoHud" / "MangoHud.conf"):
            text = _read(conf) or ""
            for m in re.finditer(r"^\s*output_folder\s*=\s*(.+?)\s*$", text, re.M):
                dirs.append(Path(os.path.expandvars(m.group(1).replace("~", str(self.home), 1))))
        return dirs or [self.home]

    def _steam_title(self, appid: str) -> str | None:
        if appid in self._titles:
            return self._titles[appid]
        title = None
        roots = [self.home / ".local" / "share" / "Steam", self.home / ".steam" / "steam",
                 self.home / ".var" / "app" / "com.valvesoftware.Steam" / ".local" / "share" / "Steam"]
        libraries = [r / "steamapps" for r in roots]
        for root in roots:
            vdf = _read(root / "steamapps" / "libraryfolders.vdf") or ""
            libraries += [Path(p) / "steamapps" for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
        for lib in libraries:
            acf = _read(lib / f"appmanifest_{appid}.acf")
            if acf and (m := re.search(r'"name"\s+"([^"]+)"', acf)):
                title = m.group(1)
                break
        self._titles[appid] = title
        return title

    def _find_net_ifaces(self) -> tuple[str, ...]:
        """Physical network interfaces (they have a device link); skips lo, bridges, VPN and container links."""
        try:
            names = sorted(os.listdir(self.sys / "class" / "net"))
        except OSError:
            return ()
        return tuple(n for n in names if (self.sys / "class" / "net" / n / "device").exists())

    def _net_rates(self, dt: float) -> tuple[float | None, float | None]:
        text = _read(self.proc / "net" / "dev", 16384)
        if not text or not self._net_ifaces:
            self._net_prev = None
            return None, None
        rx = tx = 0
        for line in text.splitlines()[2:]:
            name, _, data = line.partition(":")
            if name.strip() in self._net_ifaces:
                fields = data.split()
                if len(fields) >= 9:
                    rx += int(fields[0])
                    tx += int(fields[8])
        prev, self._net_prev = self._net_prev, (rx, tx)
        if prev is None or dt <= 0 or rx < prev[0] or tx < prev[1]:
            return None, None
        return (rx - prev[0]) * 8 / dt, (tx - prev[1]) * 8 / dt

    def _rescan(self) -> None:
        t0 = time.perf_counter()
        ifaces = self._find_net_ifaces()
        if ifaces != self._net_ifaces:
            self._net_ifaces, self._net_prev = ifaces, None
        scan = _Scan()
        children: dict[int, list[int]] = {}
        reaper: tuple[int, str] | None = None
        try:
            pids = [int(d) for d in os.listdir(self.proc) if d.isdigit()]
        except OSError:
            pids = []
        drm_pids: set[int] = set()
        for pid in pids:
            base = self.proc / str(pid)
            stat = _read(base / "stat", 512)
            if not stat or ")" not in stat:
                continue
            comm = stat[stat.find("(") + 1:stat.rfind(")")]
            fields = stat[stat.rfind(")") + 2:].split()
            if len(fields) > 1 and fields[1].isdigit():
                children.setdefault(int(fields[1]), []).append(pid)
            if comm == "reaper" and reaper is None:
                cmd = (_read(base / "cmdline", 4096) or "").replace("\0", " ")
                if "SteamLaunch" in cmd and (m := re.search(r"AppId=(\d+)", cmd)):
                    reaper = (pid, m.group(1))
            try:
                fds = os.listdir(base / "fd")          # other users' processes: PermissionError, skipped
            except OSError:
                continue
            for fd in fds:
                try:
                    if os.readlink(base / "fd" / fd).startswith("/dev/dri/"):
                        scan.drm_fds.append((pid, fd))
                        drm_pids.add(pid)
                except OSError:
                    pass

        def tree(root: int) -> set[int]:
            out, todo = set(), [root]
            while todo:
                p = todo.pop()
                if p not in out:
                    out.add(p)
                    todo += children.get(p, [])
            return out

        # The game's own .exe (Proton/Wine) that holds the GPU; also names non-Steam games.
        exe_pid, exe_name = None, None
        candidates = tree(reaper[0]) & drm_pids if reaper else drm_pids
        for pid in sorted(candidates):
            argv0 = (_read(self.proc / str(pid) / "cmdline", 4096) or "").split("\0")[0]
            name = re.split(r"[\\/]", argv0)[-1]
            if name.lower().endswith(".exe") and name.lower() not in WINE_HELPERS:
                exe_pid, exe_name = pid, name[:-4]
                break

        if reaper:
            scan.appid = reaper[1] if reaper[1] != "0" else None
            scan.game_pids = tree(reaper[0])
            scan.title = (scan.appid and self._steam_title(scan.appid)) or exe_name or (
                f"Steam app {scan.appid}" if scan.appid else "Non-Steam game")
        elif exe_pid is not None:
            scan.game_pids = tree(exe_pid)
            scan.title = exe_name
        self._scan = scan
        self._mango_dirs = self._mangohud_dirs()
        self._scan_ms = (time.perf_counter() - t0) * 1000

    # ------------------------------------------------------------- sampling
    def _cpu_total(self) -> float | None:
        line = (_read(self.proc / "stat", 256) or "").split("\n", 1)[0].split()
        if len(line) < 5 or line[0] != "cpu":
            return None
        vals = [int(v) for v in line[1:9]]
        idle, total = vals[3] + vals[4], sum(vals)
        prev, self._cpu_prev = self._cpu_prev, (total - idle, total)
        if not prev or total <= prev[1]:
            return None
        return max(0.0, min(100.0, 100 * (total - idle - prev[0]) / (total - prev[1])))

    def _engine_busy(self, dt_ns: int) -> tuple[float | None, float | None]:
        """(all clients, game clients) busy % from fdinfo; the busier of gfx and compute."""
        cur: dict[str, tuple[int, int]] = {}
        owner: dict[str, int] = {}
        for pid, fd in self._scan.drm_fds:
            text = _read(self.proc / str(pid) / "fdinfo" / fd, 4096)
            if not text or not _AMDGPU.search(text):
                continue
            m = re.search(r"^drm-client-id:\s*(\d+)", text, re.M)
            if not m or m.group(1) in cur:
                continue
            gfx = re.search(r"^drm-engine-gfx:\s*(\d+)", text, re.M)
            comp = re.search(r"^drm-engine-compute:\s*(\d+)", text, re.M)
            cur[m.group(1)] = (int(gfx.group(1)) if gfx else 0, int(comp.group(1)) if comp else 0)
            owner[m.group(1)] = pid
        prev, self._client_prev = self._client_prev, cur
        if not prev or dt_ns <= 0:
            return None, None
        sums = {"all": [0, 0], "game": [0, 0]}
        for cid, (g, c) in cur.items():
            if cid not in prev or g < prev[cid][0] or c < prev[cid][1]:
                continue
            for key in ("all", "game") if owner[cid] in self._scan.game_pids else ("all",):
                sums[key][0] += g - prev[cid][0]
                sums[key][1] += c - prev[cid][1]
        pct = {k: min(100.0, 100 * max(v) / dt_ns) for k, v in sums.items()}
        return pct["all"], (pct["game"] if self._scan.game_pids else None)

    def _game_cpu(self, dt_s: float) -> float | None:
        cur: dict[int, int] = {}
        for pid in self._scan.game_pids:
            stat = _read(self.proc / str(pid) / "stat", 512)
            if stat and ")" in stat:
                f = stat[stat.rfind(")") + 2:].split()
                if len(f) > 12:
                    cur[pid] = int(f[11]) + int(f[12])     # utime + stime
        prev, self._pid_prev = self._pid_prev, cur
        if not prev or dt_s <= 0:
            return None
        ticks = sum(t - prev[p] for p, t in cur.items() if p in prev and t >= prev[p])
        return min(100.0, 100 * ticks / (dt_s * self.clk_tck * self.ncpu))

    def _mangohud_fps(self) -> tuple[float | None, str | None]:
        newest, newest_t = None, 0.0
        now = time.time()
        for d in self._mango_dirs:
            try:
                with os.scandir(d) as it:
                    for e in it:
                        if e.name.endswith(".csv") and not e.name.endswith("_summary.csv"):
                            mt = e.stat().st_mtime
                            if mt > newest_t:
                                newest, newest_t = e.path, mt
            except OSError:
                continue
        if not newest or now - newest_t > FPS_FRESH_S:
            return None, None
        try:
            with open(newest, "rb") as fh:
                fh.seek(max(0, os.path.getsize(newest) - 2048))
                lines = fh.read().decode(errors="replace").split("\n")[1:-1]
        except OSError:
            return None, None
        fps = []
        for line in lines[-20:]:
            head = line.split(",", 1)[0]
            try:
                fps.append(float(head))
            except ValueError:
                continue
        # MangoHud names the log <program>_<date>.csv.
        program = re.sub(r"_\d{4}-\d{2}-\d{2}.*$", "", Path(newest).stem)
        return (sum(fps) / len(fps) if fps else None), program

    def sample(self) -> LiveSample:
        if not self.available:
            return LiveSample()
        t0 = time.perf_counter()
        now = time.monotonic()
        scanned = False
        if now - self._scan_t >= RESCAN_S:
            self._rescan()
            self._scan_t = now
            scanned = True
        dt = (now - self._prev_t) if self._prev_t else 0.0
        self._prev_t = now

        s = LiveSample(cpu=self._cpu_total())
        s.gpu, s.gpu_source = self._gpu_sensor()
        need_fdinfo = s.gpu_source == "fdinfo" or self._scan.game_pids
        if need_fdinfo:
            total, game_gpu = self._engine_busy(int(dt * 1e9))
            if s.gpu_source == "fdinfo":
                s.gpu = total
        else:
            game_gpu = None
        fps, program = self._mangohud_fps()
        if self._scan.game_pids or fps is not None:
            s.game = GameInfo(self._scan.title or program or "Game", self._scan.appid,
                              self._game_cpu(dt) if self._scan.game_pids else None, game_gpu, fps)
        elif self._pid_prev:
            self._pid_prev = {}
        s.net_down, s.net_up = self._net_rates(dt)
        s.net_ifaces = self._net_ifaces
        s.cost_ms = (time.perf_counter() - t0) * 1000
        s.scan_ms = self._scan_ms if scanned else 0.0
        return s
