# SPDX-License-Identifier: GPL-3.0-or-later
"""Updates outside the suite that an app can install now, for the portal's notice.

Some apps install a program from outside the suite in its newest version rather than a pinned one (the HelixSR
Manager, PCSX2's nightly channel). When such an app checks for that program's newest release, it writes what it
found here, one file per app named after its key in the portal's manifest:

    ~/.local/share/bc250-bazzite-suite/upstream/<key>.json

and the portal lists each update under "Outside the suite", linked to the app's tile. An app writes an empty list
when it found nothing to install, so a done update drops out of the notice. Pinned programs are not written: a newer
one reaches the board with a new version of the app, which the portal announces as an app update.

Standard library only; nothing here asks the network. The apps that are not on bc250_core yet carry a copy of this
file; tools/tests checks that the copies match."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_AGE_S = 30 * 24 * 3600                      # older than this, a file is not trusted any more


def folder() -> Path:
    data = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"      # platform.data_home()
    return Path(data) / "bc250-bazzite-suite" / "upstream"


@dataclass(frozen=True)
class Outside:
    name: str                                   # "HelixSR"
    installed: str                              # "1.8.1"
    latest: str                                 # "1.9.3"
    published: str = ""                         # "2026-10-16"
    url: str = ""                               # its release page
    action: str = ""                            # what to do in the app: "Get HelixSR… on the Setup page updates it."


def publish(key: str, updates: list[Outside], where: Path | None = None, now: float | None = None) -> None:
    """Record what an app's check found: *updates* it can install now, [] when there is none. Never raises: the
    notice is a convenience, the app's own window is what counts."""
    target = (where or folder()) / f"{key}.json"
    data = {"checked": time.time() if now is None else now, "updates": [asdict(u) for u in updates]}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        pass


def read_all(where: Path | None = None, now: float | None = None) -> dict[str, list[Outside]]:
    """The updates every app recorded, by key; files that are broken or older than MAX_AGE_S are left out."""
    now = time.time() if now is None else now
    found: dict[str, list[Outside]] = {}
    base = where or folder()
    if not base.is_dir():
        return found
    fields = set(Outside.__dataclass_fields__)
    for path in sorted(base.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if now - float(data["checked"]) > MAX_AGE_S:
                continue
            updates = [Outside(**{k: str(v) for k, v in item.items() if k in fields}) for item in data["updates"]]
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if updates:
            found[path.stem] = updates
    return found
