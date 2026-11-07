# SPDX-License-Identifier: GPL-3.0-or-later
"""PS2 memory cards in PCSX2's memcards folder, read and changed through mymc++'s card code (mymc/): the saves on a
card, import, export, delete, copy to another card, a new card, format and check.

A card is never changed in place: the change is made on a copy beside it, which then takes the card's place in one
step (os.replace), so a failure leaves the card as it was. Before every change the card is copied beside it as
<card>.<date>.bak; PCSX2 lists only .ps2, .mc2, .bin, .mcd and .mcr files, so it does not offer a backup as a card.
Nothing is written while PCSX2 runs: it keeps the card in memory and would write its own copy over the change.

PCSX2 lists folder memory cards and PS1 cards (.mcd, .mcr) too; mymc++ reads neither, so they are listed with that
reason. A PS1 save on a PS2 card (PCSX2's PS1 games do not make those, a PS2 that copies one does) is listed with
its title like a PS2 save."""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import struct
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import userdata
from .mymc import ps2iconsys, ps2mc
from .mymc.ps2icon import Icon
from .mymc.ps2mc_dir import DF_EXISTS, DF_POCKETSTN, DF_PSX, PS2MC_DIRENT_LENGTH, mode_is_dir, tod_to_time
from .mymc.round import round_up
from .mymc.save import format_ems, format_max_drive, ps2save

PS2_SUFFIXES = (".ps2", ".mc2", ".bin")         # PS2 card images: .ps2 with ECC (PCSX2's own), the others without
PS1_SUFFIXES = (".mcd", ".mcr")                 # PS1 cards, which PCSX2 lists too
IMPORT_SUFFIXES = (".max", ".psu", ".sps", ".xps", ".cbs", ".psv")
EXPORT_KINDS = {".psu": "EMS (.psu)", ".max": "MAX Drive (.max)"}
SIZES_MB = (8, 16, 32, 64)                      # the sizes PCSX2 makes; 8 MB is the PS2's own card
PAGE, PAGE_WITH_ECC = 512, 528                  # bytes per page in the image, without and with its ECC
BACKUP_SUFFIX = ".bak"
BACKUPS_KEPT = 10                               # per card; the oldest goes when an eleventh is made
CHECK_PAGES_LIMIT = 1 << 17                     # the ECC of every page is read up to a 64 MB card


class CardError(Exception):
    """A card that cannot be read or changed, with the reason in words for the window."""


@dataclass(frozen=True)
class Save:
    name: str                   # the save's folder on the card, e.g. BESLES-12345SAVE
    title: str                  # the title the PS2's browser shows (both lines), or "" when there is none
    size: int                   # bytes on the card, folder and files
    modified: float             # seconds since the epoch, 0 when the card has none
    ps1: bool = False           # a PS1 save on the PS2 card (PocketStation saves are PS1 saves too)

    @property
    def label(self) -> str:
        return self.title or self.name


@dataclass
class Card:
    path: Path
    saves: list[Save] = field(default_factory=list)
    free: int = 0               # bytes
    total: int = 0              # bytes the saves can use
    ecc: bool = True
    error: str = ""             # why it cannot be read here ("" for a PS2 card that was read)

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def readable(self) -> bool:
        return not self.error


# --- Where the cards are --------------------------------------------------------------------------------------

def card_folder(pcsx2_home: Path) -> Path:
    """PCSX2's memcards folder: [Folders] MemoryCards in PCSX2.ini (relative to PCSX2's folder), memcards when
    it is not set."""
    folder = userdata.ini_value(pcsx2_home, "Folders", "MemoryCards") or "memcards"
    path = Path(os.path.expanduser(folder))
    return path if path.is_absolute() else pcsx2_home / path


def slot_cards(pcsx2_home: Path) -> dict[str, int]:
    """The card file in each of PCSX2's two slots, {file name: slot}; PCSX2's own names when it has none set."""
    slots: dict[str, int] = {}
    for slot in (1, 2):
        if userdata.ini_value(pcsx2_home, "MemoryCards", f"Slot{slot}_Enable").lower() == "false":
            continue
        name = userdata.ini_value(pcsx2_home, "MemoryCards", f"Slot{slot}_Filename") or f"Mcd{slot:03d}.ps2"
        slots.setdefault(name, slot)
    return slots


def find_cards(folder: Path) -> list[Card]:
    """Every card PCSX2 would list in *folder* (files and folders by the names it lists), sorted by name; the PS2
    card images read, the others with the reason they are not."""
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    cards = []
    for path in entries:
        suffix = path.suffix                         # PCSX2 compares the endings as they are written
        if suffix not in PS2_SUFFIXES + PS1_SUFFIXES:
            continue
        if path.is_dir():
            if (path / "_pcsx2_superblock").is_file():
                cards.append(Card(path, error="A folder memory card: this window reads card files only."))
        elif suffix in PS1_SUFFIXES:
            cards.append(Card(path, error="A PS1 memory card: this window reads PS2 cards only."))
        else:
            cards.append(read_card(path))
    return cards


# --- Reading ---------------------------------------------------------------------------------------------------

@contextlib.contextmanager
def open_card(path: Path, mode: str = "rb") -> Iterator[ps2mc.ps2mc]:
    """mymc++'s card on *path*; its own errors become CardError."""
    try:
        f = open(path, mode)
    except OSError as error:
        raise CardError(f"{path.name} could not be opened: {error.strerror or error}") from error
    mc = None
    try:
        try:
            mc = ps2mc.ps2mc(f)
        except ps2mc.error as error:
            raise CardError(_reason(path, error)) from error
        yield mc
    finally:
        if mc is not None:
            mc.close()
        f.close()


def _reason(path: Path, error: Exception) -> str:
    """mymc++'s error in words, without the file it names (the copy a change is made on, at times)."""
    text = getattr(error, "strerror", None) or str(error)
    if isinstance(error, ps2mc.corrupt) and "Not a PS2" in text:
        return f"{path.name} is not a formatted PS2 memory card."
    return f"{path.name}: {text}"


def read_card(path: Path) -> Card:
    try:
        with open_card(path) as mc:
            saves = _saves(mc)
            return Card(path, saves, mc.get_free_space(), mc.get_allocatable_space(), mc.spare_size > 0)
    except CardError as error:
        return Card(path, error=str(error))
    except (OSError, ps2mc.error, ValueError, struct.error) as error:
        return Card(path, error=f"{path.name} could not be read: {error}")


def _saves(mc: ps2mc.ps2mc) -> list[Save]:
    root = mc.dir_open("/")
    try:
        entries = [ent for ent in list(root)[2:] if (ent[0] & DF_EXISTS) and mode_is_dir(ent[0])]
    finally:
        root.close()
    saves = []
    for ent in entries:
        name = ent[8].decode("latin-1")
        ps1 = bool(ent[0] & (DF_PSX | DF_POCKETSTN))
        title = _ps1_title(mc, name) if ps1 else _ps2_title(mc, name)
        saves.append(Save(name, title, mc.dir_size("/" + name), tod_to_time(ent[6]), ps1))
    return sorted(saves, key=lambda s: (s.label.casefold(), s.name))


def _ps2_title(mc: ps2mc.ps2mc, name: str) -> str:
    data = mc.get_icon_sys("/" + name)
    if data is None:
        return ""
    try:
        lines = ps2iconsys.IconSys(data).get_title("unicode")
    except ps2iconsys.Error:
        return ""
    return " ".join(" ".join(lines).split())


def _ps1_title(mc: ps2mc.ps2mc, name: str) -> str:
    """A PS1 save's title from its header: "SC", the icon's frames, its blocks and 64 bytes of Shift-JIS. The file
    has the folder's name."""
    try:
        f = mc.open(f"/{name}/{name}", "rb")
    except (ps2mc.error, OSError):
        return ""
    try:
        head = f.read(128)
    finally:
        f.close()
    if len(head) != 128 or head[:2] != b"SC":
        return ""
    title = head[4:68].split(b"\0", 1)[0]
    return " ".join(ps2iconsys.shift_jis_conv(title, "unicode").split())


def save_icon(path: Path, name: str) -> tuple[ps2iconsys.IconSys, Icon] | None:
    """The save's icon.sys and its 3D icon (the one the browser shows), for the picture; None when it has none or
    either cannot be read."""
    try:
        with open_card(path) as mc:
            data = mc.get_icon_sys("/" + name)
            if data is None:
                return None
            icon_sys = ps2iconsys.IconSys(data)
            f = mc.open(f"/{name}/{icon_sys.icon_file_normal}", "rb")
            try:
                with contextlib.redirect_stdout(io.StringIO()):     # its warnings about the size go nowhere
                    icon = Icon(f.read())
            finally:
                f.close()
            return icon_sys, icon
    except (CardError, ps2mc.error, ps2iconsys.Error, OSError, ValueError, struct.error, IndexError, TypeError):
        return None


# --- PCSX2 and the backups ------------------------------------------------------------------------------------

def pcsx2_running(proc: Path = Path("/proc")) -> bool:
    """Whether PCSX2 runs (its process is pcsx2-qt, the AppImage's and the Flatpak's alike); a zombie does not
    count, as in core's steam_running."""
    for folder in proc.glob("[0-9]*"):
        try:
            if not (folder / "comm").read_text().strip().lower().startswith("pcsx2"):
                continue
            state = (folder / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            continue
        if state not in ("Z", "X"):
            return True
    return False


def backups(card: Path) -> list[Path]:
    """The card's backups, oldest first: by their date, then by the -2, -3 of those made within one second."""
    def order(path: Path) -> tuple[str, int]:
        parts = path.name[len(card.name) + 1:-len(BACKUP_SUFFIX)].split("-")      # date, time[, n]
        n = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        return "-".join(parts[:2]), n
    return sorted(card.parent.glob(f"{card.name}.*{BACKUP_SUFFIX}"), key=order)


def backup(card: Path, now: Callable[[], datetime] = datetime.now) -> Path:
    """A copy of *card* beside it, <card>.<date>.bak; only the newest BACKUPS_KEPT stay."""
    stamp = now().strftime("%Y%m%d-%H%M%S")
    target = card.with_name(f"{card.name}.{stamp}{BACKUP_SUFFIX}")
    n = 2
    while target.exists():                              # two changes within a second
        target = card.with_name(f"{card.name}.{stamp}-{n}{BACKUP_SUFFIX}")
        n += 1
    shutil.copy2(card, target)
    for old in backups(card)[:-BACKUPS_KEPT]:
        old.unlink(missing_ok=True)
    return target


def _replace(card: Path, write: Callable[[Path], None]) -> None:
    """*write* makes the new card on a copy beside *card*, which then takes its place."""
    temp = card.with_name(f".{card.name}.new")
    try:
        write(temp)
        with open(temp, "rb+") as f:
            os.fsync(f.fileno())
        os.replace(temp, card)
    finally:
        temp.unlink(missing_ok=True)


def _change(card: Path, change: Callable[[ps2mc.ps2mc], None]) -> Path:
    """*change* on a copy of the card, after its backup; returns the backup."""
    if pcsx2_running():
        raise CardError("PCSX2 is running: close it first, it would write its own copy of the card over the change.")
    saved = backup(card)

    def write(temp: Path) -> None:
        shutil.copyfile(card, temp)
        with open_card(temp, "r+b") as mc:
            try:
                change(mc)
                mc.flush()
            except ps2mc.error as error:            # mymc++'s own (OSErrors too): in words, the card unchanged
                raise CardError(_reason(card, error)) from error
    try:
        _replace(card, write)
    except BaseException as error:
        saved.unlink(missing_ok=True)                   # the card is as it was: no backup of it needed
        if isinstance(error, OSError):
            raise CardError(f"{card.name} could not be changed: {error.strerror or error}") from error
        raise
    return saved


# --- Changes --------------------------------------------------------------------------------------------------

def _load(file: Path) -> ps2save.PS2SaveFile:
    """A save file in any of the formats mymc++ imports, recognized by its contents."""
    save = ps2save.PS2SaveFile()
    try:
        with open(file, "rb") as f:
            kind = ps2save.poll_format(f)
            if kind is None:
                raise CardError(f"{file.name} is not a save file this window knows (.max, .psu, .sps, .xps, "
                                ".cbs or .psv).")
            f.seek(0)
            kind.load(save, f)
        for i in range(len(save)):                      # a MAX Drive save unpacks here, not on the card
            save.get_file(i)
    except OSError as error:
        raise CardError(f"{file.name} could not be read: {error.strerror or error}") from error
    except (ps2save.Error, ps2mc.error, ValueError, struct.error, EOFError) as error:
        raise CardError(f"{file.name} could not be read: {error}") from error
    return save


def _needed(save: ps2save.PS2SaveFile, cluster: int) -> int:
    """The bytes a save takes on a card: its folder (its entries) and each file, in whole clusters."""
    files = [save.get_file(i) for i in range(len(save))]
    size = round_up((len(files) + 2) * PS2MC_DIRENT_LENGTH, cluster)
    return size + sum(round_up(len(data), cluster) for _, data in files)


def _root_growth(mc: ps2mc.ps2mc, new: int) -> int:
    """The bytes the card's root folder grows by for *new* saves: a deleted save's entry is used again first, then
    the folder takes another cluster for every two entries."""
    root = mc.dir_open("/")
    try:
        entries = list(root)
    finally:
        root.close()
    unused = sum(1 for ent in entries[2:] if not ent[0] & DF_EXISTS)
    grown = len(entries) + max(new - unused, 0)
    return (round_up(grown * PS2MC_DIRENT_LENGTH, mc.cluster_size)
            - round_up(len(entries) * PS2MC_DIRENT_LENGTH, mc.cluster_size))


def _name_of(save: ps2save.PS2SaveFile) -> str:
    return save.get_directory()[8].decode("latin-1")


def _import(mc: ps2mc.ps2mc, saves: list[ps2save.PS2SaveFile]) -> tuple[list[str], list[str]]:
    """(the folders written, the folders already on the card and left alone). The space is counted first, so a
    card that is too full gets none of them."""
    on_card = {s.name for s in _saves(mc)}
    new = [s for s in saves if _name_of(s) not in on_card]
    needed = sum(_needed(s, mc.cluster_size) for s in new) + _root_growth(mc, len(new))
    free = mc.get_free_space()
    if needed > free:
        raise CardError(f"Not enough space on the card: {kib(needed)} needed, {kib(free)} free.")
    for save in new:
        mc.import_save_file(save, False)
    return [_name_of(s) for s in new], sorted(_name_of(s) for s in saves if _name_of(s) in on_card)


def import_saves(card: Path, files: Iterable[Path]) -> str:
    """The save files onto the card; a save whose folder is already there is left out (delete it first to
    replace it). Returns what happened, in words."""
    return _write_saves(card, [_load(Path(f)) for f in files])


def _write_saves(card: Path, saves: list[ps2save.PS2SaveFile]) -> str:
    """The saves onto the card; when all are there already, the card is not touched (and no backup made)."""
    with open_card(card) as mc:
        on_card = {s.name for s in _saves(mc)}
    if all(_name_of(s) in on_card for s in saves):
        return _summary(card.name, [], sorted(_name_of(s) for s in saves))
    result: list[tuple[list[str], list[str]]] = []
    _change(card, lambda mc: result.append(_import(mc, saves)))
    written, skipped = result[0]
    return _summary(card.name, written, skipped)


def copy_saves(source: Path, names: Iterable[str], target: Path) -> str:
    """The saves *names* from one card onto another; the source card is only read."""
    if source.resolve() == target.resolve():
        raise CardError("Choose another card to copy to.")
    with open_card(source) as mc:
        try:
            saves = [mc.export_save_file("/" + name) for name in names]
        except (ps2mc.error, AssertionError) as error:      # export asserts that a file reads to its length
            raise CardError(_reason(source, error)) from error
    return _write_saves(target, saves)


def _summary(card: str, written: list[str], skipped: list[str]) -> str:
    text = f"{len(written)} save(s) written to {card}."
    if skipped:
        text += (f" Already on the card, left as they are: {', '.join(skipped)} (delete one first to replace "
                 "it).")
    return text


def delete_saves(card: Path, names: Iterable[str]) -> str:
    names = list(names)

    def delete(mc: ps2mc.ps2mc) -> None:
        for name in names:
            mc.rmdir("/" + name)
    _change(card, delete)
    return f"{len(names)} save(s) deleted from {card.name}."


def export_name(card: Path, name: str, suffix: str) -> str:
    """mymc++'s long file name for an export: the folder, the title and a checksum, e.g.
    SCES-50501 Rez (DD5DAEA3).psu."""
    with open_card(card) as mc:
        save = mc.export_save_file("/" + name)
    return ps2save.make_longname(name, save) + suffix


def export_save(card: Path, name: str, target: Path) -> Path:
    """The save as a file in the format its suffix names (.psu or .max); an existing file is replaced (the file
    dialog asked)."""
    writer = {".psu": format_ems, ".max": format_max_drive}.get(target.suffix.lower())
    if writer is None:
        raise CardError(f"{target.name}: export as .psu or .max.")
    with open_card(card) as mc:
        try:
            save = mc.export_save_file("/" + name)
        except (ps2mc.error, AssertionError) as error:
            raise CardError(_reason(card, error)) from error
    temp = target.with_name(f".{target.name}.new")
    try:
        with open(temp, "wb") as f:
            writer.save(save, f)
        os.replace(temp, target)
    except OSError as error:
        raise CardError(f"{target.name} could not be written: {error.strerror or error}") from error
    finally:
        temp.unlink(missing_ok=True)
    return target


def _params(size_mb: int, ecc: bool) -> tuple[bool, int, int, int]:
    """mymc++'s format parameters: ECC, page size, pages per erase block, pages on the card."""
    pages = size_mb * (1 << 20) // PAGE
    return ecc, PAGE, ps2mc.PS2MC_STANDARD_PAGES_PER_ERASE_BLOCK, pages


def _format(path: Path, size_mb: int, ecc: bool) -> None:
    with open(path, "w+b") as f:
        ps2mc.ps2mc(f, True, _params(size_mb, ecc)).close()


def new_card(folder: Path, name: str, size_mb: int = 8) -> Path:
    """A new formatted card in PCSX2's folder: *name* with .ps2 (PCSX2's, with ECC) or .mc2/.bin (without, as a
    MemCard PRO2 reads); .ps2 when it has none of those."""
    name = name.strip()
    if not name or "/" in name or name.startswith("."):
        raise CardError("Give the card a name, without / and not starting with a dot.")
    if Path(name).suffix not in PS2_SUFFIXES:
        name += ".ps2"
    if size_mb not in SIZES_MB:
        raise CardError(f"A card is {', '.join(map(str, SIZES_MB))} MB.")
    path = folder / name
    if path.exists():
        raise CardError(f"{name} already exists.")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _replace(path, lambda temp: _format(temp, size_mb, path.suffix == ".ps2"))
    except OSError as error:
        raise CardError(f"{name} could not be made: {error.strerror or error}") from error
    return path


def card_size(path: Path) -> tuple[int, bool]:
    """(MB, ECC) from the file's size, as PCSX2 tells them apart; CardError for a size no card has."""
    size = path.stat().st_size
    for mb in SIZES_MB:
        pages = mb * (1 << 20) // PAGE
        if size == pages * PAGE_WITH_ECC:
            return mb, True
        if size == pages * PAGE:
            return mb, False
    raise CardError(f"{path.name} has a size no PS2 card has ({size} bytes).")


def format_card(card: Path) -> str:
    """The card emptied: formatted again at its own size, with or without ECC as it was. The backup keeps the
    saves."""
    size_mb, ecc = card_size(card)
    if pcsx2_running():
        raise CardError("PCSX2 is running: close it first, it would write its own copy of the card over the change.")
    saved = backup(card)
    try:
        _replace(card, lambda temp: _format(temp, size_mb, ecc))
    except OSError as error:
        saved.unlink(missing_ok=True)
        raise CardError(f"{card.name} could not be formatted: {error.strerror or error}") from error
    return f"{card.name} was formatted ({size_mb} MB); the saves it had are in {saved.name}."


def check_card(card: Path) -> tuple[bool, str]:
    """mymc++'s check of the card's file system, and of every page against its ECC on a card that has one.
    (no problems, the report in words)."""
    lines: list[str] = []
    with open_card(card) as mc:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                ok = bool(mc.check())
        except (ps2mc.error, IndexError, ValueError, struct.error) as error:
            ok = False
            out.write(f"the check stopped: {error}\n")
        lines += [line.strip() for line in out.getvalue().splitlines() if line.strip()]
        bad = []
        if mc.spare_size:
            for page in range(min(mc.clusters_per_card * mc.pages_per_cluster, CHECK_PAGES_LIMIT)):
                try:
                    mc.read_page(page)
                except ps2mc.ecc_error:
                    bad.append(page)
        if bad:
            ok = False
            shown = ", ".join(f"{p:05x}" for p in bad[:20]) + (", …" if len(bad) > 20 else "")
            lines.append(f"{len(bad)} page(s) do not match their ECC: {shown}")
    if ok:
        return True, f"{card.name}: no problems found."
    return False, f"{card.name}: problems found.\n" + "\n".join(lines)


# --- Words for the window -------------------------------------------------------------------------------------

def kib(size: int) -> str:
    return f"{size // 1024:,} KB"


def when(seconds: float) -> str:
    return time.strftime("%d-%m-%Y %H:%M", time.localtime(seconds)) if seconds > 0 else "—"
