# SPDX-License-Identifier: GPL-3.0-or-later
"""How the app shows things: file sizes and times in the formats chosen in the settings, and the local system."""

from __future__ import annotations

import platform
import sys
from datetime import datetime

from .settings import AppSettings


def local_platform_name() -> str:
    if sys.platform == "win32":
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    try:
        release = platform.freedesktop_os_release()
    except (AttributeError, OSError):
        return platform.system()
    if "bazzite" in release.get("ID", "").lower() or "bazzite" in release.get(
        "NAME", ""
    ).lower():
        return "Bazzite"
    return release.get("PRETTY_NAME", platform.system())



def format_size(size_bytes: int, settings: AppSettings) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 0:
        size_bytes = 0

    fmt = settings.size_format.format
    dec_places = settings.size_format.decimal_places
    use_separator = settings.size_format.thousands_separator

    def format_number(value: float, unit: str = "") -> str:
        """Format a number with optional separator and unit."""
        if use_separator:
            # Format with thousands separator
            if unit:
                return f"{value:,.{dec_places}f} {unit}".rstrip("0").rstrip(".")
            else:
                # For bytes without decimal places
                return f"{int(value):,}"
        else:
            # Format without separator
            if unit:
                return f"{value:.{dec_places}f} {unit}".rstrip("0").rstrip(".")
            else:
                return str(int(value))

    if fmt == "auto":
        # Choose unit automatically based on size (1024-based)
        if size_bytes < 1024:
            return format_number(size_bytes)
        elif size_bytes < 1024 ** 2:
            return format_number(size_bytes / 1024, "KB")
        elif size_bytes < 1024 ** 3:
            return format_number(size_bytes / (1024 ** 2), "MB")
        else:
            return format_number(size_bytes / (1024 ** 3), "GB")
    elif fmt == "binary":
        # 1024-based with IEC units (KiB, MiB, GiB, TiB, PiB)
        size = float(size_bytes)
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024:
                return format_number(size, unit if unit != "B" else "")
            size /= 1024
        return format_number(size, "PiB")
    else:  # decimal
        # 1000-based with SI units (B, KB, MB, GB, TB, PB)
        size = float(size_bytes)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1000:
                return format_number(size, unit if unit != "B" else "")
            size /= 1000
        return format_number(size, "PB")


def format_datetime(timestamp: float, settings: AppSettings) -> str:
    """Format a Unix timestamp according to date/time settings.

    Args:
        timestamp: Unix timestamp (from file's st_mtime)
        settings: AppSettings with date_format and time_format

    Returns:
        Formatted datetime string, or empty string if timestamp is 0
    """
    if timestamp <= 0:
        return ""

    try:
        dt = datetime.fromtimestamp(timestamp)
    except (OSError, ValueError, OverflowError):
        return ""

    # Map format codes to strftime format strings
    date_map = {
        "YYYY-MM-DD": "%Y-%m-%d",
        "MM/DD/YYYY": "%m/%d/%Y",
        "DD/MM/YYYY": "%d/%m/%Y",
    }
    time_map = {
        "HH:MM:SS": "%H:%M:%S",
        "HH:MM": "%H:%M",
    }

    date_format = date_map.get(settings.date_format, "%Y-%m-%d")
    time_format = time_map.get(settings.time_format, "%H:%M:%S")

    try:
        date_part = dt.strftime(date_format)
        time_part = dt.strftime(time_format)
        return f"{date_part} {time_part}"
    except Exception:
        return ""
