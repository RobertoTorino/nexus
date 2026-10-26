# SPDX-License-Identifier: GPL-3.0-or-later
"""Personal details hidden in the log."""

from __future__ import annotations

from console_linkb import privacy

JWT = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.c2lnbmF0dXJlLXZhbHVlLWhlcmU"


def test_console_ids_keep_their_last_four():
    assert privacy.mask_id("F4001234ABCD5678") == "••••••••••••5678"
    assert privacy.mask("Waking F4001234ABCD5678") == "Waking ••••••••••••5678"
    assert privacy.mask_id("abc") == "•••"


def test_tokens_and_addresses_are_hidden():
    text = privacy.mask(f"Bearer {JWT} from 192.0.2.45 and 2a02:a453:d9cf:1::66bc.")
    assert JWT not in text and "[token]" in text
    assert "•••.•••.•••.45" in text and "2a02" not in text
    assert text.endswith(".")


def test_named_values_and_ordinary_text():
    assert privacy.mask("Signed in as Player One", names=["Player One"]) == "Signed in as ••••••"
    assert privacy.mask("Living room", ids=["Living"]) == "••ving room"
    for text in ("3 console(s) and 12 cloud game(s), version 0.1.0", "Started at 22:49:04",
                 "Session started (home)", "https://xccs.xboxlive.com/lists/devices"):
        assert privacy.mask(text) == text
