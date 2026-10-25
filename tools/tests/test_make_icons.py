# SPDX-License-Identifier: GPL-3.0-or-later
"""tools/make_icons.py: ICONS.md is what the script writes, and every picture it shows is in the checkout. Neither
needs Qt: only rendering the drawn icons does."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_icons  # noqa: E402

SUITE = Path(__file__).resolve().parent.parent.parent


def test_icons_md_is_up_to_date():
    assert (SUITE / "ICONS.md").read_text(encoding="utf-8") == make_icons.build(), \
        "run python3 tools/make_icons.py"


def test_every_picture_shown_is_in_the_checkout():
    sources = re.findall(r'<img src="([^"]+)"', make_icons.build())
    local = [s for s in sources if not s.startswith("https://")]
    assert local and not [s for s in local if not (SUITE / s).is_file()]


def test_every_category_is_listed():
    text = make_icons.build()
    for category in (p.name for p in (SUITE / "icons").iterdir() if p.is_dir()):
        assert f"icons/{category}/{category}-128.png" in text
