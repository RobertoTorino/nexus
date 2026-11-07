# SPDX-License-Identifier: AGPL-3.0-or-later
"""The masks for personal details (privacy.py): the account ID's last 4 characters, an address's last part, the
online ID whole, and free text masked by what the masker knows and by shape."""

from __future__ import annotations

import pytest

from consoles_link import privacy
from consoles_link.privacy import Masker, mask_address, mask_id


@pytest.mark.parametrize("value, masked", [
    ("AQIDBAUGBwg=", "••••••••Bwg="),
    ("4782394583276428394", "•••••••••••••••8394"),
    (" 1234 ", "••••"),
    ("", ""),
])
def test_account_id_keeps_its_last_4(value, masked):
    assert mask_id(value) == masked


@pytest.mark.parametrize("value, masked", [
    ("192.168.1.20", "•••.•••.•••.20"),
    ("10.0.0.254", "•••.•••.•••.254"),
    ("fe80::1c2b:3aff:fe4d:5", "••••:…:5"),
    ("ps5.local", "•••••ocal"),
])
def test_address_keeps_its_last_part(value, masked):
    assert mask_address(value) == masked


def test_masker_hides_what_it_knows():
    masker = Masker()
    assert masker.remember(account="AQIDBAUGBwg=", online_id="player_one", address="fe80::5")
    assert not masker.remember(account="AQIDBAUGBwg=")                     # known already: nothing new
    text = "Account ID of your PSN account (player_one): AQIDBAUGBwg=, at fe80::5."
    assert masker.mask(text) == "Account ID of your PSN account (••••••): ••••••••Bwg=, at ••••:…:5."


def test_masker_hides_by_shape():
    masker = Masker()
    text = ("Asking 192.168.1.21… Registered with 10.0.0.7. Account 4782394583276428394, code AAECAwQFBgc=. "
            "Remote Play 10.0, FFmpeg 7.1.2, 1920×1080, 3047 frames, session ID InvalidSessionId.")
    assert masker.mask(text) == (
        "Asking •••.•••.•••.21… Registered with •••.•••.•••.7. Account •••••••••••••••8394, code ••••••••Bgc=. "
        "Remote Play 10.0, FFmpeg 7.1.2, 1920×1080, 3047 frames, session ID InvalidSessionId.")


def test_name_mask_hides_the_length():
    masker = Masker()
    masker.remember(online_id="a")
    masker.remember(online_id="a_very_long_online_name")
    assert masker.mask("a_very_long_online_name") == privacy.NAME_MASK
