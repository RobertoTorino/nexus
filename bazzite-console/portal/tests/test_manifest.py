# SPDX-License-Identifier: GPL-3.0-or-later
"""The portal reads its required app first from apps.toml."""

from __future__ import annotations

import pytest

from bazzite_console_portal import CARDS, ROOT
from bazzite_console_portal.manifest import ManifestError, load, load_cards, parse, parse_cards


def test_required_app_is_first_and_only_required():
    entries = load(ROOT / "apps.toml")
    assert len(entries) == 15
    assert entries[0].key == "bazzite"
    assert entries[0].name == "Bazzite Test"
    assert entries[0].required
    assert [entry.key for entry in entries if entry.required] == ["bazzite"]
    assert entries[0].tag == "ps5-bazzite-v0.1.0"


def test_invalid_tag_and_missing_required_app_are_rejected():
    text = (ROOT / "apps.toml").read_text(encoding="utf-8")
    with pytest.raises(ManifestError, match="tag must be"):
        parse(text.replace("ps5-bazzite-v0.1.0", "bazzite-v0.1.0"))
    with pytest.raises(ManifestError, match="exactly one required"):
        parse(text.replace("required = true", "required = false"))


def test_media_services_are_cards_not_apps():
    cards = load_cards(CARDS)

    assert [(card.key, card.category, card.icon) for card in cards] == [
        ("youtube", "media", "youtube.webp"), ("twitch", "media", "twitch.webp"),
        ("stremio", "media", "stremio.webp"), ("x", "media", "x.webp"),
        ("instagram", "media", "instagram.webp"), ("discord", "media", "discord.webp"),
        ("tiktok", "media", "tiktok.webp"), ("whatsapp", "media", "whatsapp.webp"),
        ("netflix", "media", "netflix.webp"), ("spotify", "media", "spotify.webp")]
    assert cards[0].launch == ("flatpak", "run", "com.brave.Browser", "--kiosk", "https://www.youtube.com/")
    assert cards[1].launch == ("flatpak", "run", "com.brave.Browser", "--kiosk", "https://www.twitch.tv/")
    assert cards[2].flatpak_id == "com.stremio.Stremio"
    assert cards[2].launch == ("flatpak", "run", "com.stremio.Stremio")
    assert [card.launch[-1] for card in cards[3:9]] == [
        "https://x.com/", "https://www.instagram.com/", "https://discord.com/app/",
        "https://www.tiktok.com/", "https://web.whatsapp.com/", "https://www.netflix.com/"]
    assert all(card.flatpak_id == "com.brave.Browser" for card in cards[3:9])
    assert cards[9].flatpak_id == "com.spotify.Client"
    assert cards[9].launch == ("flatpak", "run", "com.spotify.Client")


def test_card_icon_must_be_a_webp_filename():
    with pytest.raises(ManifestError, match="WebP filename"):
        parse_cards('[cards.youtube]\nname = "YouTube"\nsummary = "Open YouTube."\ncategory = "media"\n'
                    'icon = "../youtube.png"\nflatpak_id = "com.brave.Browser"\nflatpak_name = "Brave Browser"\n'
                    'launch = ["flatpak", "run", "com.brave.Browser"]\n')


def test_card_must_launch_its_required_flatpak():
    with pytest.raises(ManifestError, match="required Flatpak"):
        parse_cards('[cards.youtube]\nname = "YouTube"\nsummary = "Open YouTube."\ncategory = "media"\n'
                    'icon = "youtube.webp"\nflatpak_id = "com.brave.Browser"\nflatpak_name = "Brave Browser"\n'
                    'launch = ["flatpak", "run", "com.example.Other"]\n')
