# SPDX-License-Identifier: GPL-3.0-or-later
"""Game details page: the launch line for Steam, per-game monitoring settings and the recorded sessions.

The wrapper (gamemon) records a CSV per gameplay session; this page lists the games it has seen
(games.ini), lets monitoring and the on-screen overlay be turned on/off per game with its sample
interval, and opens the sessions as graphs.
"""

from __future__ import annotations

import html
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QSplitter, QVBoxLayout, QWidget,
)

from bc250_core.steam import find_steam

from . import ROOT, plain_tooltip
from . import gamecfg, gamecheck, steamlines
from .graph import show_graph

MUTED = "#9aa0a6"
ACCENT = "#ce93d8"
# Session checks (gamecheck): one color and one mark per verdict level.
CHECK_COLORS = {"ok": "#81c784", "info": MUTED, "warn": "#ffb74d", "error": "#e57373"}
CHECK_MARKS = {"ok": "✔", "info": "•", "warn": "!", "error": "✖"}


class StatChip(QFrame):
    """A small value-over-label tile, the same visual language as the dashboard stat boxes."""

    def __init__(self, label: str, tooltip: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setToolTip(plain_tooltip(tooltip))
        self.setStyleSheet("StatChip { background:rgba(255,255,255,0.045); border:1px solid #3a3f4a;"
                           " border-radius:8px; }")
        col = QVBoxLayout(self)
        col.setContentsMargins(12, 6, 12, 6)
        col.setSpacing(0)
        self.value = QLabel("—")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setStyleSheet("font-size:17px; font-weight:800; background:transparent;")
        self.label = QLabel(label)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(f"font-size:10px; font-weight:600; color:{MUTED}; background:transparent;")
        col.addWidget(self.value)
        col.addWidget(self.label)

    def set(self, text: str | None, accent: bool = False) -> None:
        self.value.setText(text if text else "—")
        color = ACCENT if accent and text else ("palette(text)" if text else MUTED)
        self.value.setStyleSheet(f"font-size:17px; font-weight:800; background:transparent; color:{color};")


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return "< 1 min"
    h, m = divmod(s // 60, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def session_duration(path: Path) -> float | None:
    """Length of a recorded session: the last elapsed_s in the CSV (a cheap tail read)."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 4096))
            lines = fh.read().decode("utf-8", "replace").strip().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            return float(line.split(",", 1)[0])
        except ValueError:
            continue
    return None


def gamemon_prefix() -> str:
    # Steam runs the launch options through /bin/sh with the game's folder as working directory,
    # so the package location must be on PYTHONPATH for `-m bazzite_check.gamemon` to be found.
    return f"PYTHONPATH={shlex.quote(str(ROOT))} {shlex.quote(sys.executable)} -m bazzite_check.gamemon"


def launch_line(with_mangohud: bool = False) -> str:
    game = "mangohud %command%" if with_mangohud else "%command%"
    return f"{gamemon_prefix()} {game}"


def session_files(key: str) -> list[Path]:
    try:
        return sorted(gamecfg.LOG_DIR.glob(f"bc250-game-{key}-*.csv"), reverse=True)
    except OSError:
        return []


def session_stats(rows: list[dict[str, str]], summary: dict) -> dict[str, float]:
    """Numbers for the stat chips: FPS, GPU load, GPU temperature and GPU power.

    The 1% low and the stutter share come from MangoHud's per-frame log when the wrapper found one
    for the session (the real thing, as test 48 computes it); without one the 1% low falls back to
    the worst 1% of the sampled averages, which hides single hitches."""
    out: dict[str, float] = {}
    for name in ("fps", "gpu_pct", "gpu_temp_c", "gpu_power_w"):
        if values := gamecheck.column(rows, name):
            out[name] = sum(values) / len(values)
    ft = summary.get("frametime")
    if isinstance(ft, dict) and ft.get("avg_fps") and ft.get("low1_fps"):
        out["fps"] = ft["avg_fps"]
        out["fps_low"] = ft["low1_fps"]
        out["stutter_pct"] = ft["stutter_pct"]
        out["fps_low_exact"] = 1.0
    elif values := gamecheck.column(rows, "fps"):
        worst = sorted(values)[:max(1, len(values) // 100)]
        out["fps_low"] = sum(worst) / len(worst)
    return out


# FPS comes from MangoHud's CSV log (monitor.py reads output_folder from these files). Logging is off
# by default in MangoHud; these helpers turn it on without touching anything else in the user's config.
_MANGO_AUTOSTART = re.compile(r"^\s*autostart_log\s*=\s*[1-9]", re.M)
_MANGO_OUTFOLDER = re.compile(r"^\s*output_folder\s*=", re.M)


def _mango_confs() -> list[Path]:
    native = Path.home() / ".config" / "MangoHud" / "MangoHud.conf"
    flatpak_cfg = Path.home() / ".var" / "app" / "com.valvesoftware.Steam" / "config"
    confs = [native]
    if flatpak_cfg.is_dir():                      # only when the Flatpak Steam exists
        confs.append(flatpak_cfg / "MangoHud" / "MangoHud.conf")
    return confs


def mango_logging_enabled() -> bool:
    if MANGO_CONF.is_file():                      # the app-owned config always has logging on
        return True
    try:
        text = _mango_confs()[0].read_text(encoding="utf-8")
    except OSError:
        return False
    return bool(_MANGO_AUTOSTART.search(text) and _MANGO_OUTFOLDER.search(text))


def enable_mango_logging() -> None:
    """Append output_folder and autostart_log=1 to MangoHud.conf where missing (raises OSError)."""
    folder = gamecfg.LOG_DIR / "mangohud"
    folder.mkdir(parents=True, exist_ok=True)
    for conf in _mango_confs():
        try:
            text = conf.read_text(encoding="utf-8")
        except OSError:
            text = ""
        lines = []
        if not _MANGO_OUTFOLDER.search(text):
            lines.append(f"output_folder={folder}")
        if not _MANGO_AUTOSTART.search(text):
            lines.append("autostart_log=1")
        if lines:
            conf.parent.mkdir(parents=True, exist_ok=True)
            head = text.rstrip("\n") + "\n" if text else ""
            conf.write_text(head + "# Added by BC-250 Bazzite Test: FPS for the Game details graphs\n"
                            + "\n".join(lines) + "\n", encoding="utf-8")


# MangoHud styled like our overlay (overlay.py). Rather than editing MangoHud.conf (where Bazzite's
# shipped defaults and presets keep merging back in), this is a complete config file that the app
# owns; gamemon passes it with MANGOHUD_CONFIGFILE so nothing else applies. A narrow two-column
# table gives one metric per line as far as MangoHud allows (it hard-wires temperature and power to
# the GPU row), and FPS logging for the graphs is always on in it. No border option exists, so the
# thin purple border has no equivalent.
MANGO_CONF = gamecfg.CONFIG_DIR / "MangoHud.conf"
_MANGO_STYLE_MARKER = "# BC-250 Bazzite Test overlay style"
MANGO_STYLE = """\
{marker}
# Written by the app; it is replaced whenever "Set MangoHud overlay style" is clicked.
legacy_layout=0
table_columns=2
fps
fps_text=FPS
gpu_stats
gpu_text=GPU
gpu_core_clock
gpu_temp
gpu_power
cpu_stats
vram
frametime=0
frame_timing=0
throttling_status=0
engine_version=0
text_outline=0
position=top-left
round_corners=10
background_color=111418
background_alpha=0.5
font_size=20
text_color=FFFFFF
gpu_color=FFFFFF
cpu_color=FFFFFF
vram_color=FFFFFF
# engine_color paints the FPS row label and the logging indicator dot in the top right corner.
# The dot cannot be hidden: MangoHud forces colors fully opaque and has no option to disable the
# indicator, which shows whenever logging is active — and logging stays on for the FPS graphs.
engine_color=FFFFFF
autostart_log=1
output_folder={log_folder}
"""


def style_mangohud() -> None:
    """Write the app-owned MangoHud config file (raises OSError) and drop the block that an older
    version of this action appended to the user's own MangoHud.conf files."""
    folder = gamecfg.LOG_DIR / "mangohud"
    folder.mkdir(parents=True, exist_ok=True)
    MANGO_CONF.parent.mkdir(parents=True, exist_ok=True)
    MANGO_CONF.write_text(MANGO_STYLE.format(marker=_MANGO_STYLE_MARKER, log_folder=folder),
                          encoding="utf-8")
    for conf in _mango_confs():
        try:
            text = conf.read_text(encoding="utf-8")
        except OSError:
            continue
        if _MANGO_STYLE_MARKER in text:
            conf.write_text(text.split(_MANGO_STYLE_MARKER)[0].rstrip("\n") + "\n", encoding="utf-8")


class InGamePage(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        title = QLabel("Game details")
        title.setStyleSheet("font-size:17px; font-weight:bold;")
        layout.addWidget(title)

        # Setup card: everything needed once to hook a game up in Steam, kept compact so the
        # selected game below is the main content of the page.
        setup = QFrame()
        setup.setObjectName("setupCard")
        setup.setStyleSheet("#setupCard { border:1px solid #3a3f4a; border-radius:8px;"
                            " background:rgba(255,255,255,0.03); }")
        sv = QVBoxLayout(setup)
        sv.setContentsMargins(12, 8, 12, 10)
        sv.setSpacing(6)

        head = QHBoxLayout()
        intro = QLabel(
            "<b>Steam setup</b> — record FPS, CPU/GPU load, clock, temperature and power while a game "
            "runs. Put one of these in the game's <i>Properties → Launch options</i> — the second also "
            "starts MangoHud, so FPS is recorded too:")
        intro.setWordWrap(True)
        head.addWidget(intro, 1)
        self.style_btn = QPushButton("Set MangoHud overlay style")
        self.style_btn.setToolTip(plain_tooltip(
            "Writes the app's own MangoHud config (~/.config/bc250-bazzite-test/MangoHud.conf) in the\n"
            "overlay's look: narrow box, rounded corners, purple FPS, muted labels, no clutter, and\n"
            "FPS logging on. The wrapper passes it to MangoHud directly, so your own MangoHud.conf\n"
            "and distribution presets are untouched and cannot mix into the look. It only applies to\n"
            "the launch lines here. (MangoHud has no border option, so no purple border.)"))
        self.style_btn.clicked.connect(self._style_mango)
        head.addWidget(self.style_btn, 0, Qt.AlignmentFlag.AlignTop)
        self.fps_btn = QPushButton("Enable FPS logging")
        self.fps_btn.setToolTip(plain_tooltip(
            "Adds output_folder and autostart_log=1 to ~/.config/MangoHud/MangoHud.conf (and Steam's\n"
            "Flatpak copy when present); nothing else in the file is changed. The game must still run\n"
            "with MangoHud: put `mangohud` in front of the launch line, or set MANGOHUD=1 (Vulkan)."))
        self.fps_btn.clicked.connect(self._enable_fps)
        head.addWidget(self.fps_btn, 0, Qt.AlignmentFlag.AlignTop)
        sv.addLayout(head)

        row = QHBoxLayout()
        self.cmd = QLineEdit(launch_line())
        self.cmd.setReadOnly(True)
        self.cmd.setToolTip(plain_tooltip(
            "The game starts unchanged; while it runs, a CSV is written to\n"
            f"{gamecfg.LOG_DIR}\nNo root is needed and the game is never slowed down noticeably."))
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: self._copy(self.cmd))
        row.addWidget(self.cmd, 1)
        row.addWidget(copy)
        sv.addLayout(row)

        row_fps = QHBoxLayout()
        self.cmd_fps = QLineEdit(launch_line(with_mangohud=True))
        self.cmd_fps.setReadOnly(True)
        self.cmd_fps.setToolTip(plain_tooltip(
            "Same, but the game starts under MangoHud so FPS is recorded too. Click \"Enable FPS\n"
            "logging\" once; if mangohud is not installed the wrapper skips it and the game\n"
            "still starts."))
        copy_fps = QPushButton("Copy")
        copy_fps.clicked.connect(lambda: self._copy(self.cmd_fps))
        row_fps.addWidget(self.cmd_fps, 1)
        row_fps.addWidget(copy_fps)
        sv.addLayout(row_fps)

        self.fps_note = QLabel()
        self.fps_note.setWordWrap(True)
        self.fps_note.setStyleSheet(f"color:{MUTED}; background:transparent;")
        sv.addWidget(self.fps_note)

        if steamlines.from_checkout(ROOT):
            checkout = QLabel(
                f"<span style='color:{CHECK_COLORS['warn']}'>{CHECK_MARKS['warn']}</span> This app runs from a "
                "checkout, so these lines name the checkout and its python. They stop working when that folder "
                "moves or its python goes; copy them from the installed app instead.")
            checkout.setWordWrap(True)
            checkout.setStyleSheet("background:transparent;")
            sv.addWidget(checkout)

        # Launch lines already in Steam whose gamemon can no longer start: the game then never starts.
        self.stale_box = QVBoxLayout()
        self.stale_box.setSpacing(4)
        sv.addLayout(self.stale_box)
        layout.addWidget(setup)
        self._update_fps_state()

        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("Games seen so far:"))
        self.games = QListWidget()
        self.games.currentItemChanged.connect(lambda *_: self._show_game())
        lv.addWidget(self.games, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        lv.addWidget(refresh)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        rv.setSpacing(8)

        # Hero banner: the screenshot with the title, playtime and per-game settings next to it.
        banner = QHBoxLayout()
        banner.setSpacing(12)
        shot_col = QVBoxLayout()
        shot_col.setSpacing(4)
        self.shot = QLabel()
        self.shot.setFixedSize(420, 236)
        self.shot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shot.setStyleSheet(f"color:{MUTED}; border:1px solid #555; border-radius:6px;")
        self.shot.setWordWrap(True)
        shot_col.addWidget(self.shot)
        self.reshoot = QPushButton("New screenshot")
        self.reshoot.setToolTip(plain_tooltip(
            "Removes the current screenshot; the wrapper takes a fresh one about 45 s into the next\n"
            "recorded session of this game."))
        self.reshoot.clicked.connect(self._new_shot)
        shot_col.addWidget(self.reshoot)
        banner.addLayout(shot_col)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        self.game_title = QLabel()
        self.game_title.setWordWrap(True)
        self.game_title.setStyleSheet("font-size:20px; font-weight:800;")
        info_col.addWidget(self.game_title)
        self.playtime = QLabel()
        self.playtime.setStyleSheet(f"color:{MUTED};")
        info_col.addWidget(self.playtime)
        self.last_played = QLabel()
        self.last_played.setStyleSheet(f"color:{MUTED};")
        info_col.addWidget(self.last_played)
        info_col.addSpacing(8)
        self.enabled = QCheckBox("Record this game")
        self.enabled.toggled.connect(self._save)
        info_col.addWidget(self.enabled)
        self.overlay = QCheckBox("Show overlay")
        self.overlay.setToolTip(plain_tooltip(
            "A small translucent box (rounded corners, thin purple border) on the screen with\n"
            "the live FPS, CPU/GPU load, clock, temperature, power and VRAM. It never takes focus and\n"
            "lets all mouse input through. Use \"Test overlay\" to drag it to where it should sit.\n"
            "Works over windowed and borderless-fullscreen games on the\n"
            "desktop; gamescope's game mode and exclusive fullscreen can cover it."))
        self.overlay.toggled.connect(self._save)
        ov_row = QHBoxLayout()
        ov_row.addWidget(self.overlay)
        test_overlay = QPushButton("Test overlay")
        test_overlay.setToolTip(plain_tooltip(
            "Shows the overlay with sample numbers for about 45 s. Drag it with the mouse to where\n"
            "it should sit — the position is saved and the in-game overlay (which is click-through)\n"
            "appears there. Run `python -m bazzite_check.overlay --demo` in a terminal to see start-up\n"
            "errors."))
        test_overlay.clicked.connect(self._test_overlay)
        ov_row.addWidget(test_overlay)
        ov_row.addStretch(1)
        info_col.addLayout(ov_row)
        iv = QHBoxLayout()
        iv.addWidget(QLabel("Sample every"))
        self.interval = QDoubleSpinBox()
        self.interval.setRange(gamecfg.MIN_INTERVAL_S, gamecfg.MAX_INTERVAL_S)
        self.interval.setDecimals(0)
        self.interval.setSuffix(" s")
        self.interval.valueChanged.connect(self._save)
        iv.addWidget(self.interval)
        iv.addStretch(1)
        info_col.addLayout(iv)
        info_col.addStretch(1)
        banner.addLayout(info_col, 1)
        rv.addLayout(banner)

        # Stat chips: hard numbers from the newest session, so the page shows how the game ran.
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.chip_sessions = StatChip("sessions", "Recorded sessions of this game.")
        self.chip_fps = StatChip("avg FPS", "Average FPS over the last session.\n"
                                            "Needs the MangoHud launch line, otherwise FPS is not in the log.")
        self.chip_low = StatChip("low 1% FPS", "The 1% low: the average of the worst 1% of frames in the last\n"
                                               "session, computed from MangoHud's per-frame log (purple) exactly as\n"
                                               "test 48 does. Without that log it falls back to the worst 1% of the\n"
                                               "sampled averages, which hides single hitches.")
        self.chip_stutter = StatChip("stutter", "Share of frames that took more than twice the median frametime —\n"
                                                "the visible hitches. Needs MangoHud's per-frame log.")
        self.chip_gpu = StatChip("avg GPU load", "Average GPU load over the last session. Far below 100%\n"
                                                 "usually means a CPU limit or an FPS cap.")
        self.chip_temp = StatChip("avg GPU temp", "Average GPU temperature over the last session.")
        self.chip_power = StatChip("avg GPU power", "Average GPU power draw over the last session.")
        for chip in (self.chip_sessions, self.chip_fps, self.chip_low, self.chip_stutter,
                     self.chip_gpu, self.chip_temp, self.chip_power):
            chips.addWidget(chip)
        chips.addStretch(1)
        rv.addLayout(chips)

        # Session checks: the verdicts over the newest session (gamecheck), so the page says what went
        # wrong and why, instead of only what the numbers were.
        self.checks_frame = QFrame()
        self.checks_frame.setObjectName("checksCard")
        self.checks_frame.setStyleSheet("#checksCard { border:1px solid #3a3f4a; border-radius:8px;"
                                        " background:rgba(255,255,255,0.03); }")
        self.checks_box = QVBoxLayout(self.checks_frame)
        self.checks_box.setContentsMargins(12, 8, 12, 10)
        self.checks_box.setSpacing(3)
        rv.addWidget(self.checks_frame)

        rv.addWidget(QLabel("Sessions (newest first):"))
        self.sessions = QListWidget()
        self.sessions.itemDoubleClicked.connect(lambda _i: self._graph())
        rv.addWidget(self.sessions, 1)
        buttons = QHBoxLayout()
        graph = QPushButton("Show graph")
        graph.clicked.connect(self._graph)
        folder = QPushButton("Open folder")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(gamecfg.LOG_DIR))))
        buttons.addWidget(graph)
        buttons.addWidget(folder)
        buttons.addStretch(1)
        rv.addLayout(buttons)
        split.addWidget(right)
        split.setSizes([230, 640])

        self.empty = QLabel("No games recorded yet. Add the launch line to a game in Steam and play; "
                            "the game appears here after the first session.")
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f"color:{MUTED};")
        layout.addWidget(self.empty)

        self._loading = False
        self.reload()

    # ------------------------------------------------------------------ data
    def reload(self) -> None:
        self._show_stale()
        current = self.games.currentItem().data(Qt.ItemDataRole.UserRole) if self.games.currentItem() else None
        self.games.clear()
        for cfg in sorted(gamecfg.load_all(), key=lambda c: (c.title or c.key).lower()):
            item = QListWidgetItem(cfg.title or cfg.key)
            item.setData(Qt.ItemDataRole.UserRole, cfg.key)
            self.games.addItem(item)
            if cfg.key == current:
                self.games.setCurrentItem(item)
        has_games = self.games.count() > 0
        self.empty.setVisible(not has_games)
        if has_games and self.games.currentRow() < 0:
            self.games.setCurrentRow(0)
        self._show_game()

    def _current_key(self) -> str | None:
        item = self.games.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _show_game(self) -> None:
        key = self._current_key()
        enabled = key is not None
        for w in (self.game_title, self.enabled, self.overlay, self.interval, self.sessions):
            w.setEnabled(enabled)
        self.sessions.clear()
        self.shot.clear()
        self.shot.setVisible(key is not None)
        self.reshoot.setVisible(key is not None)
        if key is None:
            self.game_title.setText("")
            self.playtime.setText("")
            self.last_played.setText("")
            self._set_chips(0, {})
            self._set_checks([])
            return
        cfg = gamecfg.load(key)
        self._loading = True
        self.game_title.setText(html.escape(cfg.title or key))
        if cfg.total_runtime_s > 0:
            text = f"Playtime: {fmt_duration(cfg.total_runtime_s)}"
            if cfg.last_runtime_s > 0:
                text += f" — last session {fmt_duration(cfg.last_runtime_s)}"
            self.playtime.setText(text)
        else:
            self.playtime.setText("")
        self.playtime.setVisible(bool(self.playtime.text()))
        self.enabled.setChecked(cfg.enabled)
        self.overlay.setChecked(cfg.overlay)
        self.interval.setValue(cfg.interval_s)
        self._loading = False
        self._show_shot(key)
        files = session_files(key)
        for path in files:
            try:
                stamp = time.strftime("%d-%m-%Y %H:%M", time.localtime(path.stat().st_mtime))
                size = f"{path.stat().st_size / 1024:.0f} KiB"
            except OSError:
                stamp, size = "", ""
            dur = session_duration(path)
            extra = f", {fmt_duration(dur)}" if dur else ""
            item = QListWidgetItem(f"{stamp}  ({size}{extra})")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(plain_tooltip(str(path)))
            self.sessions.addItem(item)
        if self.sessions.count():
            self.sessions.setCurrentRow(0)
        last = ""
        if files:
            try:
                last = time.strftime("%d-%m-%Y %H:%M", time.localtime(files[0].stat().st_mtime))
            except OSError:
                pass
        self.last_played.setText(f"Last played: {last}" if last else "")
        self.last_played.setVisible(bool(last))
        # The newest session is read once here: the chips and the checks both work on these rows.
        rows = gamecheck.read_rows(files[0]) if files else []
        summary = gamecheck.load_summary(files[0]) if files else {}
        self._set_chips(len(files), session_stats(rows, summary))
        self._set_checks(gamecheck.session_checks(rows, summary) if rows else [])

    def _set_chips(self, count: int, stats: dict[str, float]) -> None:
        def num(key: str, fmt: str) -> str | None:
            return fmt.format(stats[key]) if key in stats else None
        self.chip_sessions.set(str(count) if count else None)
        self.chip_fps.set(num("fps", "{:.0f}"), accent=True)
        # Accented only when it is the real per-frame low, not the fallback over sampled averages.
        self.chip_low.set(num("fps_low", "{:.0f}"), accent="fps_low_exact" in stats)
        self.chip_stutter.set(num("stutter_pct", "{:.1f}%"))
        self.chip_gpu.set(num("gpu_pct", "{:.0f}%"))
        self.chip_temp.set(num("gpu_temp_c", "{:.0f} °C"))
        self.chip_power.set(num("gpu_power_w", "{:.0f} W"))

    def _set_checks(self, checks: list[gamecheck.Check]) -> None:
        while (item := self.checks_box.takeAt(0)) is not None:
            if (w := item.widget()) is not None:
                w.deleteLater()
        self.checks_box.addWidget(QLabel("<b>Checks for the last session</b>"))
        if not checks:
            none = QLabel("No session recorded for this game yet.")
            none.setWordWrap(True)
            none.setStyleSheet(f"color:{MUTED}; background:transparent;")
            self.checks_box.addWidget(none)
            return
        for c in checks:
            color = CHECK_COLORS.get(c.level, MUTED)
            label = QLabel(f"<span style='color:{color}; font-weight:700;'>"
                           f"{CHECK_MARKS.get(c.level, '•')}</span> "
                           f"<b>{html.escape(c.title)}</b> — {html.escape(c.text)}")
            label.setWordWrap(True)
            label.setStyleSheet("background:transparent;")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.checks_box.addWidget(label)

    def _show_shot(self, key: str) -> None:
        path = gamecfg.shot_path(key)
        pix = QPixmap(str(path)) if path.exists() else QPixmap()
        self.reshoot.setEnabled(not pix.isNull())
        if pix.isNull():
            self.shot.setText("A screenshot is taken automatically during the next recorded session.")
            self.shot.setToolTip("")
            return
        self.shot.setPixmap(pix.scaled(self.shot.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
        self.shot.setToolTip(plain_tooltip(str(path)))

    def _show_stale(self) -> None:
        while self.stale_box.count():
            item = self.stale_box.takeAt(0)
            if (widget := item.widget()) is not None:
                widget.deleteLater()
            elif (row := item.layout()) is not None:
                while row.count():
                    if (w := row.takeAt(0).widget()) is not None:
                        w.deleteLater()
                row.deleteLater()
        stale = steamlines.stale_lines(find_steam(), gamemon_prefix())
        if not stale:
            return
        head = QLabel(
            f"<span style='color:{CHECK_COLORS['error']}'>{CHECK_MARKS['error']}</span> <b>"
            f"{len(stale)} game{'s' if len(stale) != 1 else ''} in Steam will not start</b>: "
            "their launch options start the game monitor from a place that is gone. Put the line below in the "
            "game's <i>Properties → Launch options</i> instead, or clear them; Refresh checks again.")
        head.setWordWrap(True)
        head.setStyleSheet("background:transparent;")
        self.stale_box.addWidget(head)
        for s in stale:
            label = QLabel(f"<b>{html.escape(s.name)}</b> — {html.escape(s.reason)}")
            label.setWordWrap(True)
            label.setStyleSheet("background:transparent;")
            label.setToolTip(plain_tooltip(f"Now in Steam:\n{s.line}"))
            self.stale_box.addWidget(label)
            row = QHBoxLayout()
            field = QLineEdit(s.fixed)
            field.setReadOnly(True)
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda _c=False, f=field: self._copy(f))
            row.addWidget(field, 1)
            row.addWidget(copy)
            self.stale_box.addLayout(row)

    # --------------------------------------------------------------- actions
    def _copy(self, field: QLineEdit) -> None:
        QGuiApplication.clipboard().setText(field.text())

    def _update_fps_state(self) -> None:
        on = mango_logging_enabled()
        self.fps_btn.setVisible(not on)
        self.fps_note.setText(
            "FPS logging is on; FPS appears in the overlay and the graphs." if on else
            "FPS comes from MangoHud's log (off by default) — the button turns it on.")

    def _enable_fps(self) -> None:
        try:
            enable_mango_logging()
        except OSError as exc:
            self.fps_note.setText(f"Could not update MangoHud.conf: {html.escape(str(exc))}")
            return
        self._update_fps_state()

    def _style_mango(self) -> None:
        try:
            style_mangohud()
        except OSError as exc:
            self.fps_note.setText(f"Could not update MangoHud.conf: {html.escape(str(exc))}")
            return
        self.fps_note.setText("MangoHud is styled like the overlay (takes effect at the next game start).")

    def _test_overlay(self) -> None:
        env = dict(os.environ)
        env.setdefault("QT_QPA_PLATFORM", "xcb;wayland")   # same choice as the wrapper
        try:
            subprocess.Popen([sys.executable, "-m", "bazzite_check.overlay", "--demo"],
                             env=env, cwd=str(ROOT))
        except OSError:
            pass

    def _new_shot(self) -> None:
        key = self._current_key()
        if key is None:
            return
        try:
            gamecfg.shot_path(key).unlink(missing_ok=True)
        except OSError:
            pass
        self.shot.clear()
        self._show_shot(key)

    def _save(self) -> None:
        key = self._current_key()
        if key is None or self._loading:
            return
        cfg = gamecfg.load(key)
        cfg.enabled = self.enabled.isChecked()
        cfg.overlay = self.overlay.isChecked()
        cfg.interval_s = self.interval.value()
        gamecfg.save(cfg)

    def _graph(self) -> None:
        item = self.sessions.currentItem()
        key = self._current_key()
        siblings = session_files(key) if key else []
        path = Path(item.data(Qt.ItemDataRole.UserRole)) if item else None
        show_graph(self, path, siblings, "No session recorded for this game yet.")
