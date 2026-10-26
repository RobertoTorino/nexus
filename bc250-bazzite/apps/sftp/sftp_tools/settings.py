# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent general application settings: the values and their limits, the file they are kept in, and the
settings the running app uses."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from bc250_core.platform import config_home, data_home

from . import APP_ID

LOG_LEVELS = ("ERROR", "WARNING", "INFO", "DEBUG")
OVERWRITE_MODES = ("ask", "overwrite", "skip")
SIZE_FORMATS = ("auto", "binary", "decimal")
DATE_FORMATS = ("YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY")
TIME_FORMATS = ("HH:MM:SS", "HH:MM")


@dataclass
class SizeFormat:
    """How to display file sizes."""
    format: str = "auto"  # auto, binary (1024), decimal (1000)
    thousands_separator: bool = True
    decimal_places: int = 1


@dataclass
class AppSettings:
    default_local_folder: str = ""
    connection_timeout: int = 10
    log_level: str = "INFO"
    overwrite_mode: str = "ask"
    speed_limit_kbps: int = 0
    keepalive_interval: int = 15
    reconnect_count: int = 2
    reconnect_delay: int = 5
    view_hidden_files: bool = False
    size_format: SizeFormat = field(default_factory=SizeFormat)
    sound_on_transfer_complete: bool = True
    filter_invalid_chars: bool = True
    invalid_char_replacement: str = "_"
    sftp_compression: bool = True
    queue_autoclear: bool = True
    preserve_timestamps: bool = True
    date_format: str = "YYYY-MM-DD"
    time_format: str = "HH:MM:SS"
    logging_max_mb: int = 10

    def validate(self) -> None:
        if not 1 <= self.connection_timeout <= 300:
            raise ValueError("Connection timeout must be between 1 and 300 seconds.")
        if self.overwrite_mode not in OVERWRITE_MODES:
            raise ValueError("Invalid overwrite mode.")
        if not 0 <= self.speed_limit_kbps <= 10_000_000:
            raise ValueError("Speed limit must be between 0 and 10,000,000 KB/s.")
        if not 1 <= self.keepalive_interval <= 300:
            raise ValueError("TCP keep-alive must be between 1 and 300 seconds.")
        if not 0 <= self.reconnect_count <= 10:
            raise ValueError("Reconnect count must be between 0 and 10.")
        if not 1 <= self.reconnect_delay <= 60:
            raise ValueError("Reconnect delay must be between 1 and 60 seconds.")
        if self.log_level not in LOG_LEVELS:
            raise ValueError(f"Log level must be one of: {', '.join(LOG_LEVELS)}.")
        if self.size_format is None:
            self.size_format = SizeFormat()
        if self.size_format.format not in SIZE_FORMATS:
            raise ValueError(f"Size format must be one of: {', '.join(SIZE_FORMATS)}.")
        if not 0 <= self.size_format.decimal_places <= 3:
            raise ValueError("Decimal places must be between 0 and 3.")
        if self.default_local_folder and not os.path.isdir(
            os.path.expanduser(self.default_local_folder)
        ):
            raise ValueError("The default local folder does not exist.")
        if len(self.invalid_char_replacement) != 1:
            raise ValueError("Invalid character replacement must be a single character.")
        if self.invalid_char_replacement in ('/', '\\', '\0', ':'):
            raise ValueError("Invalid character replacement cannot be a path separator or null byte.")
        if self.date_format not in DATE_FORMATS:
            raise ValueError(f"Date format must be one of: {', '.join(DATE_FORMATS)}.")
        if self.time_format not in TIME_FORMATS:
            raise ValueError(f"Time format must be one of: {', '.join(TIME_FORMATS)}.")
        if not 1 <= self.logging_max_mb <= 100:
            raise ValueError("Log file size limit must be between 1 and 100 MB.")



class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppSettings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return AppSettings()
        if not isinstance(data, dict):
            return AppSettings()
        known = {f.name: f.type for f in fields(AppSettings)}
        defaults = AppSettings()
        values = {}
        for key, value in data.items():
            if key not in known:
                continue
            # Handle SizeFormat specially since it's a dataclass
            if key == "size_format":
                if isinstance(value, dict):
                    try:
                        values[key] = SizeFormat(**{k: v for k, v in value.items() if k in ("format", "thousands_separator", "decimal_places")})
                    except Exception:
                        pass
            elif type(value) is type(getattr(defaults, key)):
                values[key] = value
        settings = AppSettings(**values)
        try:
            settings.validate()
        except ValueError:
            # Keep valid fields only when something stored is out of range.
            settings = AppSettings()
        return settings

    def save(self, settings: AppSettings) -> None:
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(asdict(settings), handle, indent=2)
            os.replace(temp_name, self.path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise


def config_dir() -> Path:
    return config_home() / APP_ID


def data_dir() -> Path:
    return data_home() / APP_ID


def log_file() -> Path:
    return data_dir() / f"{APP_ID}.log"


# The settings the running app uses; the settings dialog replaces them through apply_settings().
_store: SettingsStore | None = None
_current = AppSettings()


def current_settings() -> AppSettings:
    return _current


def load_settings(folder: Path | None = None) -> AppSettings:
    global _store, _current
    _store = SettingsStore((folder or config_dir()) / "settings.json")
    _current = _store.load()
    return _current


def apply_settings(new: AppSettings) -> None:
    """Validate and keep *new*, on disk once the settings were loaded; raises ValueError or OSError."""
    global _current
    if _store is None:
        new.validate()
    else:
        _store.save(new)
    _current = new
