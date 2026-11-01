# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds small synthetic BIOS images for the tests: firmware volumes, FFS files and sections (LZMA included), an
AMI NVAR store with StdDefaults, an SMBIOS type 0 table and a setup module with HII strings and IFR forms.

The layout of the setup screens (FORMSET):
  Setup (root)        -> links "Main" (form 2), "Hidden tab" (form 3, under SuppressIf TRUE)
  Main (form 2)       -> subtitle, text "BIOS Vendor", oneof "Mode" (Setup+0), checkbox "Feature" (Setup+1),
                         numeric "Level" (Setup+2, 2 bytes, hex), oneof "Detail" (Setup+4) shown only when Mode
                         is 1, link "Sub" (form 4)
  Hidden tab (form 3) -> oneof "Secret" (Setup+5)
  Sub (form 4)        -> checkbox "Deep" (Setup+6, grayed out when Feature is on)
  Orphan (form 5)     -> oneof "Lost" (Setup+7): no link leads here"""

from __future__ import annotations

import lzma
import struct
import uuid

from bios_reader import firmware

SETUP_GUID = uuid.UUID("ec87d643-eba4-4bb5-a1e5-3f3e36b20da9")
FORMSET = uuid.UUID("7b59104a-c00d-4158-87ff-f04d6396a915")
OTHER_GUID = uuid.UUID("11111111-2222-3333-4444-555555555555")
STRINGS = ["Setup", "Setup help", "Main", "Hidden tab", "Sub", "BIOS Info", "BIOS Vendor", "N/A",
           "Mode", "Pick a mode", "Off", "On", "Feature", "Level", "Detail", "Secret", "Deep", "Orphan", "Lost",
           "Auto"]
S = {text: i + 1 for i, text in enumerate(STRINGS)}         # string ids start at 1
SETUP_SIZE = 8


# --- IFR ----------------------------------------------------------------------------------------------------

def op(code: int, payload: bytes = b"", scope: bool = False) -> bytes:
    return bytes([code, (len(payload) + 2) | (0x80 if scope else 0)]) + payload


END = op(0x29)
TRUE = op(0x46)
NOT = op(0x17)


def eq_id_val(qid: int, value: int) -> bytes:
    return op(0x12, struct.pack("<HH", qid, value))


def _qh(prompt: str, qid: int, offset: int, vid: int = 1, help_text: str = "") -> bytes:
    return struct.pack("<HHHHHB", S[prompt], S.get(help_text, 0), qid, vid, offset, 0)


def oneof(prompt: str, qid: int, offset: int, options: list[tuple[str, int, bool]], help_text: str = "") -> bytes:
    body = op(0x05, _qh(prompt, qid, offset, help_text=help_text) + bytes([0x00, 0, 255, 0]), scope=True)
    for text, value, default in options:
        body += op(0x09, struct.pack("<HBBB", S[text], 0x10 if default else 0, 0, value))
    return body + END


def checkbox(prompt: str, qid: int, offset: int, default: bool) -> bytes:
    return op(0x06, _qh(prompt, qid, offset) + bytes([1 if default else 0]))


def numeric(prompt: str, qid: int, offset: int) -> bytes:
    return op(0x07, _qh(prompt, qid, offset) + bytes([0x21]) + struct.pack("<HHH", 0, 0x1FF, 1), scope=True) + END


def ref(prompt: str, qid: int, form_id: int) -> bytes:
    return op(0x0F, _qh(prompt, qid, 0xFFFF, vid=0) + struct.pack("<H", form_id))


def form(form_id: int, title: str, *items: bytes) -> bytes:
    return op(0x01, struct.pack("<HH", form_id, S[title]), scope=True) + b"".join(items) + END


def form_package() -> bytes:
    body = op(0x0E, FORMSET.bytes_le + struct.pack("<HHB", S["Setup"], S["Setup help"], 0), scope=True)
    body += op(0x24, SETUP_GUID.bytes_le + struct.pack("<HH", 1, SETUP_SIZE) + b"Setup\0")
    body += form(1, "Setup", ref("Main", 100, 2), op(0x0A, scope=True) + TRUE + ref("Hidden tab", 101, 3) + END)
    body += form(2, "Main",
                 op(0x02, struct.pack("<HHB", S["BIOS Info"], 0, 0), scope=True) + END,
                 op(0x03, struct.pack("<HHH", S["BIOS Vendor"], 0, S["N/A"])),
                 oneof("Mode", 1, 0, [("Off", 0, True), ("On", 1, False)], help_text="Pick a mode"),
                 checkbox("Feature", 2, 1, True),
                 numeric("Level", 3, 2),
                 op(0x0A, scope=True) + eq_id_val(1, 1) + NOT + oneof("Detail", 4, 4, [("Auto", 0, True)]) + END,
                 ref("Sub", 102, 4))
    body += form(3, "Hidden tab", oneof("Secret", 5, 5, [("Off", 0, True), ("On", 1, False)]))
    body += form(4, "Sub", op(0x19, scope=True) + eq_id_val(2, 1) + checkbox("Deep", 6, 6, False) + END)
    body += form(5, "Orphan", oneof("Lost", 7, 7, [("Off", 0, True), ("On", 1, False)]))
    body += END
    return (len(body) + 4).to_bytes(3, "little") + bytes([0x02]) + body


def string_package(strings: list[str] = STRINGS) -> bytes:
    lang = b"en-US\0"
    hdr_size = 46 + len(lang)
    blocks = b"".join(b"\x14" + s.encode("utf-16-le") + b"\0\0" for s in strings) + b"\x00"
    body = struct.pack("<II", hdr_size, hdr_size) + bytes(32) + struct.pack("<H", 0) + lang + blocks
    return (len(body) + 4).to_bytes(3, "little") + bytes([0x04]) + body


def setup_module() -> bytes:
    """A stand-in for the Setup PE file: some code bytes around the two packages."""
    return b"MZ" + bytes(62) + string_package() + bytes(16) + form_package() + bytes(32)


# --- Volumes, files, sections -------------------------------------------------------------------------------

def section(kind: int, body: bytes) -> bytes:
    data = (len(body) + 4).to_bytes(3, "little") + bytes([kind]) + body
    return data + b"\0" * (-len(data) % 4)


def ui_section(name: str) -> bytes:
    return section(firmware.SEC_USER_INTERFACE, name.encode("utf-16-le") + b"\0\0")


def lzma_section(inner: bytes) -> bytes:
    packed = lzma.compress(inner, format=lzma.FORMAT_ALONE)
    return section(firmware.SEC_GUID_DEFINED, firmware.LZMA_SECTION.bytes_le + struct.pack("<HH", 24, 1) + packed)


def ffs_file(guid: uuid.UUID, ftype: int, body: bytes) -> bytes:
    size = 24 + len(body)
    return guid.bytes_le + struct.pack("<HBB", 0, ftype, 0) + size.to_bytes(3, "little") + b"\xf8" + body


def volume(files: list[bytes], size: int | None = None) -> bytes:
    body = b""
    for f in files:
        body += b"\xff" * (-len(body) % 8) + f
    length = size or (0x48 + len(body) + 0xFF) // 0x100 * 0x100
    header = (bytes(16) + firmware.FFS2.bytes_le + struct.pack("<Q", length) + b"_FVH" +
              struct.pack("<IHHHBB", 0x4FEFF, 0x48, 0, 0, 0, 2) + struct.pack("<IIII", length // 0x100, 0x100, 0, 0))
    data = header + body
    return data + b"\xff" * (length - len(data))


def smbios_type0(vendor: str, version: str, date: str) -> bytes:
    formatted = bytes([0x00, 0x18]) + b"\0\0" + bytes([1, 2]) + b"\0\xf0" + bytes([3]) + bytes(0x18 - 9)
    return formatted + b"\0".join(s.encode() for s in (vendor, version, date)) + b"\0\0"


# --- NVRAM --------------------------------------------------------------------------------------------------

def nvar(name: str, guid_index: int, data: bytes, nxt: int = 0xFFFFFF, attrs: int = 0x82 | 0x01) -> bytes:
    body = bytes([guid_index]) + name.encode() + b"\0" + data
    return b"NVAR" + struct.pack("<H", 10 + len(body)) + nxt.to_bytes(3, "little") + bytes([attrs]) + body


def nvar_data(data: bytes, nxt: int = 0xFFFFFF) -> bytes:
    return b"NVAR" + struct.pack("<H", 10 + len(data)) + nxt.to_bytes(3, "little") + bytes([0x88]) + data


def store(entries: list[bytes], guids: list[uuid.UUID], size: int = 0x800) -> bytes:
    body = b"".join(entries)
    tail = b"".join(g.bytes_le for g in reversed(guids))                  # index 0 is the last 16 bytes
    return body + b"\xff" * (size - len(body) - len(tail)) + tail


def nvram(setup_old: bytes, setup_now: bytes, setup_default: bytes, amd: bytes = b"") -> bytes:
    """A store where Setup was written twice (a chain of a full entry and a data-only one) plus StdDefaults."""
    defaults = store([nvar("Setup", 0, setup_default, attrs=0x82)], [SETUP_GUID], size=0x100)
    std = nvar("StdDefaults", 1, defaults, attrs=0x82)
    head = nvar("Setup", 0, setup_old)
    head = head[:6] + len(head).to_bytes(3, "little") + head[9:]          # next: the entry right after it
    entries = [std, head, nvar_data(setup_now)]
    guids = [SETUP_GUID, uuid.UUID("4599d26f-1a11-49b8-b91f-858745cff824")]
    if amd:
        entries.append(nvar("AmdSetup", 2, amd))
        guids.append(uuid.UUID("3a997502-647a-4c82-998e-52ef9486a247"))
    return store(entries, guids)


def image(setup_now: bytes = bytes([1, 0, 0x34, 0x12, 0, 0, 0, 0]), version: str = "P9.99",
          module: bytes | None = None) -> bytes:
    """A whole flash image: an NVRAM volume, padding, and an LZMA-packed main volume with the setup module."""
    nv = volume([ffs_file(firmware.NVAR_STORE_FILE, firmware.FILE_RAW,
                          nvram(bytes(SETUP_SIZE), setup_now, bytes([0, 1, 0, 0, 0, 0, 0, 0])))], size=0x1000)
    setup = ffs_file(uuid.uuid4(), 0x07, ui_section("Setup") + section(firmware.SEC_PE32, module or setup_module()))
    smb = ffs_file(uuid.uuid4(), 0x02, section(0x18, uuid.uuid4().bytes_le + smbios_type0("Vendor Inc.", version,
                                                                                            "01/02/2023")))
    inner = volume([setup, smb])
    main = volume([ffs_file(uuid.uuid4(), 0x0B, lzma_section(section(firmware.SEC_FV_IMAGE, inner)))])
    return nv + b"\xff" * 0x1000 + main
