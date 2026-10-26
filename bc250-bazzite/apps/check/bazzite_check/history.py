# SPDX-License-Identifier: GPL-3.0-or-later
"""Test history in SQLite: every run, the result of every test and the key numbers, for statistics that
survive a restart and (later) browsing and comparing past runs.

Full output stays in the log files; the database only points to them. A run writes a few dozen rows and
the counters are one query, so the cost is negligible.
"""

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .logstore import log_dir

SCHEMA_VERSION = 1
SCRIPT_LOG_DIR = Path("/var/log/bc250-bazzite-test")
DESKTOP_DIR = Path.home() / "Desktop" / "bc250-bazzite-test"
REPORT_GLOB = "bc250-test-results-*.log"
_REPORT_TS = re.compile(r"bc250-test-results-(\d{8}-\d{6})\.log$")
_TS_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - ")
_TAG = re.compile(r"^(?:SUCCESS|INFO|WARNING|ERROR|FAILURE|HINT|NOTE):\s*")
_REPORT_PATH = re.compile(r"Review results in (/\S+?\.log)")


def db_path() -> Path:
    return log_dir().parent / "history.db"


# ------------------------------------------------------------------ line scanning
_NUM = r"(-?\d+(?:\.\d+)?)"
# (regex on the line body without timestamp/tag, [metric names for its groups])
_METRICS: list[tuple[re.Pattern, list[str]]] = [
    (re.compile(rf"^sclk\s+min {_NUM} / avg {_NUM} / max {_NUM} MHz"), ["stress.sclk_min", "stress.sclk_avg", "stress.sclk_max"]),
    (re.compile(rf"^GPU busy\s+avg {_NUM} / max {_NUM}"), ["stress.busy_avg", "stress.busy_max"]),
    (re.compile(rf"^GPU temp\s+max {_NUM}"), ["stress.gpu_temp_max"]),
    (re.compile(rf"^GPU power avg {_NUM} / max {_NUM}"), ["stress.gpu_power_avg", "stress.gpu_power_max"]),
    (re.compile(rf"^CPU Tctl\s+max {_NUM}"), ["stress.cpu_temp_max"]),
    (re.compile(rf"^Fan\s+max {_NUM}"), ["stress.fan_max"]),
    (re.compile(rf"^Download: {_NUM} Mbps"), ["net.down_mbps"]),
    (re.compile(rf"^Upload: {_NUM} Mbps"), ["net.up_mbps"]),
    (re.compile(rf"^Idle latency: {_NUM} ms"), ["net.ping_ms"]),
    (re.compile(rf"^Sequential read: {_NUM} MB/s"), ["disk.read_mbps"]),
    (re.compile(rf"^Sequential write: {_NUM} MB/s at the start, {_NUM} MB/s at the end, {_NUM} MB/s average"),
     ["disk.write_start_mbps", "disk.write_end_mbps", "disk.write_avg_mbps"]),
    (re.compile(rf"^Random 4K read, queue depth 1: {_NUM} IOPS"), ["disk.iops_qd1"]),
    (re.compile(rf"^Random 4K read, queue depth 32: {_NUM} IOPS"), ["disk.iops_qd32"]),
    (re.compile(rf"^{_NUM} packages and apps installed, from {_NUM} source"), ["pkg.total", "pkg.sources"]),
    (re.compile(rf"^Layered on top of the image \(rpm-ostree install\): {_NUM}"), ["pkg.layered"]),
    (re.compile(rf"^Flatpak apps \(system\): {_NUM}"), ["pkg.flatpak_system"]),
    (re.compile(rf"^Flatpak apps \(user\): {_NUM}"), ["pkg.flatpak_user"]),
]
_BENCH = re.compile(r"^BENCH:\s*(.*)$")
_CONFIG = re.compile(r"^Configuration: .*?(\d+)C/(\d+)T, (\d+|unknown) CUs, .*mitigations (\w+), kernel (\S+)")
_KERNEL = re.compile(r"^Kernel: (\S+)$")
_CU_ARRAY = re.compile(r"SE(\d)\.SH(\d) 0x[0-9a-fA-F]+ = (\d+)")
_CUS = re.compile(r"^(?:All )?(\d+) CUs (?:active|are unlocked)|^Active Compute Units: (\d+) of 40")


@dataclass
class RunInfo:
    """What a run's output says about the machine, and the numbers worth comparing between runs."""
    meta: dict[str, str] = field(default_factory=dict)       # kernel, cus, cores, threads, mitigations
    metrics: dict[str, float] = field(default_factory=dict)
    report_path: str | None = None

    def scan(self, raw: str) -> None:
        body = _TS_PREFIX.sub("", raw)
        if m := _REPORT_PATH.search(body):
            self.report_path = m.group(1)
        if m := _BENCH.match(body):
            for kv in m.group(1).split():
                key, _, value = kv.partition("=")
                try:
                    self.metrics[f"bench.{key}"] = float(value)
                except ValueError:
                    pass
            return
        body = _TAG.sub("", body)
        if m := _CONFIG.match(body):
            cores, threads, cus, mit, kernel = m.groups()
            self.meta.update(cores=cores, threads=threads, mitigations=mit, kernel=kernel)
            if cus != "unknown":
                self.meta["cus"] = cus
            return
        if body.startswith("Live WGP masks per shader array:"):
            for se, sh, n in _CU_ARRAY.findall(body):
                self.metrics[f"cu.sa{int(se) * 2 + int(sh)}"] = float(n)
            return
        if m := _KERNEL.match(body):
            self.meta.setdefault("kernel", m.group(1))
        elif m := _CUS.match(body):
            self.meta.setdefault("cus", m.group(1) or m.group(2))
        elif "'mitigations=off' is present" in body:
            self.meta.setdefault("mitigations", "off")
        elif "'mitigations=off' is NOT" in body:
            self.meta.setdefault("mitigations", "on")
        for rx, names in _METRICS:
            if m := rx.match(body):
                for name, value in zip(names, m.groups()):
                    self.metrics[name] = float(value)
                break


@dataclass
class LatestResult:
    status: str
    hints: int
    started: str
    log_path: str | None = None       # GUI log of the run (may start with ~)
    report_path: str | None = None    # the script's report of the run


@dataclass
class RunSummary:
    """One row of the History page: a run with its result counts."""
    id: int
    started: str
    finished: str | None
    scope: str
    source: str
    cancelled: bool
    exit_code: int | None
    kernel: str | None
    cus: int | None
    cores: int | None
    threads: int | None
    mitigations: str | None
    log_path: str | None
    report_path: str | None
    logs_removed: bool
    passed: int = 0
    warnings: int = 0
    failures: int = 0
    info: int = 0
    hints: int = 0

    @property
    def tests(self) -> int:
        return self.passed + self.warnings + self.failures + self.info


class History:
    def __init__(self, path: Path | None = None):
        self.path = path or db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.recovered_from: Path | None = None     # set when a damaged database was moved aside
        try:
            self.db = self._open()
        except sqlite3.DatabaseError as exc:
            self.recovered_from = self._move_aside()
            print(f"Test history: {exc}; moved to {self.recovered_from}, starting a new one.")
            self.db = self._open()
        self.keep_system_details = True     # kernel version and mitigation state; see Settings > Privacy
        self._migrate()

    def _open(self) -> sqlite3.Connection:
        """Open the database; raise DatabaseError when it is damaged or holds objects this app never creates."""
        if self.path.is_symlink():
            raise sqlite3.DatabaseError("the history file is a symbolic link")
        old_umask = os.umask(0o077)
        try:
            db = sqlite3.connect(self.path)
        finally:
            os.umask(old_umask)
        try:
            os.chmod(self.path, 0o600)                  # history is private to this user
            # A changed file must not be able to run code: no functions with side effects from
            # triggers or views, and no triggers or views at all (this app creates neither).
            db.execute("PRAGMA trusted_schema = OFF")
            db.execute("PRAGMA foreign_keys = ON")
            check = db.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise sqlite3.DatabaseError(f"integrity check failed: {check}")
            foreign = db.execute("SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'view')").fetchall()
            if foreign:
                raise sqlite3.DatabaseError("unexpected objects in the database: "
                                            + ", ".join(f"{t} {n}" for t, n in foreign))
        except (sqlite3.DatabaseError, OSError):
            db.close()
            raise
        return db

    def _move_aside(self) -> Path:
        stamp = f"{self.path.name}.damaged-{datetime.now():%Y%m%d-%H%M%S}"
        target, n = self.path.with_name(stamp), 1
        while target.exists() or target.is_symlink():
            n += 1
            target = self.path.with_name(f"{stamp}-{n}")
        for suffix in ("", "-wal", "-shm", "-journal"):
            src = Path(str(self.path) + suffix)
            if src.exists() or src.is_symlink():
                src.rename(Path(str(target) + suffix))
        return target

    def _migrate(self) -> None:
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id          INTEGER PRIMARY KEY,
                started     TEXT NOT NULL,              -- 'YYYY-MM-DD HH:MM:SS', local time
                finished    TEXT,
                scope       TEXT NOT NULL,              -- 'all', a category key, 'test-NN', 'import'
                source      TEXT NOT NULL,              -- 'gui' or 'script' (imported report)
                log_path    TEXT,                       -- the GUI's own log of the run
                report_path TEXT UNIQUE,                -- the script's report in /var/log/bc250-bazzite-test
                exit_code   INTEGER,
                cancelled   INTEGER NOT NULL DEFAULT 0,
                kernel      TEXT, cus INTEGER, cores INTEGER, threads INTEGER, mitigations TEXT,
                logs_removed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS results (
                run_id  INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                test_id TEXT NOT NULL,
                status  TEXT NOT NULL,
                hints   INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (run_id, test_id)
            );
            CREATE TABLE IF NOT EXISTS metrics (
                run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                key    TEXT NOT NULL,
                value  REAL NOT NULL,
                PRIMARY KEY (run_id, key)
            );
            CREATE INDEX IF NOT EXISTS results_test ON results(test_id);
            CREATE INDEX IF NOT EXISTS runs_started ON runs(started);
        """)
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.db.commit()

    # -------------------------------------------------------------- writing
    def start_run(self, scope: str, log_path: Path | None, started: datetime | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO runs (started, scope, source, log_path) VALUES (?, ?, 'gui', ?)",
            ((started or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"), scope, _short(log_path)))
        self.db.commit()
        return int(cur.lastrowid)

    def record_result(self, run_id: int, test_id: str, status: str, hints: int) -> None:
        self.db.execute("INSERT OR REPLACE INTO results (run_id, test_id, status, hints) VALUES (?, ?, ?, ?)",
                        (run_id, test_id, status, hints))
        self.db.commit()

    def finish_run(self, run_id: int, info: RunInfo, exit_code: int | None, cancelled: bool) -> None:
        m = info.meta if self.keep_system_details else {k: v for k, v in info.meta.items()
                                                         if k not in ("kernel", "mitigations")}
        report = _short(info.report_path)
        if report and self.db.execute("SELECT 1 FROM runs WHERE report_path = ? AND id != ?",
                                      (report, run_id)).fetchone():
            report = None
        self.db.execute(
            "UPDATE runs SET finished = ?, exit_code = ?, cancelled = ?, report_path = ?, kernel = ?, cus = ?,"
            " cores = ?, threads = ?, mitigations = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), exit_code, int(cancelled), report,
             m.get("kernel"), _int(m.get("cus")), _int(m.get("cores")), _int(m.get("threads")),
             m.get("mitigations"), run_id))
        self.db.executemany("INSERT OR REPLACE INTO metrics (run_id, key, value) VALUES (?, ?, ?)",
                            [(run_id, k, v) for k, v in info.metrics.items()])
        self.db.commit()

    def delete_run(self, run_id: int) -> None:
        self.db.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        self.db.commit()

    # -------------------------------------------------------------- reading
    def latest_results(self) -> dict[str, LatestResult]:
        """The most recent result of every test, over all runs."""
        rows = self.db.execute("""
            SELECT test_id, status, hints, started, log_path, report_path FROM (
                SELECT r.test_id, r.status, r.hints, runs.started, runs.log_path, runs.report_path,
                       ROW_NUMBER() OVER (PARTITION BY r.test_id ORDER BY runs.started DESC, runs.id DESC) AS n
                FROM results r JOIN runs ON runs.id = r.run_id)
            WHERE n = 1""").fetchall()
        return {row[0]: LatestResult(*row[1:]) for row in rows}

    def latest_config(self, column: str) -> tuple[int, str] | None:
        """Latest known (value, run date) of cus, cores or threads."""
        if column not in ("cus", "cores", "threads"):
            raise ValueError(column)
        row = self.db.execute(f"SELECT {column}, started FROM runs WHERE {column} IS NOT NULL "
                              "ORDER BY started DESC, id DESC LIMIT 1").fetchone()
        return (int(row[0]), row[1]) if row else None

    def latest_metric(self, key: str) -> tuple[float, str] | None:
        """Latest (value, run date) of a metric such as net.down_mbps."""
        row = self.db.execute("SELECT m.value, runs.started FROM metrics m JOIN runs ON runs.id = m.run_id "
                              "WHERE m.key = ? ORDER BY runs.started DESC, runs.id DESC LIMIT 1", (key,)).fetchone()
        return (float(row[0]), row[1]) if row else None

    def runs(self, since: str | None = None, until: str | None = None) -> list[RunSummary]:
        """Runs with at least one result, newest first; since/until are 'YYYY-MM-DD', both inclusive."""
        rows = self.db.execute("""
            SELECT runs.id, started, finished, scope, source, cancelled, exit_code, kernel, cus, cores, threads,
                   mitigations, log_path, report_path, logs_removed,
                   SUM(r.status = 'success'), SUM(r.status = 'warning'), SUM(r.status = 'error'),
                   SUM(r.status = 'info'), SUM(r.hints)
            FROM runs JOIN results r ON r.run_id = runs.id
            WHERE (? IS NULL OR substr(started, 1, 10) >= ?) AND (? IS NULL OR substr(started, 1, 10) <= ?)
            GROUP BY runs.id ORDER BY started DESC, runs.id DESC""", (since, since, until, until)).fetchall()
        return [RunSummary(*row[:5], bool(row[5]), *row[6:14], bool(row[14]), *(int(v or 0) for v in row[15:]))
                for row in rows]

    def run_dates(self) -> tuple[str, str] | None:
        """('YYYY-MM-DD' of the first run, of the last run) of the runs with results, or None."""
        row = self.db.execute("SELECT MIN(substr(started, 1, 10)), MAX(substr(started, 1, 10)) FROM runs "
                              "WHERE id IN (SELECT run_id FROM results)").fetchone()
        return (row[0], row[1]) if row and row[0] else None

    def run_results(self, run_id: int) -> dict[str, tuple[str, int]]:
        """test id -> (status, hints) of one run."""
        return {t: (st, h) for t, st, h in self.db.execute(
            "SELECT test_id, status, hints FROM results WHERE run_id = ?", (run_id,))}

    def latest_run_metrics(self, key: str) -> dict[str, float]:
        """All metrics of the newest run that recorded `key` (empty when none did)."""
        row = self.db.execute("SELECT m.run_id FROM metrics m JOIN runs ON runs.id = m.run_id WHERE m.key = ? "
                              "ORDER BY runs.started DESC, runs.id DESC LIMIT 1", (key,)).fetchone()
        return self.run_metrics(row[0]) if row else {}

    def run_metrics(self, run_id: int) -> dict[str, float]:
        return {k: float(v) for k, v in self.db.execute("SELECT key, value FROM metrics WHERE run_id = ?", (run_id,))}

    def run_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]

    # -------------------------------------------------------------- import
    def import_reports(self, dirs: tuple[Path, ...] | None = None) -> int:
        """Add the script's own reports (command-line runs, and runs from before this database existed).
        Reports already known (by file name, or a GUI run that started within 15 s of them) are skipped."""
        from .runner import parse_report     # runner imports nothing from here; avoids a cycle at load

        known = {Path(p).name for (p,) in self.db.execute(
            "SELECT report_path FROM runs WHERE report_path IS NOT NULL")}
        seen: dict[str, Path] = {}
        for d in dirs or (SCRIPT_LOG_DIR, DESKTOP_DIR):
            try:
                for p in d.glob(REPORT_GLOB):
                    seen.setdefault(p.name, p)
            except OSError:
                continue
        added = 0
        for name, path in sorted(seen.items()):
            if name in known or not (m := _REPORT_TS.search(name)):
                continue
            started = datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")
            near = self.db.execute(
                "SELECT 1 FROM runs WHERE source = 'gui' AND report_path IS NULL"
                " AND abs(strftime('%s', started) - strftime('%s', ?)) <= 15",
                (started.strftime("%Y-%m-%d %H:%M:%S"),)).fetchone()
            if near:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            statuses, hints, info = parse_report(lines)
            if not statuses:
                continue
            info.report_path = str(path)
            cur = self.db.execute(
                "INSERT INTO runs (started, finished, scope, source, report_path) VALUES (?, ?, ?, 'script', ?)",
                (started.strftime("%Y-%m-%d %H:%M:%S"), None, "import", _short(path)))
            run_id = int(cur.lastrowid)
            self.db.executemany("INSERT INTO results (run_id, test_id, status, hints) VALUES (?, ?, ?, ?)",
                                [(run_id, t, s, hints.get(t, 0)) for t, s in statuses.items()])
            self.finish_run(run_id, info, None, False)
            self.db.execute("UPDATE runs SET finished = NULL WHERE id = ?", (run_id,))
            added += 1
        self.db.commit()
        return added

    # -------------------------------------------------------------- cleanup
    def mark_logs_removed(self, removed: set[str]) -> None:
        removed = {_short(p) for p in removed}
        for run_id, log_path, report_path in self.db.execute(
                "SELECT id, log_path, report_path FROM runs WHERE logs_removed = 0").fetchall():
            if (log_path in removed or not log_path) and (report_path in removed or not report_path):
                self.db.execute("UPDATE runs SET logs_removed = 1 WHERE id = ?", (run_id,))
        self.db.commit()

    def scrub_system_details(self) -> None:
        """Forget kernel versions and mitigation states of earlier runs."""
        if self.db.execute("SELECT 1 FROM runs WHERE kernel IS NOT NULL OR mitigations IS NOT NULL").fetchone():
            self.db.execute("UPDATE runs SET kernel = NULL, mitigations = NULL")
            self.db.commit()

    def clear(self) -> None:
        self.db.executescript("DELETE FROM metrics; DELETE FROM results; DELETE FROM runs;")
        self.db.commit()
        self.db.execute("VACUUM")


def _short(path: Path | str | None) -> str | None:
    """Paths are stored with the home folder as ~, so the database does not hold the user name."""
    if not path:
        return None
    text, home = str(path), str(Path.home())
    return "~" + text[len(home):] if home != "/" and (text == home or text.startswith(home + "/")) else text


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None
