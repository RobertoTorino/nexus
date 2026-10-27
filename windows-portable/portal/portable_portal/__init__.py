# SPDX-License-Identifier: GPL-3.0-or-later
"""The Windows Portable Suite's portal: it installs, updates and starts the apps its manifest (apps.toml) pins.
Windows Portable Test is always installed and listed first. So far this package holds the manifest's parser
(manifest.py), which tools/check_manifest.py checks apps.toml with."""

APP_NAME = "Windows Portable Suite"
APP_ID = "windows-portable-suite"
__version__ = "0.1.1"

__all__ = ["APP_ID", "APP_NAME", "__version__"]
