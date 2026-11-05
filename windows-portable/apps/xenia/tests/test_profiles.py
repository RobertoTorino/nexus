# SPDX-License-Identifier: GPL-3.0-or-later
"""Xenia's profiles (profiles.py), as build e6cd2e4 makes and reads them: RC4 against a published test vector, the
Account file against Xenia's EncryptAccountFile steps written out here on their own, the header's fields at their
offsets, the gamertag rules, the profiles found in the content folder (and what is not one), the XUID's range, the
line in [Profiles] that signs one in at start, and a new profile's three files."""

from __future__ import annotations

import hashlib
import hmac
import random
import struct

import pytest

from xenia_manager import profiles


def test_rc4_against_a_published_vector():
    # The Wikipedia test vector: key "Key", plain text "Plaintext".
    assert profiles._rc4(b"Key", b"Plaintext").hex().upper() == "BBF316E8D940AF0AD3"


def test_the_account_file_as_xenia_encrypts_it():
    """EncryptAccountFile (profile_manager.cc): hash = HMAC-SHA1(key 0x19, confounder + account)[:16], then the
    confounder and the account RC4-encrypted with HMAC-SHA1(key 0x19, hash)[:16]."""
    data = profiles.account_bytes("Player One")
    assert len(data) == 0x194
    key = bytes.fromhex("E1BC159C73B1EAE9AB3170F3AD47EBF3")
    info = bytearray(0x17C)
    info[8:8 + 20] = "Player One".encode("utf-16-be")
    plain = b"\xfd" * 8 + bytes(info)
    digest = hmac.new(key, plain, hashlib.sha1).digest()[:16]
    assert data[:16] == digest
    assert data[16:] == profiles._rc4(hmac.new(key, digest, hashlib.sha1).digest()[:16], plain)
    assert profiles.read_account(data) == "Player One"
    assert profiles.read_account(data[:0x100]) is None                       # too short
    assert profiles.read_account(bytes(16) + data[16:]) is None              # the hash does not match
    devkit = profiles.account_bytes("Dev", profiles.KEY_0X19_DEVKIT)
    assert profiles.read_account(devkit) == "Dev"                             # Xenia tries that key second


def test_the_gamertag_is_cut_at_15_characters():
    assert profiles.read_account(profiles.account_bytes("A" * 20)) == "A" * 15


def test_the_header_as_xenia_writes_it():
    header = profiles.header_bytes(0xE03000001A2B3C4D)
    assert len(header) == 0xA000 and header[:4] == b"CON "
    assert struct.unpack_from(">I", header, 0x340)[0] == 0x971A              # header_size
    assert struct.unpack_from(">I", header, 0x344)[0] == 0x00010000          # content_type: a profile
    assert struct.unpack_from(">I", header, 0x348)[0] == 2                   # metadata_version
    assert header[0x360:0x364].hex().upper() == "FFFE07D1"                    # execution_info.title_id
    assert struct.unpack_from(">Q", header, 0x371)[0] == 0xE03000001A2B3C4D  # profile_id
    assert struct.unpack_from(">I", header, 0x39D)[0] == 1                   # data_file_count
    assert sum(1 for b in header if b) <= 4 + 3 + 1 + 1 + 4 + 8 + 1          # nothing else set


@pytest.mark.parametrize("name, ok", [("Player", True), ("Player One", True), ("P1 2", True), ("A" * 15, True),
                                      ("", False), ("A" * 16, False), ("1Player", False), (" Player", False),
                                      ("Player ", False), ("Player  One", False), ("Player_One", False),
                                      ("Spielerä", False)])
def test_the_gamertag_rules(name, ok):
    assert (profiles.gamertag_problem(name) == "") is ok


def test_a_xuid_as_xenia_makes_one():
    for seed in range(20):
        xuid = profiles.new_xuid(random.Random(seed))
        assert 0xE030000000000000 <= xuid <= 0xE03000007FFFFFFF


def test_create_find_and_sign_in(tmp_path):
    home = tmp_path / "emulator"
    home.mkdir()
    (home / "xenia-canary.config.toml").write_text(
        "[Profiles]\nlogged_profile_slot_0_xuid = ''" + " " * 21 + "\t# XUID of the profile to load on boot in slot 0\n"
        "logged_profile_slot_1_xuid = ''\n\n[Storage]\ncontent_root = ''\n", encoding="utf-8")
    assert profiles.find(home) == [] and profiles.signed_in(home) is None
    made = profiles.create(home, " Player One ", random.Random(1))
    assert made.gamertag == "Player One" and made.folder_name == f"{made.xuid:016X}"
    root = home / "content"
    folder = root / made.folder_name / "FFFE07D1" / "00010000" / made.folder_name
    assert profiles.read_account((folder / "Account").read_bytes()) == "Player One"
    header = root / made.folder_name / "FFFE07D1" / "Headers" / "00010000" / f"{made.folder_name}.header"
    assert header.read_bytes() == profiles.header_bytes(made.xuid)
    text = (home / "xenia-canary.config.toml").read_text(encoding="utf-8")
    assert f"logged_profile_slot_0_xuid = '{made.xuid:016X}'" in text
    assert "\t# XUID of the profile to load on boot in slot 0" in text and "logged_profile_slot_1_xuid = ''" in text
    assert profiles.find(home) == [made] and profiles.signed_in(home) == made.xuid
    with pytest.raises(profiles.ProfileError, match="already"):
        profiles.create(home, "player one", random.Random(2))
    with pytest.raises(profiles.ProfileError, match="starts with a letter"):
        profiles.create(home, "1up")


def test_what_is_not_a_profile(tmp_path):
    """FindProfiles: a folder named in 16 capital hex digits, not all zero, with an Account that decrypts."""
    home = tmp_path / "emulator"
    root = home / "content"
    good = profiles.Profile(0xE030000000000001, "Good")
    for xuid, data in ((good.xuid, profiles.account_bytes("Good")), (0, profiles.account_bytes("Zero")),
                       (0xE030000000000002, b"not an account")):
        folder = profiles.profile_folder(root, xuid)
        folder.mkdir(parents=True)
        (folder / "Account").write_bytes(data)
    (root / "e030000000000003").mkdir()                                      # small letters: not Xenia's
    (root / "4D5307E6").mkdir()                                              # a game's title ID
    assert profiles.find(home) == [good]


def test_the_content_folder_and_the_signed_in_xuid_as_xenia_reads_them(tmp_path):
    home = tmp_path / "emulator"
    home.mkdir()
    assert profiles.content_root(home) == home / "content"                   # no settings file yet
    (home / "xenia-canary.config.toml").write_text(
        "[Profiles]\nlogged_profile_slot_0_xuid = \"0xe03000001a2b3c4d\"\n[Storage]\ncontent_root = 'saves'\n",
        encoding="utf-8")
    assert profiles.content_root(home) == home / "saves"
    assert profiles.signed_in(home) == 0xE03000001A2B3C4D                    # from_string<uint64_t>(s, true)
    (home / "xenia-canary.config.toml").write_text("[Profiles]\nlogged_profile_slot_0_xuid = '0000000000000000'\n",
                                                   encoding="utf-8")
    assert profiles.signed_in(home) is None                                  # what Logout writes


def test_a_new_settings_file_has_the_line(tmp_path):
    """Before Xenia's first start there is no settings file: the line goes in a new one, which Xenia fills."""
    home = tmp_path / "emulator"
    made = profiles.create(home, "Player", random.Random(3))
    assert (home / "xenia-canary.config.toml").read_text(encoding="utf-8") == (
        f"[Profiles]\nlogged_profile_slot_0_xuid = '{made.xuid:016X}'\n")
