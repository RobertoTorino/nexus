# SPDX-License-Identifier: GPL-3.0-or-later
"""The BIOS as the app shows it: the setup screens of a BIOS file, the values each setting has, and what the BIOS
hides and why.

A BIOS file is the maker's update (ASUS's RC73XAAS.319, a .cap or a .bin), or that file still in its zip: its
setup screens (HII forms), its defaults (StdDefaults) and, when the file holds them, stored values. A setting shows
the value the device has (read with device.py, when asked), else the file's stored value, else its default; the
conditions that hide a menu or a setting follow those values. The parsers (firmware.py, hii.py) and the conditions
are the BC250 Bazzite Suite's BIOS Reader's."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from . import firmware, hii
from .hii import FormSet, Statement

MAX_SIZE = 64 * 1024 * 1024             # a BIOS file is 16 or 32 MiB; anything far larger is something else
SUFFIXES = (".cap", ".bin", ".rom", ".fd", ".zip", *(f".{n:03d}" for n in range(1000)))  # ASUS: RC73XAAS.319
SETUP_FORMSET = "7B59104A-C00D-4158-87FF-F04D6396A915"
ASUS_VERSION = re.compile(rb"\$AsusTestVer\$\0*([A-Za-z0-9_]+\.\d+)\0")
TEMPLATE_DATE = "12/12/2012"            # AMI's template in a file's SMBIOS table: the BIOS fills it in at boot

Key = tuple[str, str]                   # (variable GUID in upper case, name)

DEVICE, FILE, DEFAULT = "device", "file", "default"     # where a value comes from


class BiosError(ValueError):
    pass


@dataclass
class Identity:
    """The BIOS's maker, version and date, as SMBIOS has them (the device's) or as the file names them."""
    vendor: str = ""
    version: str = ""
    date: str = ""


def smbios_bios(image: bytes) -> Identity:
    """Vendor, version and date from the SMBIOS type 0 table stored in a flash image ("" when not found)."""
    pos = 0
    while (i := image.find(b"\x00", pos)) >= 0 and i + 0x12 < len(image):
        pos = i + 1
        length = image[i + 1]
        if not 0x12 <= length <= 0x1A or image[i + 4] != 1 or image[i + 5] != 2 or image[i + 8] != 3:
            continue
        strings = image[i + length:i + length + 200].split(b"\0")
        if len(strings) < 3:
            continue
        try:
            vendor, version, date = (s.decode("ascii") for s in strings[:3])
        except UnicodeDecodeError:
            continue
        if re.fullmatch(r"\d\d/\d\d/\d{4}", date) and version and vendor.isprintable():
            return Identity(vendor, version, date)
    return Identity()


def _image_identity(fw: firmware.Firmware) -> Identity:
    """The file's own version: ASUS's version marker, else the SMBIOS table (unless it is AMI's template)."""
    if (found := ASUS_VERSION.search(fw.image)) is not None:
        smbios = _smbios_of(fw)
        return Identity(smbios.vendor, found[1].decode("ascii"), "")
    smbios = _smbios_of(fw)
    if smbios.date == TEMPLATE_DATE:
        return Identity(smbios.vendor, "", "")
    return smbios


def _smbios_of(fw: firmware.Firmware) -> Identity:
    for f in fw.files():
        for sec in firmware.walk_sections(f.sections):
            if b"\x00\x18" in sec.body or b"\x00\x1a" in sec.body:
                found = smbios_bios(sec.body)
                if found.version:
                    return found
    return Identity()


def formsets_of(fw: firmware.Firmware) -> list[FormSet]:
    out: list[FormSet] = []
    for f in fw.files():
        pe = f.section(firmware.SEC_PE32)
        if pe is not None and hii.PKG_FORMS.to_bytes(1, "little") + b"\x0e" in pe:
            out.extend(hii.read_module(pe, f.name))
    return out


def _keyed(variables: dict) -> dict[Key, bytes]:
    return {(str(g).upper(), n): v.data for (g, n), v in variables.items()}


def read_file(path: Path) -> tuple[str, bytes]:
    """(the image's name, its bytes): the file itself, or the largest file in a zip (the maker's download)."""
    if path.stat().st_size > MAX_SIZE:
        raise BiosError(f"{path.name} is larger than a BIOS file can be.")
    if path.suffix.lower() != ".zip":
        return path.name, path.read_bytes()
    try:
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if not members:
                raise BiosError(f"{path.name} is empty.")
            biggest = max(members, key=lambda m: m.file_size)
            if biggest.file_size > MAX_SIZE:
                raise BiosError(f"{biggest.filename} in {path.name} is larger than a BIOS file can be.")
            return Path(biggest.filename).name, archive.read(biggest)
    except zipfile.BadZipFile as error:
        raise BiosError(f"{path.name} is not a zip that can be read: {error}") from error


@dataclass
class Bios:
    formsets: list[FormSet]
    stored: dict[Key, bytes]            # the values the file holds (a vendor file: usually none)
    defaults: dict[Key, bytes]          # StdDefaults
    name: str = ""                      # the image's file name
    identity: Identity = field(default_factory=Identity)
    sha256: str = ""
    device: dict[Key, bytes] = field(default_factory=dict)      # read from the device (device.py)

    def formset(self, guid: str) -> FormSet | None:
        return next((fs for fs in self.formsets if fs.guid == guid), None)

    @property
    def values(self) -> dict[Key, bytes]:
        """What a setting shows: the device's variable, else the file's, else its default."""
        return {**self.defaults, **self.stored, **self.device}

    def source(self, key: Key) -> str:
        if key in self.device:
            return DEVICE
        return FILE if key in self.stored else DEFAULT if key in self.defaults else ""

    def stores(self) -> list[Key]:
        """Every variable the setup screens store their settings in, once, in order."""
        seen: dict[Key, None] = {}
        for fs in self.formsets:
            for store in fs.varstores.values():
                seen.setdefault((store.guid.upper(), store.name), None)
        return list(seen)


def load_image(name: str, image: bytes) -> Bios:
    fw = firmware.parse_image(image)
    formsets = formsets_of(fw)
    if not formsets:
        raise BiosError(f"{name} has no setup screens: it may be another firmware (a controller's, a drive's).")
    return Bios(formsets, _keyed(fw.variables), _keyed(fw.defaults), name, _image_identity(fw),
                hashlib.sha256(image).hexdigest())


def load_file(path: Path) -> Bios:
    """A BIOS file (or its zip); raises BiosError or firmware.FirmwareError with what is wrong."""
    try:
        name, image = read_file(path)
    except OSError as error:
        raise BiosError(f"{path.name} could not be read: {error.strerror or error}") from error
    return load_image(name, image)


# --- Values and visibility ------------------------------------------------------------------------------------

@dataclass
class ItemState:
    hidden: bool = False                # the BIOS does not show it (on its form)
    always: bool = False                # hidden whatever the settings are (SuppressIf TRUE)
    grayed: bool = False                # shown but locked
    unknown: bool = False               # depends on a value this app cannot read
    reason: str = ""


class Screens:
    """Evaluates the setup screens of a Bios: each question's value and default, which items and forms the BIOS
    hides and why."""

    def __init__(self, bios: Bios):
        self.bios = bios
        self.values = bios.values
        self._questions: dict[tuple[str, int], Statement] = {}
        for fs in bios.formsets:
            for form in fs.forms:
                for st in form.statements:
                    if st.question_id and st.kind != "ref":
                        self._questions.setdefault((fs.guid, st.question_id), st)
        self._form_states = self._reachability()

    # Values

    def key(self, fs: FormSet, st: Statement) -> Key | None:
        store = fs.varstores.get(st.varstore)
        return (store.guid.upper(), store.name) if store is not None else None

    def _variable(self, fs: FormSet, st: Statement, source: dict[Key, bytes]) -> bytes | None:
        key = self.key(fs, st)
        return source.get(key) if key is not None else None

    def raw_value(self, fs: FormSet, st: Statement) -> int | None:
        return _read(self._variable(fs, st, self.values), st)

    def default_value(self, fs: FormSet, st: Statement) -> int | None:
        stored = _read(self._variable(fs, st, self.bios.defaults), st)
        return stored if stored is not None else st.default

    def source(self, fs: FormSet, st: Statement) -> str:
        """Where the setting's value comes from: DEVICE, FILE, DEFAULT or "" (none)."""
        key = self.key(fs, st)
        return self.bios.source(key) if key is not None else ""

    def string_value(self, fs: FormSet, st: Statement) -> str | None:
        data = self._variable(fs, st, self.values)
        if data is None or st.offset + st.size > len(data):
            return None
        return data[st.offset:st.offset + st.size].decode("utf-16-le", "replace").split("\0", 1)[0]

    def ascii_value(self, fs: FormSet, st: Statement) -> str | None:
        """The whole variable as text, for the few that hold a string ("en-US" in PlatformLang)."""
        data = self._variable(fs, st, self.values)
        return data.split(b"\0", 1)[0].decode("ascii", "replace") if data is not None else None

    def store_label(self, fs: FormSet, st: Statement) -> str:
        store = fs.varstores.get(st.varstore)
        return f"{store.name} + 0x{st.offset:X}" if store else f"varstore 0x{st.varstore:X}"

    # Conditions

    def evaluate(self, fs: FormSet, expr: list[tuple]) -> bool | None:
        """A postfix condition -> True/False, or None when it needs a value this app cannot read."""
        stack: list = []
        try:
            for term in expr:
                op = term[0]
                if op == "true":
                    stack.append(True)
                elif op == "false":
                    stack.append(False)
                elif op in ("const",):
                    stack.append(term[1])
                elif op == "zero":
                    stack.append(0)
                elif op == "one":
                    stack.append(1)
                elif op == "ones":
                    stack.append(0xFFFFFFFFFFFFFFFF)
                elif op == "eq_id_val":
                    v = self._qvalue(fs, term[1])
                    stack.append(None if v is None else v == term[2])
                elif op == "eq_id_id":
                    a, b = self._qvalue(fs, term[1]), self._qvalue(fs, term[2])
                    stack.append(None if a is None or b is None else a == b)
                elif op == "eq_id_list":
                    v = self._qvalue(fs, term[1])
                    stack.append(None if v is None else v in term[2])
                elif op == "question_ref1":
                    stack.append(self._qvalue(fs, term[1]))
                elif op == "not":
                    v = stack.pop()
                    stack.append(None if v is None else not v)
                elif op in ("and", "or"):
                    b, a = stack.pop(), stack.pop()
                    stack.append(_logic(op, a, b))
                elif op in _COMPARE:
                    b, a = stack.pop(), stack.pop()
                    stack.append(None if a is None or b is None else _COMPARE[op](a, b))
                else:
                    return None                         # an opcode this app does not evaluate
        except IndexError:
            return None
        if len(stack) != 1:
            return None
        return None if stack[0] is None else bool(stack[0])

    def _qvalue(self, fs: FormSet, qid: int) -> int | None:
        st = self._questions.get((fs.guid, qid))
        return self.raw_value(fs, st) if st is not None else None

    def item_state(self, fs: FormSet, st: Statement) -> ItemState:
        state = ItemState()
        reasons = []
        for cond in st.conditions:
            result = self.evaluate(fs, cond.expr)
            if cond.kind == "suppress":
                if cond.expr == [("true",)]:
                    state.hidden = state.always = True
                    reasons.append("always hidden (SuppressIf TRUE)")
                elif result:
                    state.hidden = True
                    reasons.append("hidden by the value of another setting")
                elif result is None:
                    state.unknown = True
                    reasons.append("may be hidden: it depends on a value this app cannot read")
            elif result:
                state.grayed = True
                reasons.append("shown but locked (" + ("GrayOutIf" if cond.kind == "grayout" else "DisableIf") + ")")
        state.reason = "; ".join(reasons)
        return state

    # Forms

    def form_state(self, fs: FormSet, form_id: int) -> str:
        """"" when the BIOS shows the form, otherwise why not."""
        return self._form_states.get((fs.guid, form_id), "not linked from any menu")

    def _reachability(self) -> dict[tuple[str, int], str]:
        """Walk the links from each form set's first form; a form reached only through hidden links is hidden."""
        states: dict[tuple[str, int], str] = {}
        todo: deque[tuple[FormSet, int]] = deque()
        for fs in self.bios.formsets:
            if fs.root is not None:
                states[(fs.guid, fs.root.id)] = ""
                todo.append((fs, fs.root.id))
        hidden_links: list[tuple[FormSet, int, str]] = []
        while todo:
            fs, form_id = todo.popleft()
            form = fs.form(form_id)
            if form is None:
                continue
            for st in form.statements:
                if st.kind != "ref":
                    continue
                target_fs = self.bios.formset(st.target_formset) if st.target_formset else fs
                if target_fs is None or target_fs.form(st.target_form) is None:
                    continue
                key = (target_fs.guid, st.target_form)
                if self.item_state(fs, st).hidden:
                    hidden_links.append((target_fs, st.target_form, f"its link \"{st.prompt}\" is hidden"))
                elif key not in states or states[key]:
                    states[key] = ""
                    todo.append((target_fs, st.target_form))
        # Forms behind hidden links, and everything they lead to, are hidden with that reason.
        for fs, form_id, reason in hidden_links:
            stack = [(fs, form_id)]
            while stack:
                cur_fs, cur = stack.pop()
                if (cur_fs.guid, cur) in states:
                    continue
                states[(cur_fs.guid, cur)] = reason
                form = cur_fs.form(cur)
                for st in form.statements if form else ():
                    if st.kind == "ref" and not st.target_formset:
                        stack.append((cur_fs, st.target_form))
        return states

    def unlinked_forms(self) -> list[tuple[FormSet, hii.Form]]:
        """Forms no link anywhere leads to (each form set's first form aside): only reachable in this app."""
        targets = {(st.target_formset or fs.guid, st.target_form)
                   for fs in self.bios.formsets for form in fs.forms for st in form.statements if st.kind == "ref"}
        return [(fs, form) for fs in self.bios.formsets for form in fs.forms
                if form is not fs.root and (fs.guid, form.id) not in targets]

    def hidden_forms(self) -> Iterator[tuple[FormSet, hii.Form, str]]:
        for fs in self.bios.formsets:
            for form in fs.forms:
                if reason := self.form_state(fs, form.id):
                    yield fs, form, reason


_COMPARE = {
    "equal": lambda a, b: a == b, "not_equal": lambda a, b: a != b, "greater_than": lambda a, b: a > b,
    "greater_equal": lambda a, b: a >= b, "less_than": lambda a, b: a < b, "less_equal": lambda a, b: a <= b,
    "bitwise_and": lambda a, b: a & b, "bitwise_or": lambda a, b: a | b, "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
}


def _logic(op: str, a, b) -> bool | None:
    if op == "and":
        if a is False or b is False:
            return False
        return None if a is None or b is None else bool(a and b)
    if a is True or b is True:
        return True
    return None if a is None or b is None else bool(a or b)


def _read(data: bytes | None, st: Statement) -> int | None:
    if data is None or st.offset + st.size > len(data):
        return None
    return int.from_bytes(data[st.offset:st.offset + st.size], "little")


def value_text(st: Statement, value: int | None) -> str:
    """How the setup screen shows a value: an option's name, Enabled/Disabled, a number."""
    if value is None:
        return "?"
    if st.kind == "checkbox":
        return "Enabled" if value else "Disabled"
    if st.kind == "oneof":
        for opt in st.options:
            if opt.value == value:
                return opt.text
        return f"0x{value:X} (not one of the options)"
    if st.hex_display:
        return f"0x{value:X}"
    return str(value)
