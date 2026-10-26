# SPDX-License-Identifier: GPL-3.0-or-later
"""The BIOS as the app shows it: setup screens, stored values and defaults, what the BIOS hides, and whether it is a
stock release.

Two sources:
  * a dump of the flash chip (load_dump): its own setup screens, every variable and the StdDefaults;
  * the running board (load_running): the built-in table of its BIOS release for the screens and defaults, and the
    UEFI variables Linux can read for the values (AmdSetup; the main Setup variable is hidden after boot)."""

from __future__ import annotations

import hashlib
import re
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from . import firmware, hii, table
from .hii import FormSet, Statement

# The stock releases this app knows, with the fingerprints of their setup screens (SHA-256 of each form package)
# and the size of the AMD CBS variable. Taken from a dump of a stock P5.00 board.
STOCK = {
    "P5.00": {
        "date": "05/03/2022",
        "amdsetup_size": 0x8B5,
        "formsets": {
            "B04535E3-3004-4946-9EB7-149428983053": "55c91bd0dd29cb71f1c6deb3dae8c844feda5635ac2b980da3911a240794d370",
            "7B59104A-C00D-4158-87FF-F04D6396A915": "c0296f4ca9bc9e05d0cb220815ad94c430306a222fdcef1c46b30476a8dc46a2",
            "941BC855-BF7E-4FCB-882F-7AEAD15C9D47": "ed5ea5dccec563042683b68b8ffc7b007b73784ba91d042076826922916dcc9a",
            "80E1202E-2697-4264-9CC9-80762C3E5863": "cc3831add5d41e343bbbe715dad39f28b5da126f820905c2c1a3e7e541b11d75",
            "5E39CF2E-6712-45AB-84C4-35D3C6A3686D": "de56c91402c69e64be2cc0526ee0e7f9e8e660020b2cdc14f2219d82442711c4",
            "4D20583A-7765-4E7A-8A67-DCDE74EE3EC5": "79cae4fd1c44bf1ec3c0d94670f9bd8c8a823efdee2887b1128619e0182b9259",
            "CEE81408-4764-4314-AB17-5D61691BDA1F": "fdda595e9db762ede08d518700aa18f5309236ec06c0430bab3720487a89bade",
        },
    },
}
AMD_SETUP = ("3A997502-647A-4C82-998E-52EF9486A247", "AmdSetup")
SETUP_FORMSET = "7B59104A-C00D-4158-87FF-F04D6396A915"
# Version strings, with the same rules as bazzite-test's BIOS check.
STOCK_VERSION = re.compile(r"^[LP]?([1-5])\.00$")
MODDED_VERSION = re.compile(r"meimei|mod|unlock", re.IGNORECASE)

Key = tuple[str, str]               # (variable GUID in upper case, name)


@dataclass
class Dmi:
    vendor: str = ""
    version: str = ""
    date: str = ""


def read_dmi(sys_root: Path = Path("/sys")) -> Dmi:
    folder = sys_root / "class" / "dmi" / "id"

    def read(name: str) -> str:
        try:
            return (folder / name).read_text(errors="replace").strip()
        except OSError:
            return ""
    return Dmi(read("bios_vendor"), read("bios_version"), read("bios_date"))


def read_efivars(sys_root: Path = Path("/sys")) -> dict[Key, bytes]:
    """The UEFI variables Linux exposes (runtime ones only), without their 4 attribute bytes. Needs no root."""
    out: dict[Key, bytes] = {}
    folder = sys_root / "firmware" / "efi" / "efivars"
    try:
        entries = list(folder.iterdir())
    except OSError:
        return out
    for path in entries:
        # "AmdSetup-3a997502-647a-4c82-998e-52ef9486a247": the name, a dash and a 36-character GUID
        if len(path.name) < 38 or path.name[-37] != "-":
            continue
        name, guid = path.name[:-37], path.name[-36:]
        try:
            data = path.read_bytes()
        except OSError:
            continue
        out[(guid.upper(), name)] = data[4:]
    return out


def smbios_bios(image: bytes) -> Dmi:
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
            return Dmi(vendor, version, date)
    return Dmi()


@dataclass
class Bios:
    formsets: list[FormSet]
    values: dict[Key, bytes]            # current variable contents
    defaults: dict[Key, bytes]          # StdDefaults variables
    source: str                         # "dump" or "running"
    version: str = ""                   # of the BIOS the screens come from
    date: str = ""
    vendor: str = ""
    dump_path: str = ""
    dump_sha256: str = ""
    dmi: Dmi = field(default_factory=Dmi)
    note: str = ""                      # why something is missing, shown in the window

    def formset(self, guid: str) -> FormSet | None:
        return next((fs for fs in self.formsets if fs.guid == guid), None)


def _image_bios(fw: firmware.Firmware) -> Dmi:
    for f in fw.files():
        for sec in firmware.walk_sections(f.sections):
            if b"\x00\x18" in sec.body or b"\x00\x1a" in sec.body:
                found = smbios_bios(sec.body)
                if found.version:
                    return found
    return Dmi()


def formsets_of(fw: firmware.Firmware) -> list[FormSet]:
    out: list[FormSet] = []
    for f in fw.files():
        pe = f.section(firmware.SEC_PE32)
        if pe is not None and hii.PKG_FORMS.to_bytes(1, "little") + b"\x0e" in pe:
            out.extend(hii.read_module(pe, f.name))
    return out


def _keyed(variables: dict) -> dict[Key, bytes]:
    return {(str(g).upper(), n): v.data for (g, n), v in variables.items()}


def load_dump(path: Path, sys_root: Path = Path("/sys")) -> Bios:
    image = path.read_bytes()
    fw = firmware.parse_image(image)
    found = _image_bios(fw)
    return Bios(formsets_of(fw), _keyed(fw.variables), _keyed(fw.defaults), "dump", found.version, found.date,
                found.vendor, str(path), hashlib.sha256(image).hexdigest(), read_dmi(sys_root))


def load_running(sys_root: Path = Path("/sys"), tables_dir: Path = table.TABLES_DIR) -> Bios:
    """The running board: the table of its BIOS release (when there is one) and the readable UEFI variables."""
    dmi = read_dmi(sys_root)
    values = read_efivars(sys_root)
    path = table.table_path(dmi.version, tables_dir) if dmi.version else None
    if path is None or not path.is_file():
        note = (f"There is no built-in table for BIOS {dmi.version or '(unknown)'}. Read the BIOS chip or open a "
                "dump to see its setup screens.")
        return Bios([], values, {}, "running", dmi.version, dmi.date, dmi.vendor, dmi=dmi, note=note)
    version, date, formsets, defaults = table.load_table(path)
    note = ("The main Setup variable is not readable while the system runs: its options show their defaults. "
            "Read the BIOS chip to see the values stored in it.")
    return Bios(formsets, values, defaults, "running", version, date, dmi.vendor, dmi=dmi, note=note)


def build_table(dump: Path) -> tuple[str, bytes]:
    """(file name, gzipped table) made from a dump: its screens, StdDefaults, version and date."""
    bios = load_dump(dump)
    if not bios.version:
        raise ValueError("the dump has no SMBIOS BIOS version, so the table would have no name")
    data = table.dump_table(bios.version, bios.date, bios.formsets, bios.defaults)
    return table.table_path(bios.version).name, data


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
        self._questions: dict[tuple[str, int], Statement] = {}
        for fs in bios.formsets:
            for form in fs.forms:
                for st in form.statements:
                    if st.question_id and st.kind != "ref":
                        self._questions.setdefault((fs.guid, st.question_id), st)
        self._form_states = self._reachability()

    # Values

    def _variable(self, fs: FormSet, st: Statement, source: dict[Key, bytes]) -> bytes | None:
        store = fs.varstores.get(st.varstore)
        if store is None:
            return None
        return source.get((store.guid, store.name))

    def raw_value(self, fs: FormSet, st: Statement) -> int | None:
        data = self._variable(fs, st, self.bios.values)
        return _read(data, st)

    def default_value(self, fs: FormSet, st: Statement) -> int | None:
        stored = _read(self._variable(fs, st, self.bios.defaults), st)
        return stored if stored is not None else st.default

    def string_value(self, fs: FormSet, st: Statement) -> str | None:
        data = self._variable(fs, st, self.bios.values)
        if data is None or st.offset + st.size > len(data):
            return None
        return data[st.offset:st.offset + st.size].decode("utf-16-le", "replace").split("\0", 1)[0]

    def ascii_value(self, fs: FormSet, st: Statement) -> str | None:
        """The whole variable as text, for the few that hold a string ("en-US" in PlatformLang)."""
        data = self._variable(fs, st, self.bios.values)
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
                    reasons.append("hidden by the current value of another setting")
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


# --- Stock or modded -------------------------------------------------------------------------------------------

@dataclass
class Verdict:
    kind: str                           # "stock", "modded" or "unknown"
    title: str                          # "Stock BIOS P5.00"
    certain: bool                       # proven by the setup screens of a dump
    reasons: list[str] = field(default_factory=list)


def verdict(bios: Bios, stock_screens: Screens | None = None) -> Verdict:
    """Is the BIOS a stock release? From a dump: its setup screens against the stock fingerprints (and, with the
    stock table in *stock_screens*, which hidden menus it opens). From the running board: the version string and
    the size of the AMD CBS variable."""
    if bios.source == "dump":
        return _dump_verdict(bios, stock_screens)
    return _running_verdict(bios)


def _dump_verdict(bios: Bios, stock_screens: Screens | None) -> Verdict:
    version = bios.version or "(no version in the dump)"
    reasons = []
    if bios.dmi.version and bios.version and bios.dmi.version != bios.version:
        reasons.append(f"The dump is BIOS {bios.version}; the running board reports {bios.dmi.version}.")
    stock = STOCK.get(bios.version)
    if stock is None:
        reasons.append(f"This app knows the setup screens of stock {', '.join(STOCK)} only.")
        if MODDED_VERSION.search(bios.version):
            reasons.insert(0, f"The version string \"{bios.version}\" names a modded BIOS.")
            return Verdict("modded", "Modded BIOS", False, reasons)
        return Verdict("unknown", f"BIOS {version}", False, reasons)
    present = {fs.guid: fs for fs in bios.formsets}
    changed = [present[g].title for g, sha in stock["formsets"].items() if g in present and present[g].sha256 != sha]
    missing = [g for g in stock["formsets"] if g not in present]
    added = [fs.title for fs in bios.formsets if fs.guid not in stock["formsets"]]
    if not changed and not missing and not added:
        reasons.insert(0, f"Its setup screens are identical to those of stock {bios.version}.")
        return Verdict("stock", f"Stock BIOS {bios.version}", True, reasons)
    if changed:
        reasons.insert(0, "Setup screens that differ from stock " + bios.version + ": " + ", ".join(changed) + ".")
    if added:
        reasons.append("Setup screens stock " + bios.version + " does not have: " + ", ".join(added) + ".")
    if missing:
        reasons.append(f"{len(missing)} setup screen(s) of stock {bios.version} are missing.")
    if stock_screens is not None:
        opened = unlocked_forms(stock_screens, Screens(bios))
        if opened:
            reasons.append("Menus stock " + bios.version + " hides that this BIOS shows: " + ", ".join(opened) + ".")
    return Verdict("modded", f"Modded BIOS (based on {bios.version})", True, reasons)


def unlocked_forms(stock: Screens, other: Screens) -> list[str]:
    """Titles of the forms the stock BIOS hides and *other* shows."""
    out = []
    for fs, form, _ in stock.hidden_forms():
        mine = other.bios.formset(fs.guid)
        if mine is not None and mine.form(form.id) is not None and not other.form_state(mine, form.id):
            out.append(form.title or f"form 0x{form.id:X}")
    return out


def _running_verdict(bios: Bios) -> Verdict:
    version = bios.dmi.version
    if not version:
        return Verdict("unknown", "BIOS version unknown", False, ["Linux does not report a BIOS version (DMI)."])
    if MODDED_VERSION.search(version):
        return Verdict("modded", "Modded BIOS", False, [f"The version string \"{version}\" names a modded BIOS."])
    stock = STOCK.get(version)
    if stock is not None:
        amd = bios.values.get(AMD_SETUP)
        if amd is not None and len(amd) != stock["amdsetup_size"]:
            return Verdict("modded", f"Modded BIOS (reports {version})", False, [
                f"The AMD CBS settings take {len(amd)} bytes; in stock {version} they take {stock['amdsetup_size']}. "
                "The BIOS's AMD CBS screens are changed."])
        reasons = [f"The version string is that of stock {version}" +
                   (" and the AMD CBS settings have the stock layout." if amd is not None else ".")]
        if bios.dmi.date and bios.dmi.date != stock["date"]:
            reasons.append(f"Its date {bios.dmi.date} differs from stock {version} ({stock['date']}).")
        reasons.append("Many modded BIOSes keep the stock version string: read the BIOS chip to be sure.")
        return Verdict("stock", f"Stock BIOS {version}", False, reasons)
    if STOCK_VERSION.match(version):
        return Verdict("stock", f"Stock BIOS {version}", False, [
            f"The version string is that of a stock release; this app has no setup screens for {version}."])
    return Verdict("unknown", f"BIOS {version}", False, ["The version string matches no stock release."])
