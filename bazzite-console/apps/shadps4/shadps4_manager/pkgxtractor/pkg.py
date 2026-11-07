# SPDX-License-Identifier: GPL-3.0-or-later
"""PKG container parsing and extraction.

Port of ``src/core/file_format/pkg.cpp`` (and the bits of ``pfs.h`` it uses).
The structure of the original is kept on purpose so behavior, edge cases and
error messages match the C++ tool.
"""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Union

from . import crypto
from .pkg_type import get_entry_name_by_type

PathLike = Union[str, os.PathLike]

PKG_MAGIC = b"\x7fCNT"
PKG_HEADER_SIZE = 0x1000
PKG_ENTRY_SIZE = 32
PFSC_MAGIC = b"PFSC"
PFSC_HEADER_SIZE = 48
MIN_PFSC_SIZE = 0x100

PFS_FILE = 2
PFS_DIR = 3
PFS_CURRENT_DIR = 4
PFS_PARENT_DIR = 5

INODE_MODE_DIR = 16384
INODE_MODE_FILE = 32768
INODE_SIZE = 104
INODE_STRIDE = 0xA8
DIRENT_SIZE = 528
DIRENT_NAME_MAX = 512

PFS_BLOCK_SIZE = 0x10000
PFS_SECTOR_SIZE = 0x1000
MAX_SECTOR_READ = 0x20000

CONTENT_FLAG_NAMES: tuple[tuple[int, str], ...] = (
    (0x100000, "FIRST_PATCH"),
    (0x200000, "PATCHGO"),
    (0x400000, "REMASTER"),
    (0x800000, "PS_CLOUD"),
    (0x2000000, "GD_AC"),
    (0x4000000, "NON_GAME"),
    (0x8000000, "UNKNOWN_0x8000000"),
    (0x40000000, "SUBSEQUENT_PATCH"),
    (0x41000000, "DELTA_PATCH"),
    (0x60000000, "CUMULATIVE_PATCH"),
)

_INVALID_NAME_CHARS = set('<>:"/\\|?*')


class PKGError(Exception):
    """Raised for every PKG parsing/extraction failure (the C++ ``failreason``)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_file_name(filename: str) -> str:
    """Replace characters that are invalid in file names; never returns ''."""
    result = []
    for ch in filename:
        if ord(ch) < 0x20 or ch in _INVALID_NAME_CHARS:
            result.append("_")
        else:
            result.append(ch)
    cleaned = "".join(result).rstrip(" .")
    if not cleaned or not filename:
        return "unnamed_file"
    return cleaned


def sanitize_folder_name(folder_name: str) -> str:
    """Same rules as :func:`sanitize_file_name` but with the GUI's fallback name."""
    cleaned = sanitize_file_name(folder_name)
    if cleaned == "unnamed_file":
        return "unknown_title"
    return cleaned


def is_pkg_file(path: PathLike) -> bool:
    """Equivalent of ``Loader::DetectFileType(path) == FileTypes::Pkg``."""
    try:
        with open(path, "rb") as handle:
            return handle.read(4) == PKG_MAGIC
    except OSError:
        return False


def decompress_pfsc(compressed: bytes, out: bytearray) -> bool:
    """Inflate one PFSC sector into ``out`` (a 0x10000-byte buffer).

    PFSC sectors carry a 2-byte zlib prefix followed by a raw DEFLATE stream.
    Like the C++ code, the stream must end cleanly (``Z_STREAM_END``).
    """
    if len(compressed) <= 2:
        return False
    inflater = zlib.decompressobj(-15)
    try:
        data = inflater.decompress(bytes(compressed[2:]), len(out) + 1)
    except zlib.error:
        return False
    if len(data) > len(out) or not inflater.eof:
        return False
    out[:len(data)] = data
    return True


def find_pfsc_offset(image: bytes) -> int:
    """Locate the PFSC header inside a (decrypted) PFS image. Returns -1 if absent."""
    size = len(image)
    if size < MIN_PFSC_SIZE:
        return -1

    # Ultra-fast path: many update PKGs place PFSC at offset 0.
    if image[0:4] == PFSC_MAGIC:
        return 0

    # Fast path: original layout used by many PKGs.
    for i in range(0x20000, size - 3, 0x10000):
        if image[i:i + 4] == PFSC_MAGIC and i + MIN_PFSC_SIZE <= size:
            return i

    # Fallback: some PKGs place PFSC on 0x1000 boundaries instead.
    for i in range(0, size - 3, 0x1000):
        if image[i:i + 4] == PFSC_MAGIC and i + MIN_PFSC_SIZE <= size:
            return i

    # Last resort: byte-granular scan for uncommon layouts.
    pos = image.find(PFSC_MAGIC)
    while pos != -1:
        if pos + MIN_PFSC_SIZE <= size:
            return pos
        pos = image.find(PFSC_MAGIC, pos + 1)
    return -1


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class PKGHeader:
    magic: bytes
    pkg_type: int
    pkg_file_count: int
    pkg_table_entry_count: int
    pkg_sc_entry_count: int
    pkg_table_entry_offset: int
    pkg_sc_entry_data_size: int
    pkg_body_offset: int
    pkg_body_size: int
    pkg_content_offset: int
    pkg_content_size: int
    pkg_content_id: bytes
    pkg_drm_type: int
    pkg_content_type: int
    pkg_content_flags: int
    pkg_promote_size: int
    pkg_version_date: int
    pkg_version_hash: int
    pkg_iro_tag: int
    pkg_drm_type_version: int
    pfs_image_count: int
    pfs_image_flags: int
    pfs_image_offset: int
    pfs_image_size: int
    mount_image_offset: int
    mount_image_size: int
    pkg_size: int
    pfs_signed_size: int
    pfs_cache_size: int
    pfs_image_digest: bytes
    pfs_signed_digest: bytes
    pfs_split_size_nth_0: int
    pfs_split_size_nth_1: int
    pkg_digest: bytes

    @classmethod
    def parse(cls, data: bytes) -> "PKGHeader":
        if len(data) < PKG_HEADER_SIZE:
            raise PKGError("Failed to read PKG header")
        u32 = lambda off: struct.unpack_from(">I", data, off)[0]  # noqa: E731
        u16 = lambda off: struct.unpack_from(">H", data, off)[0]  # noqa: E731
        u64 = lambda off: struct.unpack_from(">Q", data, off)[0]  # noqa: E731
        return cls(
            magic=bytes(data[0:4]),
            pkg_type=u32(0x04),
            pkg_file_count=u32(0x0C),
            pkg_table_entry_count=u32(0x10),
            pkg_sc_entry_count=u16(0x14),
            pkg_table_entry_offset=u32(0x18),
            pkg_sc_entry_data_size=u32(0x1C),
            pkg_body_offset=u64(0x20),
            pkg_body_size=u64(0x28),
            pkg_content_offset=u64(0x30),
            pkg_content_size=u64(0x38),
            pkg_content_id=bytes(data[0x40:0x64]),
            pkg_drm_type=u32(0x70),
            pkg_content_type=u32(0x74),
            pkg_content_flags=u32(0x78),
            pkg_promote_size=u32(0x7C),
            pkg_version_date=u32(0x80),
            pkg_version_hash=u32(0x84),
            pkg_iro_tag=u32(0x98),
            pkg_drm_type_version=u32(0x9C),
            pfs_image_count=u32(0x404),
            pfs_image_flags=u64(0x408),
            pfs_image_offset=u64(0x410),
            pfs_image_size=u64(0x418),
            mount_image_offset=u64(0x420),
            mount_image_size=u64(0x428),
            pkg_size=u64(0x430),
            pfs_signed_size=u32(0x438),
            pfs_cache_size=u32(0x43C),
            pfs_image_digest=bytes(data[0x440:0x460]),
            pfs_signed_digest=bytes(data[0x460:0x480]),
            pfs_split_size_nth_0=u64(0x480),
            pfs_split_size_nth_1=u64(0x488),
            pkg_digest=bytes(data[0xFE0:0x1000]),
        )

    def flag_names(self) -> list[str]:
        return [name for flag, name in CONTENT_FLAG_NAMES if self.pkg_content_flags & flag]


@dataclass
class PKGEntry:
    id: int
    filename_offset: int
    flags1: int
    flags2: int
    offset: int
    size: int
    raw: bytes  # the 32 on-disk bytes; hashed together with DK3 to form IV keys

    @classmethod
    def parse(cls, data: bytes) -> "PKGEntry":
        entry_id, filename_offset, flags1, flags2, offset, size = struct.unpack_from(">IIIIII", data, 0)
        return cls(entry_id, filename_offset, flags1, flags2, offset, size, bytes(data[:PKG_ENTRY_SIZE]))


@dataclass
class PFSCHeader:
    magic: bytes
    block_sz: int
    block_sz2: int
    block_offsets: int
    data_start: int
    data_length: int

    @classmethod
    def parse(cls, data: bytes) -> "PFSCHeader":
        _magic, _unk4, _unk8, block_sz, block_sz2, block_offsets, data_start, data_length = \
            struct.unpack_from("<iiiiqqQq", data, 0)
        return cls(bytes(data[0:4]), block_sz, block_sz2, block_offsets, data_start, data_length)


@dataclass
class Inode:
    mode: int
    nlink: int
    flags: int
    size: int
    size_compressed: int
    uid: int
    gid: int
    blocks: int
    loc: int

    _FORMAT = struct.Struct("<HHIqqqqqqIIIIIIQQII")

    @classmethod
    def parse(cls, data: bytes, offset: int) -> "Inode":
        fields = cls._FORMAT.unpack_from(data, offset)
        return cls(mode=fields[0], nlink=fields[1], flags=fields[2], size=fields[3],
                   size_compressed=fields[4], uid=fields[13], gid=fields[14],
                   blocks=fields[17], loc=fields[18])


@dataclass
class FSEntry:
    """One row of the file table built from the PFS directory entries."""
    name: str
    inode: int
    type: int


def _normalize_dirent_type(dirent_type: int, ino: int, inodes: list[Inode]) -> int:
    if dirent_type in (PFS_FILE, PFS_DIR, PFS_CURRENT_DIR, PFS_PARENT_DIR):
        return dirent_type
    if 0 <= ino < len(inodes):
        mode = inodes[ino].mode
        if mode & INODE_MODE_FILE:
            return PFS_FILE
        if mode & INODE_MODE_DIR:
            return PFS_DIR
    return 0


def _read_exact(handle: BinaryIO, size: int, what: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise PKGError(f"Failed to read {what}")
    return data


def _open_fail_reason(exc: OSError) -> str:
    detail = exc.strerror or str(exc)
    return f"Failed to open PKG file ({detail})" if detail else "Failed to open PKG file"


# ---------------------------------------------------------------------------
# PKG
# ---------------------------------------------------------------------------

class PKG:
    """A package (.pkg) file.

    Typical use::

        pkg = PKG()
        pkg.open(path)                  # header, flags, content id, param.sfo
        pkg.extract(path, out_dir)      # writes sce_sys/ and builds the file table
        for index in range(pkg.num_files):
            ok, reason = pkg.can_extract_file(index)
            if ok:
                pkg.extract_files(index)
        pkg.close()
    """

    def __init__(self) -> None:
        self._file: BinaryIO | None = None
        self.path: Path | None = None
        self.pkg_size = 0
        self.header: PKGHeader | None = None
        self.sfo = b""
        self.pkg_flags = ""
        self.title_id = ""
        self.content_id = ""
        self.warnings: list[str] = []

        self.fs_table: list[FSEntry] = []
        self.inodes: list[Inode] = []
        self.sector_map: list[int] = []
        self.extract_paths: dict[int, Path] = {}
        self.pfsc_offset = 0
        self.extract_path: Path | None = None

        self._dk3 = bytes(32)
        self._iv_key = bytes(32)
        self._img_key = bytes(256)
        self._ekpfs_key = bytes(32)
        self._data_key = bytes(16)
        self._tweak_key = bytes(16)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None

    def __enter__(self) -> "PKG":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best effort
        try:
            self.close()
        except Exception:
            pass

    # -- properties -----------------------------------------------------------

    @property
    def num_files(self) -> int:
        return len(self.fs_table)

    @property
    def is_open(self) -> bool:
        return self._file is not None

    # -- internal helpers ---------------------------------------------------

    def _open_handle(self, path: PathLike) -> BinaryIO:
        self.close()
        try:
            handle = open(path, "rb")
        except OSError as exc:
            raise PKGError(_open_fail_reason(exc)) from exc
        self._file = handle
        self.path = Path(path)
        self.pkg_size = os.fstat(handle.fileno()).st_size
        return handle

    def _read_header(self, handle: BinaryIO) -> PKGHeader:
        handle.seek(0)
        data = handle.read(PKG_HEADER_SIZE)
        if len(data) != PKG_HEADER_SIZE:
            raise PKGError("Failed to read PKG header")
        if data[:4] != PKG_MAGIC:
            raise PKGError("Invalid PKG magic")
        header = PKGHeader.parse(data)
        self.header = header
        self.pkg_flags = ", ".join(header.flag_names())
        self.content_id = data[0x40:0x64].split(b"\x00", 1)[0].decode("ascii", "replace")
        self.title_id = data[0x47:0x50].split(b"\x00", 1)[0].decode("ascii", "replace")
        return header

    @staticmethod
    def _read_entries(handle: BinaryIO, header: PKGHeader) -> list[PKGEntry]:
        handle.seek(header.pkg_table_entry_offset)
        count = header.pkg_table_entry_count
        table = handle.read(count * PKG_ENTRY_SIZE)
        if len(table) != count * PKG_ENTRY_SIZE:
            raise PKGError("Failed to read PKG table entries")
        return [PKGEntry.parse(table[i:i + PKG_ENTRY_SIZE])
                for i in range(0, len(table), PKG_ENTRY_SIZE)]

    # -- public API -----------------------------------------------------------

    def open(self, path: PathLike) -> None:
        """Read header, content ID, flags and ``param.sfo`` (no extraction)."""
        handle = self._open_handle(path)
        header = self._read_header(handle)
        self.sfo = b""
        for entry in self._read_entries(handle, header):
            if get_entry_name_by_type(entry.id) == "param.sfo":
                handle.seek(entry.offset)
                self.sfo = _read_exact(handle, entry.size, "param.sfo")

    def get_entry_data_by_id(self, entry_id: int) -> bytes:
        """Return the raw bytes of a PKG table entry (e.g. ``0x1200`` for icon0.png)."""
        if self.path is None:
            raise PKGError("PKG path not initialized")
        try:
            handle = open(self.path, "rb")
        except OSError as exc:
            raise PKGError(_open_fail_reason(exc)) from exc
        with handle:
            data = handle.read(PKG_HEADER_SIZE)
            if len(data) != PKG_HEADER_SIZE or data[:4] != PKG_MAGIC:
                raise PKGError("Invalid PKG magic")
            header = PKGHeader.parse(data)
            for entry in self._read_entries(handle, header):
                if entry.id == entry_id:
                    handle.seek(entry.offset)
                    return _read_exact(handle, entry.size, "entry data")
        raise PKGError("Entry not found")

    def extract(self, path: PathLike, extract_dir: PathLike) -> None:
        """Write ``sce_sys`` entries, derive the PFS keys and build the file table.

        Raises :class:`PKGError` with the same messages the C++ ``failreason``
        carried. After this call ``num_files`` entries can be extracted with
        :meth:`extract_files`.
        """
        self.extract_path = Path(extract_dir)
        self.fs_table = []
        self.inodes = []
        self.sector_map = []
        self.extract_paths = {}
        self.sfo = b""
        self.warnings = []
        self.pfsc_offset = 0

        handle = self._open_handle(path)
        header = self._read_header(handle)

        if header.pkg_size > self.pkg_size:
            raise PKGError("PKG file size is different")
        if header.pkg_content_size + header.pkg_content_offset > header.pkg_size:
            raise PKGError("Content size is bigger than pkg size")

        self._extract_sce_sys(handle, header)

        # Some small content packages carry only metadata/sce_sys entries and no usable
        # outer PFS payload. In this case, extraction is successful after the table entries.
        has_outer_pfs_region = (header.pfs_image_count != 0 and header.pfs_image_size != 0
                                and header.pfs_image_offset < self.pkg_size)
        if not has_outer_pfs_region:
            return
        if header.pfs_image_offset > (2**64 - 1) - 0x380:
            return
        if header.pfs_image_offset + 0x380 > self.pkg_size:
            return

        # Read the seed and derive the PFS data/tweak keys.
        handle.seek(header.pfs_image_offset + 0x370)
        seed = _read_exact(handle, 16, "PFS seed")
        self._data_key, self._tweak_key = crypto.pfs_gen_crypto_key(self._ekpfs_key, seed)

        pfsc, num_blocks = self._load_pfsc(handle, header)
        self._parse_pfs_metadata(pfsc, num_blocks)

    # -- extraction stages ----------------------------------------------------

    def _extract_sce_sys(self, handle: BinaryIO, header: PKGHeader) -> None:
        assert self.extract_path is not None
        sce_sys = self.extract_path / "sce_sys"
        entries = self._read_entries(handle, header)

        for entry in entries:
            name = get_entry_name_by_type(entry.id)
            target = sce_sys / name if name else sce_sys / str(entry.id)
            target.parent.mkdir(parents=True, exist_ok=True)

            handle.seek(entry.offset)
            data = _read_exact(handle, entry.size, f"PKG entry 0x{entry.id:X}")

            if entry.id == 0x1000 and name == "param.sfo":
                self.sfo = data

            if not name:
                target.write_bytes(data)
                continue

            if entry.id == 0x10:  # ENTRY_KEYS: seed digest, 7 digests, 7 RSA blocks
                if entry.size < 32 + 7 * 32 + 7 * 256:
                    self.warnings.append("entry_keys is too small; DK3 not derived")
                else:
                    key3 = data[32 + 7 * 32 + 3 * 256: 32 + 7 * 32 + 4 * 256]
                    dk3 = crypto.rsa2048_decrypt(key3, is_dk3=True)
                    if dk3 is None:
                        self.warnings.append("DK3 RSA decryption produced invalid padding")
                        dk3 = bytes(32)
                    self._dk3 = dk3
            elif entry.id == 0x20:  # IMAGE_KEY: IV key -> image key -> EKPFS
                if entry.size < 256:
                    self.warnings.append("image_key is too small; EKPFS not derived")
                else:
                    self._iv_key = crypto.ivkey_hash256(entry.raw + self._dk3)
                    self._img_key = crypto.aes_cbc_cfb128_decrypt(self._iv_key, data[:256])
                    ekpfs = crypto.rsa2048_decrypt(self._img_key, is_dk3=False)
                    if ekpfs is None:
                        self.warnings.append("EKPFS RSA decryption produced invalid padding")
                        ekpfs = bytes(32)
                    self._ekpfs_key = ekpfs

            target.write_bytes(data)

            # Decrypt NP data (license.dat, license.info, nptitle.dat, npbind.dat) and overwrite.
            if entry.id in (0x400, 0x401, 0x402, 0x403):
                self._iv_key = crypto.ivkey_hash256(entry.raw + self._dk3)
                decrypted = crypto.aes_cbc_cfb128_decrypt(self._iv_key, data)
                target.write_bytes(decrypted)

    def _load_pfsc(self, handle: BinaryIO, header: PKGHeader) -> tuple[bytes, int]:
        """Find and return the PFSC image region plus its block count."""
        pkg_size = self.pkg_size
        max_pfs_read = pkg_size - header.pfs_image_offset if header.pfs_image_offset < pkg_size else 0
        cache_length = header.pfs_cache_size * 2
        length = min(cache_length, max_pfs_read)
        if length == 0 and header.pfs_image_size != 0:
            length = min(header.pfs_image_size, max_pfs_read)
        # Update PKGs often have PFSC at non-standard locations: load at least 1 MB.
        if 0 < length < 0x100000:
            length = max(length, min(0x100000, max_pfs_read))

        def normalize(requested: int) -> int:
            if requested == 0 or max_pfs_read < PFS_SECTOR_SIZE:
                return 0
            requested = min(requested, max_pfs_read)
            return requested & ~(PFS_SECTOR_SIZE - 1)

        length = normalize(length)
        if length == 0:
            raise PKGError("Failed to find PFSC header")

        state: dict[str, object] = {"pfsc": b"", "offset": -1}

        def load(read_length: int) -> bool:
            read_length = normalize(read_length)
            if read_length == 0:
                return False
            handle.seek(header.pfs_image_offset)
            encrypted = handle.read(read_length)
            if len(encrypted) != read_length:
                return False
            decrypted = crypto.decrypt_pfs(self._data_key, self._tweak_key, encrypted, 0)
            offset = find_pfsc_offset(decrypted)
            source = decrypted
            if offset == -1:
                offset = find_pfsc_offset(encrypted)
                source = encrypted
            if offset == -1 or offset >= read_length:
                state["offset"] = -1
                return False
            state["offset"] = offset
            state["pfsc"] = source[offset:]
            return True

        loaded = load(length)
        if not loaded and max_pfs_read > length:
            retry = min(max_pfs_read, max(length * 4, 0x800000))
            if retry > length:
                loaded = load(retry)
                length = normalize(retry)
        if not loaded and header.pfs_image_size != 0:
            retry = min(max_pfs_read, header.pfs_image_size)
            if retry > length:
                loaded = load(retry)
                length = normalize(retry)
        if not loaded and max_pfs_read > length:
            retry = min(max_pfs_read, 0x400000)
            if retry > length:
                loaded = load(retry)
                length = normalize(retry)
        if not loaded and max_pfs_read > length:
            loaded = load(max_pfs_read)
            length = normalize(max_pfs_read)
        if not loaded:
            raise PKGError("Failed to find PFSC header")

        pfsc: bytes = state["pfsc"]  # type: ignore[assignment]
        self.pfsc_offset = int(state["offset"])  # type: ignore[arg-type]

        if len(pfsc) < PFSC_HEADER_SIZE:
            raise PKGError("PFSC buffer too small")
        pfsc_hdr = PFSCHeader.parse(pfsc)
        if pfsc_hdr.magic != PFSC_MAGIC:
            raise PKGError("Invalid PFSC magic")
        if pfsc_hdr.block_sz2 == 0:
            raise PKGError("Invalid PFSC block size (0)")
        if pfsc_hdr.data_length == 0:
            raise PKGError("Invalid PFSC data length (0)")
        if pfsc_hdr.block_offsets < PFSC_HEADER_SIZE or pfsc_hdr.block_offsets >= len(pfsc):
            raise PKGError(f"PFSC block_offsets out of bounds (offset={pfsc_hdr.block_offsets}, "
                           f"pfsc_size={len(pfsc)})")

        num_blocks = int(pfsc_hdr.data_length / pfsc_hdr.block_sz2)
        if num_blocks <= 0 or num_blocks > 100_000_000:
            raise PKGError(f"Invalid PFSC block count ({num_blocks})")

        sector_map_end = pfsc_hdr.block_offsets + (num_blocks + 1) * 8
        if sector_map_end > len(pfsc):
            # Grow the PFSC read so the whole sector map is available.
            grown = False
            minimum_read = self.pfsc_offset + sector_map_end
            if minimum_read <= max_pfs_read:
                growth_target = max(length * 2, minimum_read + 0x1000)
                retry = min(max_pfs_read, growth_target)
                if retry > length and load(retry):
                    length = normalize(retry)
                    pfsc = state["pfsc"]  # type: ignore[assignment]
                    self.pfsc_offset = int(state["offset"])  # type: ignore[arg-type]
                    grown = sector_map_end <= len(pfsc)
            if not grown:
                raise PKGError(f"PFSC sector map out of bounds (required={sector_map_end}, "
                               f"pfsc_size={len(pfsc)}, tried_len={length})")

        count = num_blocks + 1
        self.sector_map = list(struct.unpack_from(f"<{count}Q", pfsc, pfsc_hdr.block_offsets))
        return pfsc, num_blocks

    def _parse_pfs_metadata(self, pfsc: bytes, num_blocks: int) -> None:
        """Walk the PFSC metadata blocks collecting inodes and directory entries."""
        assert self.extract_path is not None
        extract_path = self.extract_path
        sector_map = self.sector_map
        inodes = self.inodes
        fs_table = self.fs_table
        extract_paths = self.extract_paths

        ent_size = 0
        ndinode = 0
        ndinode_counter = 0
        dinode_reached = False
        uroot_reached = False
        current_dir = extract_path
        decompressed = bytearray(PFS_BLOCK_SIZE)

        for i in range(num_blocks):
            sector_offset = sector_map[i]
            sector_size = sector_map[i + 1] - sector_offset

            if sector_size < 0 or sector_offset >= len(pfsc) or sector_offset + sector_size > len(pfsc):
                raise PKGError(f"Extract: PFSC sector {i} out of bounds (offset={sector_offset}, "
                               f"size={sector_size}, pfsc_size={len(pfsc)})")
            if sector_size == 0:
                raise PKGError(f"Extract: PFSC sector {i} has zero size")
            if sector_size > MAX_SECTOR_READ:
                raise PKGError(f"Extract: PFSC sector {i} size suspiciously large ({sector_size} bytes)")

            compressed = pfsc[sector_offset:sector_offset + sector_size]
            if sector_size == PFS_BLOCK_SIZE:
                decompressed[:] = compressed
            elif sector_size < PFS_BLOCK_SIZE:
                if not decompress_pfsc(compressed, decompressed):
                    raise PKGError(f"Extract: PFSC sector decompression failed at metadata block {i}")
            else:
                decompressed[:] = bytes(PFS_BLOCK_SIZE)

            if i == 0:
                ndinode = struct.unpack_from("<I", decompressed, 0x30)[0]

            occupied_blocks = (ndinode * INODE_STRIDE) // PFS_BLOCK_SIZE
            if (ndinode * INODE_STRIDE) % PFS_BLOCK_SIZE != 0:
                occupied_blocks += 1

            if 1 <= i <= occupied_blocks:
                for p in range(0, PFS_BLOCK_SIZE, INODE_STRIDE):
                    if p + INODE_SIZE > PFS_BLOCK_SIZE:
                        break
                    node = Inode.parse(decompressed, p)
                    if node.mode == 0:
                        break
                    inodes.append(node)

            # Root/uroot entries; sometimes more than 2 (Tomb Raider Remastered).
            if decompressed[0x10:0x1F] == b"flat_path_table":
                uroot_reached = True

            if uroot_reached:
                j = 0
                while j < PFS_BLOCK_SIZE:
                    if j + DIRENT_SIZE > PFS_BLOCK_SIZE:
                        uroot_reached = False
                        break
                    ino, _dtype, _namelen, entsize = struct.unpack_from("<iiii", decompressed, j)
                    if entsize <= 0 or entsize > PFS_BLOCK_SIZE - j:
                        uroot_reached = False
                        break
                    ent_size = entsize
                    if ino != 0:
                        ndinode_counter += 1
                    else:
                        # Always anchor extraction to the caller-provided extraction path.
                        extract_paths[ndinode_counter] = extract_path
                        uroot_reached = False
                        break
                    j += ent_size

            if decompressed[0x10] == 0x2E and decompressed[0x28:0x2A] == b"..":
                dinode_reached = True

            end_reached = False
            if dinode_reached:
                j = 0
                while j < PFS_BLOCK_SIZE:
                    if j + DIRENT_SIZE > PFS_BLOCK_SIZE:
                        break
                    ino, dtype, namelen, entsize = struct.unpack_from("<iiii", decompressed, j)
                    if entsize <= 0 or entsize > PFS_BLOCK_SIZE - j:
                        break
                    if ino == 0:
                        break
                    ent_size = entsize

                    if ino < 0:
                        j += ent_size
                        continue
                    normalized_type = _normalize_dirent_type(dtype, ino, inodes)
                    if normalized_type == 0:
                        j += ent_size
                        continue
                    if namelen < 0 or namelen > DIRENT_NAME_MAX:
                        j += ent_size
                        continue

                    name = bytes(decompressed[j + 16:j + 16 + namelen]).decode("utf-8", "replace")
                    fs_table.append(FSEntry(name=name, inode=ino, type=normalized_type))

                    if normalized_type == PFS_CURRENT_DIR:
                        if ino in extract_paths:
                            current_dir = extract_paths[ino]
                        else:
                            extract_paths[ino] = current_dir or extract_path
                            current_dir = extract_paths[ino]
                    elif normalized_type == PFS_PARENT_DIR:
                        pass
                    else:
                        base_dir = current_dir or extract_path
                        extract_paths[ino] = base_dir / sanitize_file_name(name)

                    if normalized_type in (PFS_FILE, PFS_DIR):
                        if normalized_type == PFS_DIR:
                            extract_paths[ino].mkdir(parents=True, exist_ok=True)
                        ndinode_counter += 1
                        if ndinode_counter + 1 == ndinode:  # 1 for the image itself (root)
                            end_reached = True
                    j += ent_size
            if end_reached:
                break

        file_entries = sum(1 for entry in fs_table if entry.type == PFS_FILE)
        if file_entries == 0:
            # Some PKGs carry valid inode metadata but use non-standard dirent types.
            for inode_index, inode in enumerate(inodes):
                if not (inode.mode & INODE_MODE_FILE) or inode.size <= 0:
                    continue
                if inode_index not in extract_paths:
                    extract_paths[inode_index] = extract_path / f"inode_{inode_index}.bin"
                fs_table.append(FSEntry(name=extract_paths[inode_index].name,
                                        inode=inode_index, type=PFS_FILE))
                file_entries += 1

        if file_entries == 0:
            raise PKGError("No extractable file entries were found in PFSC metadata")

    # -- file table -----------------------------------------------------------

    def export_file_list(self, output_path: PathLike) -> bool:
        """Write ``filelist.txt`` describing every file-table entry."""
        try:
            lines = [
                "PKG File List Export",
                "====================",
                f"Total entries: {len(self.fs_table)}",
                "",
                'Format: [Index] Inode:#### Type:# Name: "filename" -> Path: "full_path"',
                "Types: 2=FILE, 3=DIR, 4=CURRENT_DIR(.), 5=PARENT_DIR(..)",
                "",
            ]
            file_count = dir_count = other_count = 0
            for index, entry in enumerate(self.fs_table):
                line = f'[{index}] Inode:{entry.inode} Type:{entry.type} Name: "{entry.name}"'
                if entry.inode in self.extract_paths:
                    line += f' -> Path: "{self.extract_paths[entry.inode]}"'
                else:
                    line += " -> Path: [NOT SET]"
                lines.append(line)
                if entry.type == PFS_FILE:
                    file_count += 1
                elif entry.type == PFS_DIR:
                    dir_count += 1
                else:
                    other_count += 1
            lines += [
                "",
                "====================",
                "Summary:",
                f"  Files: {file_count}",
                f"  Directories: {dir_count}",
                f"  Other (., ..): {other_count}",
                f"  Total: {len(self.fs_table)}",
                "",
            ]
            Path(output_path).write_text("\n".join(lines), encoding="utf-8")
            return True
        except Exception:
            return False

    def can_extract_file(self, index: int) -> tuple[bool, str]:
        """Pre-flight validation of one file-table entry: ``(ok, reason)``."""
        if index < 0 or index >= len(self.fs_table):
            return False, "fsTable index out of range"
        entry = self.fs_table[index]
        if entry.type != PFS_FILE:
            return True, ""  # directories and ./.. are skipped by extract_files

        inode_number = entry.inode
        if inode_number < 0 or inode_number >= len(self.inodes):
            return False, "inode out of range"
        if inode_number not in self.extract_paths:
            return False, "missing extract path"

        inode = self.inodes[inode_number]
        if not (inode.mode & INODE_MODE_FILE):
            return False, "inode mode is not a file"
        if inode.size < 0:
            return False, "inode size out of bounds"

        sector_loc = inode.loc
        nblocks = inode.blocks
        file_size = inode.size
        if file_size > nblocks * PFS_BLOCK_SIZE:
            return False, "inode size exceeds block capacity"
        if nblocks == 0 and file_size > 0:
            return False, "zero blocks for non-empty file"
        if sector_loc >= len(self.sector_map):
            return False, "inode sector location out of bounds"
        if nblocks + 1 > len(self.sector_map) - sector_loc:
            return False, "inode sector range out of bounds"

        assert self.header is not None
        pfs_image_offset = self.header.pfs_image_offset
        for block in range(nblocks):
            current = sector_loc + block
            if current + 1 >= len(self.sector_map):
                return False, "sector map index out of range"
            sector_offset = self.sector_map[current]
            next_offset = self.sector_map[current + 1]
            if next_offset <= sector_offset:
                return False, "non-monotonic sector offsets"
            sector_size = next_offset - sector_offset
            if sector_size == 0 or sector_size > PFS_BLOCK_SIZE:
                return False, "invalid sector size"
            file_offset = pfs_image_offset + self.pfsc_offset + sector_offset
            previous_data = (sector_offset + self.pfsc_offset) & 0xFFF
            if file_offset < previous_data:
                return False, "invalid sector seek underflow"
            required_buf = (previous_data + sector_size + 0xFFF) & ~0xFFF
            read_start = file_offset - previous_data
            if required_buf == 0 or read_start > self.pkg_size or required_buf > self.pkg_size - read_start:
                return False, "sector read out of pkg bounds"

        filename = self.extract_paths[inode_number].name
        if not filename or filename in (".", ".."):
            return False, "invalid output filename"
        return True, ""

    def extract_files(self, index: int) -> None:
        """Decrypt, inflate and write one file-table entry. Non-file entries are skipped."""
        if index < 0 or index >= len(self.fs_table):
            raise IndexError(f"ExtractFiles: fsTable index out of range: {index}")

        entry = self.fs_table[index]
        if entry.type != PFS_FILE:
            return

        inode_number = entry.inode
        inode_name = entry.name
        if inode_number < 0 or inode_number >= len(self.inodes):
            raise PKGError(f"ExtractFiles: inode out of range for entry index {index}, inode {inode_number}")
        if inode_number not in self.extract_paths:
            raise PKGError(f"ExtractFiles: missing extract path for inode {inode_number} "
                           f"(name: '{inode_name}', type: {entry.type})")

        inode = self.inodes[inode_number]
        if not (inode.mode & INODE_MODE_FILE):
            raise PKGError(f"ExtractFiles: inode mode is not a file for inode {inode_number}")
        if inode.size < 0:
            raise PKGError(f"ExtractFiles: invalid inode size for inode {inode_number}")

        sector_loc = inode.loc
        nblocks = inode.blocks
        file_size = inode.size
        if file_size > nblocks * PFS_BLOCK_SIZE:
            raise PKGError(f"ExtractFiles: inode size exceeds block capacity for inode {inode_number}")
        if nblocks == 0 and file_size > 0:
            raise PKGError(f"ExtractFiles: zero blocks for non-empty file inode {inode_number}")
        if sector_loc >= len(self.sector_map):
            raise PKGError(f"ExtractFiles: inode sector location out of bounds for inode {inode_number}")
        if nblocks + 1 > len(self.sector_map) - sector_loc:
            raise PKGError(f"ExtractFiles: inode sector range out of bounds for inode {inode_number}")

        assert self.extract_path is not None and self.header is not None
        output_path = self.extract_paths.get(inode_number) or (self.extract_path / sanitize_file_name(inode_name))
        self.extract_paths[inode_number] = output_path

        filename = output_path.name
        if not filename or filename in (".", ".."):
            raise PKGError(f"ExtractFiles: invalid file path (no filename) for inode {inode_number} "
                           f"(name: '{inode_name}', type: {entry.type}) path: {output_path}")

        parent_dir = output_path.parent
        try:
            parent_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PKGError(f"ExtractFiles: failed to create parent directory: {exc} (inode {inode_number})") from exc

        if self._file is None:
            raise PKGError("ExtractFiles: PKG file handle not open - extract() must be called first")
        pkg_file = self._file
        pfs_image_offset = self.header.pfs_image_offset
        pfsc_offset = self.pfsc_offset
        sector_map = self.sector_map

        try:
            out = open(output_path, "wb")
        except OSError as exc:
            raise PKGError(f"ExtractFiles: failed to open output file for inode {inode_number} "
                           f"(name: '{inode_name}', filename: '{filename}') at path: {output_path}: {exc}") from exc

        with out:
            size_decompressed = 0
            decompressed = bytearray(PFS_BLOCK_SIZE)

            for j in range(nblocks):
                if sector_loc + j + 1 >= len(sector_map):
                    raise PKGError(f"ExtractFiles: sector map out of range at file index {index}, block {j}")

                sector_offset = sector_map[sector_loc + j]
                sector_size = sector_map[sector_loc + j + 1] - sector_offset
                file_offset = pfs_image_offset + pfsc_offset + sector_offset
                current_sector = (pfsc_offset + sector_offset) // PFS_SECTOR_SIZE

                if sector_size <= 0:
                    raise PKGError(f"ExtractFiles: zero-sized sector at file index {index}, block {j}")
                if sector_size > PFS_BLOCK_SIZE:
                    raise PKGError(f"ExtractFiles: sector too large at file index {index}, block {j}, "
                                   f"size {sector_size}")

                previous_data = (sector_offset + pfsc_offset) & 0xFFF
                required_buf = (previous_data + sector_size + 0xFFF) & ~0xFFF
                if required_buf == 0:
                    raise PKGError(f"ExtractFiles: invalid zero aligned PFSC read size at file index {index}, block {j}")
                if required_buf > MAX_SECTOR_READ:
                    raise PKGError(f"ExtractFiles: suspicious PFSC read size at file index {index}, block {j}, "
                                   f"size {required_buf}")
                if file_offset < previous_data:
                    raise PKGError(f"ExtractFiles: invalid PFSC seek underflow at file index {index}, block {j}")
                read_start = file_offset - previous_data
                if read_start + required_buf > self.pkg_size:
                    raise PKGError(f"ExtractFiles: PFSC read out of PKG bounds at file index {index}, block {j} "
                                   f"(read_start={read_start}, required={required_buf}, pkgSize={self.pkg_size})")

                pkg_file.seek(read_start)
                encrypted = pkg_file.read(required_buf)
                if len(encrypted) != required_buf:
                    raise PKGError(f"ExtractFiles: short read from PKG at file index {index}, block {j}")

                plain = crypto.decrypt_pfs(self._data_key, self._tweak_key, encrypted, current_sector)
                compressed = plain[previous_data:previous_data + sector_size]

                if sector_size == PFS_BLOCK_SIZE:
                    decompressed[:] = compressed
                elif not decompress_pfsc(compressed, decompressed):
                    raise PKGError(f"ExtractFiles: PFSC sector decompression failed at file index {index}, block {j}")

                size_decompressed += PFS_BLOCK_SIZE
                if j < nblocks - 1:
                    out.write(decompressed)
                else:
                    # Trim the zero padding at the end of the file.
                    write_size = file_size - (size_decompressed - PFS_BLOCK_SIZE)
                    write_size = max(0, min(write_size, PFS_BLOCK_SIZE))
                    out.write(decompressed[:write_size])
