# SPDX-License-Identifier: GPL-3.0-or-later
"""Xenia's profiles (owner's roadmap, 04-11-2026: saves need a profile, and Xenia makes one only in its own window):
found, read and created the way builds e6cd2e4 and 838850f do it (src/xenia/kernel/xam/profile_manager.cc,
ProfileManager: FindProfiles, LoadAccount, CreateProfile, UpdateConfig; 838850f moved the HMAC, RC4 and key 0x19
into xboxkrnl_crypt.cc, unchanged), so a game starts with the profile signed in and its saves
go to it.

A profile is a folder in Xenia's content folder (content\\ beside the program, or [Storage] content_root in its
settings), named after its XUID in 16 capital hex digits: X\\FFFE07D1\\00010000\\X\\Account, the account (its gamertag),
encrypted; and its header, X\\FFFE07D1\\Headers\\00010000\\X.header (xcontent_package_directory.cc). Xenia writes the
rest itself when a game first runs (the profile's GPD files, the game's saves under X\\<title ID>\\).

The Account file is 0x194 bytes: a 16-byte hash, then the 8-byte confounder and X_XAMACCOUNTINFO (0x17C bytes,
big-endian, xam.h; only the gamertag set, UTF-16, at most 15 characters), RC4-encrypted with a key that is the
HMAC-SHA1 of the hash; the hash is the HMAC-SHA1 of the plain text. Both HMACs use the console's key 0x19
(crypto_utils.cc; xboxkrnl_crypt.cc in 838850f), which Xenia carries; it tries the development consoles' key too when it reads one. The header is
the XContentContainerHeader Xenia writes for the package (content_manager.cc, ExtractContentHeader; its fields from
xcontent_package.cc, InitializePackageHeader), 0xA000 bytes: Xenia reads a profile without it, but writes it.

Xenia signs a profile in at start from [Profiles] logged_profile_slot_0_xuid in its settings (a string: the XUID in 16
capital hex digits), and then shows no "No Profiles Found" window. Xenia writes its whole settings file when it
starts and when it closes, so the app changes it only while Xenia does not run (the caller's check, as for the
settings)."""

from __future__ import annotations

import hashlib
import hmac
import random
import re
import struct
from dataclasses import dataclass
from pathlib import Path

from . import xenia_settings

KEY_0X19 = bytes.fromhex("E1BC159C73B1EAE9AB3170F3AD47EBF3")             # retail (crypto_utils.cc: xekey_0x19)
KEY_0X19_DEVKIT = bytes.fromhex("DAB69AD98E28764F977EE2487E4F3F68")      # read only, as Xenia tries it second
DASHBOARD = "FFFE07D1"                          # the title ID a profile belongs to (kDashboardID)
PROFILE_TYPE = 0x00010000                       # XContentType::kProfile
ACCOUNT = "Account"
ACCOUNT_INFO = 0x17C                            # sizeof(X_XAMACCOUNTINFO)
CONFOUNDER = b"\xfd" * 8                        # as Xenia writes it ("should be random but meh")
ACCOUNT_SIZE = 0x10 + 8 + ACCOUNT_INFO          # 0x194
GAMERTAG_AT, GAMERTAG_CHARS = 0x08, 15          # char16_t gamertag[0x10]: 15 and the terminator
HEADER_SIZE = 0xA000                            # round_up(sizeof(XContentContainerHeader) = 0x9744, 0x1000)
XUID_DIR = re.compile(r"[0-9A-F]{16}")
GAMERTAG = re.compile(r"[A-Za-z][A-Za-z0-9]*( [A-Za-z0-9]+)*")       # ProfileManager::IsGamertagValid
SECTION, SLOT_0 = "Profiles", "logged_profile_slot_0_xuid"


class ProfileError(Exception):
    pass


@dataclass(frozen=True)
class Profile:
    xuid: int
    gamertag: str

    @property
    def folder_name(self) -> str:
        return f"{self.xuid:016X}"


def content_root(home: Path) -> Path:
    """Xenia's content folder: [Storage] content_root in its settings, relative to its folder; content\\ when empty."""
    value = xenia_settings.toml_value(xenia_settings._lines(home), "Storage", "content_root")
    value = (value or "").strip().strip("'\"")
    return home / value if value else home / "content"


def _rc4(key: bytes, data: bytes) -> bytes:
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + key[i % len(key)]) % 256
        box[i], box[j] = box[j], box[i]
    out, i, j = bytearray(), 0, 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]
        out.append(byte ^ box[(box[i] + box[j]) % 256])
    return bytes(out)


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha1).digest()


def account_bytes(gamertag: str, key: bytes = KEY_0X19) -> bytes:
    """The Account file of a new offline profile (ProfileManager::CreateAccount, then EncryptAccountFile)."""
    info = bytearray(ACCOUNT_INFO)
    name = gamertag[:GAMERTAG_CHARS].encode("utf-16-be")
    info[GAMERTAG_AT:GAMERTAG_AT + len(name)] = name
    plain = CONFOUNDER + bytes(info)
    digest = _hmac(key, plain)[:16]
    return digest + _rc4(_hmac(key, digest)[:16], plain)


def read_account(data: bytes) -> str | None:
    """The gamertag in an Account file, or None when it does not decrypt (DecryptAccountFile: the retail key, then
    the development consoles')."""
    if len(data) < ACCOUNT_SIZE:
        return None
    for key in (KEY_0X19, KEY_0X19_DEVKIT):
        plain = _rc4(_hmac(key, data[:16])[:16], data[16:ACCOUNT_SIZE])
        if hmac.compare_digest(_hmac(key, plain)[:16], data[:16]):
            raw = plain[8 + GAMERTAG_AT:8 + GAMERTAG_AT + 2 * (GAMERTAG_CHARS + 1)]
            return raw.decode("utf-16-be", "replace").split("\x00", 1)[0]
    return None


def header_bytes(xuid: int) -> bytes:
    """The package header Xenia writes for a profile made before a game runs (xcontent.h, big-endian): magic "CON ",
    header_size, content_type, metadata_version 2, the title ID FFFE07D1, profile_id = the XUID, one data file;
    everything else 0, padded to 0xA000."""
    header = bytearray(HEADER_SIZE)
    header[0x000:0x004] = b"CON "
    struct.pack_into(">I", header, 0x340, 0x971A)                       # header_size
    struct.pack_into(">I", header, 0x344, PROFILE_TYPE)                 # content_type
    struct.pack_into(">I", header, 0x348, 2)                            # metadata_version
    header[0x360:0x364] = bytes.fromhex(DASHBOARD)                      # execution_info.title_id
    struct.pack_into(">Q", header, 0x371, xuid)                         # profile_id
    struct.pack_into(">I", header, 0x39D, 1)                            # data_file_count
    return bytes(header)


def profile_folder(root: Path, xuid: int) -> Path:
    name = f"{xuid:016X}"
    return root / name / DASHBOARD / f"{PROFILE_TYPE:08X}" / name


def header_path(root: Path, xuid: int) -> Path:
    name = f"{xuid:016X}"
    return root / name / DASHBOARD / "Headers" / f"{PROFILE_TYPE:08X}" / f"{name}.header"


def find(home: Path) -> list[Profile]:
    """The profiles Xenia loads (FindProfiles, LoadAccount): a folder named after a XUID (not 0) with an Account
    file that decrypts, by gamertag."""
    root = content_root(home)
    found = []
    try:
        folders = sorted(root.iterdir())
    except OSError:
        return []
    for folder in folders:
        if not XUID_DIR.fullmatch(folder.name) or folder.name == "0" * 16:
            continue
        xuid = int(folder.name, 16)
        try:
            gamertag = read_account((profile_folder(root, xuid) / ACCOUNT).read_bytes())
        except OSError:
            continue
        if gamertag is not None:
            found.append(Profile(xuid, gamertag))
    return sorted(found, key=lambda p: p.gamertag.lower())


def signed_in(home: Path) -> int | None:
    """The XUID Xenia signs in at start ([Profiles] logged_profile_slot_0_xuid), or None."""
    value = (xenia_settings.toml_value(xenia_settings._lines(home), SECTION, SLOT_0) or "").strip().strip("'\"")
    value = value.removeprefix("0x").removeprefix("0X")
    try:
        xuid = int(value, 16)
    except ValueError:
        return None
    return xuid or None


def gamertag_problem(gamertag: str) -> str:
    """Why Xenia would refuse *gamertag* (IsGamertagValid), or ""."""
    if not gamertag:
        return "Type a gamertag first."
    if len(gamertag) > GAMERTAG_CHARS:
        return f"A gamertag is at most {GAMERTAG_CHARS} characters."
    if not GAMERTAG.fullmatch(gamertag):
        return ("A gamertag starts with a letter and has letters and digits, with single spaces between words.")
    return ""


def new_xuid(rng: random.Random | None = None) -> int:
    """An offline XUID as Xenia makes one (GenerateXuid): 0xE03 in the top 12 bits, a random 31-bit number below."""
    return (0xE03 << 52) + (rng or random.SystemRandom()).randrange(1 << 31)


def sign_in(home: Path, xuid: int) -> None:
    """[Profiles] logged_profile_slot_0_xuid set to *xuid*, as Xenia's UpdateConfig writes it (a string); the settings
    file made when there is none. OSError is the caller's; the caller makes sure Xenia does not run."""
    lines = xenia_settings._lines(home)
    xenia_settings.toml_set(lines, SECTION, SLOT_0, f"'{xuid:016X}'")
    path = xenia_settings.settings_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def create(home: Path, gamertag: str, rng: random.Random | None = None) -> Profile:
    """A new profile with *gamertag*, signed in at start. ProfileError when the gamertag is refused or a profile has
    it already; OSError is the caller's."""
    gamertag = gamertag.strip()
    problem = gamertag_problem(gamertag)
    if problem:
        raise ProfileError(problem)
    if any(p.gamertag.lower() == gamertag.lower() for p in find(home)):
        raise ProfileError(f"There is a profile called {gamertag} already.")
    root = content_root(home)
    xuid = new_xuid(rng)
    while (root / f"{xuid:016X}").exists():
        xuid = new_xuid(rng)
    folder = profile_folder(root, xuid)
    folder.mkdir(parents=True)
    (folder / ACCOUNT).write_bytes(account_bytes(gamertag))
    header = header_path(root, xuid)
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_bytes(header_bytes(xuid))
    sign_in(home, xuid)
    return Profile(xuid, gamertag)
