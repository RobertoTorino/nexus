# SPDX-License-Identifier: GPL-3.0-or-later
"""Reads the setup screens of a BIOS module: its HII form packages (IFR) and en-US string packages.

The result is a plain model: form sets with forms, and on each form the statements in order (subtitles, texts,
links to other forms and the questions with their variable, offset, size, options and defaults). Each statement
keeps the conditions it sits under (SuppressIf, GrayOutIf, DisableIf), as postfix expressions that bios.py
evaluates against the stored values. Opcodes: UEFI specification, chapter "Human Interface Infrastructure"."""

from __future__ import annotations

import hashlib
import struct
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

PKG_FORMS, PKG_STRINGS, PKG_END = 0x02, 0x04, 0xDF
LANGUAGE = b"en-US"

# Opcodes this reader uses
OP_FORM, OP_SUBTITLE, OP_TEXT, OP_ONE_OF, OP_CHECKBOX, OP_NUMERIC = 0x01, 0x02, 0x03, 0x05, 0x06, 0x07
OP_PASSWORD, OP_ONE_OF_OPTION, OP_SUPPRESS_IF, OP_ACTION, OP_RESET_BUTTON = 0x08, 0x09, 0x0A, 0x0C, 0x0D
OP_FORM_SET, OP_REF, OP_GRAY_OUT_IF, OP_DATE, OP_TIME, OP_STRING = 0x0E, 0x0F, 0x19, 0x1A, 0x1B, 0x1C
OP_DISABLE_IF, OP_ORDERED_LIST, OP_VARSTORE, OP_VARSTORE_EFI, OP_END = 0x1E, 0x23, 0x24, 0x26, 0x29
OP_DEFAULT, OP_GUID, OP_FORM_MAP = 0x5B, 0x5F, 0x5D

CONDITIONS = {OP_SUPPRESS_IF: "suppress", OP_GRAY_OUT_IF: "grayout", OP_DISABLE_IF: "disable"}
QUESTIONS = {OP_ONE_OF: "oneof", OP_CHECKBOX: "checkbox", OP_NUMERIC: "numeric", OP_PASSWORD: "password",
             OP_ACTION: "action", OP_DATE: "date", OP_TIME: "time", OP_STRING: "string",
             OP_ORDERED_LIST: "orderedlist", OP_REF: "ref"}

# Expression opcodes and how many bytes of operands each takes (after the 2-byte header); -1: read by length.
EXPRESSIONS = {
    0x12: "eq_id_val", 0x13: "eq_id_id", 0x14: "eq_id_list", 0x15: "and", 0x16: "or", 0x17: "not",
    0x2A: "match", 0x2B: "get", 0x2F: "equal", 0x30: "not_equal", 0x31: "greater_than", 0x32: "greater_equal",
    0x33: "less_than", 0x34: "less_equal", 0x35: "bitwise_and", 0x36: "bitwise_or", 0x37: "bitwise_not",
    0x38: "shift_left", 0x39: "shift_right", 0x3A: "add", 0x3B: "subtract", 0x3C: "multiply", 0x3D: "divide",
    0x3E: "modulo", 0x3F: "rule_ref", 0x40: "question_ref1", 0x41: "question_ref2", 0x42: "uint8",
    0x43: "uint16", 0x44: "uint32", 0x45: "uint64", 0x46: "true", 0x47: "false", 0x48: "to_uint",
    0x49: "to_string", 0x4A: "to_boolean", 0x4B: "mid", 0x4C: "find", 0x4D: "token", 0x4E: "string_ref1",
    0x4F: "string_ref2", 0x50: "conditional", 0x51: "question_ref3", 0x52: "zero", 0x53: "one", 0x54: "ones",
    0x55: "undefined", 0x56: "length", 0x57: "dup", 0x58: "this", 0x59: "span", 0x5A: "value", 0x5E: "catenate",
    0x60: "security", 0x64: "match2", 0x20: "to_lower", 0x21: "to_upper", 0x22: "map",
}


@dataclass
class Option:
    text: str
    value: int
    default: bool = False


@dataclass
class Condition:
    kind: str                       # "suppress", "grayout" or "disable"
    expr: list[tuple]               # postfix: ("eq_id_val", qid, value), ("not",), ("true",), ...


@dataclass
class Statement:
    kind: str                       # "subtitle", "text", "ref", "oneof", "checkbox", "numeric", "string", ...
    prompt: str
    help: str = ""
    text: str = ""                  # a text statement's second string
    question_id: int = 0
    varstore: int = 0
    offset: int = 0                 # VarStoreInfo: byte offset into the variable
    size: int = 1                   # bytes the value takes
    flags: int = 0
    minimum: int = 0
    maximum: int = 0
    step: int = 0
    options: list[Option] = field(default_factory=list)
    default: int | None = None
    target_form: int = 0            # ref: form id it opens
    target_formset: str = ""        # ref: other form set (GUID), "" for this one
    conditions: list[Condition] = field(default_factory=list)

    @property
    def is_question(self) -> bool:
        return self.kind in QUESTIONS.values() and self.kind != "ref"

    @property
    def hex_display(self) -> bool:
        return self.kind == "numeric" and self.flags & 0x30 == 0x20


@dataclass
class VarStore:
    id: int
    guid: str
    name: str
    size: int


@dataclass
class Form:
    id: int
    title: str
    statements: list[Statement] = field(default_factory=list)


@dataclass
class FormSet:
    guid: str
    title: str
    help: str
    module: str                     # the BIOS file the forms come from ("Setup", "CbsSetupDxe")
    varstores: dict[int, VarStore] = field(default_factory=dict)
    forms: list[Form] = field(default_factory=list)
    sha256: str = ""                # of the form package: tells a stock form set from a changed one

    def form(self, form_id: int) -> Form | None:
        return next((f for f in self.forms if f.id == form_id), None)

    @property
    def root(self) -> Form | None:
        return self.forms[0] if self.forms else None


class HiiError(ValueError):
    pass


# --- Packages -----------------------------------------------------------------------------------------------

def _pkg_header(data: bytes, pos: int) -> tuple[int, int]:
    return int.from_bytes(data[pos:pos + 3], "little"), data[pos + 3]


def _walks_cleanly(data: bytes, start: int, length: int) -> bool:
    """True when the opcodes from *start* fill exactly *length* bytes: a real form package, not a chance match."""
    pos, end = start, start + length
    while pos < end:
        oplen = data[pos + 1] & 0x7F
        if oplen < 2:
            return False
        pos += oplen
    return pos == end


def find_form_packages(module: bytes) -> list[bytes]:
    """Form packages (header included) in a module's bytes: package type 0x02 followed by a FormSet opcode."""
    out, pos = [], 0
    while (i := module.find(bytes([PKG_FORMS, OP_FORM_SET]), pos)) >= 0:
        start = i - 3
        pos = i + 1
        if start < 0:
            continue
        length, _ = _pkg_header(module, start)
        if 6 < length <= len(module) - start and _walks_cleanly(module, start + 4, length - 4):
            out.append(bytes(module[start:start + length]))
            pos = start + length
    return out


def find_string_packages(module: bytes, language: bytes = LANGUAGE) -> list[bytes]:
    """String packages of *language*: header 0x04, then HdrSize, StringInfoOffset, LanguageWindow, the name."""
    out, pos = [], 0
    while (i := module.find(language + b"\0", pos)) >= 0:
        start = i - 46                      # 4 header + 4 HdrSize + 4 StringInfoOffset + 32 window + 2 name
        pos = i + 1
        if start < 0 or module[start + 3] != PKG_STRINGS:
            continue
        length, _ = _pkg_header(module, start)
        hdr_size, info_offset = struct.unpack_from("<II", module, start + 4)
        if hdr_size == 46 + len(language) + 1 and info_offset == hdr_size and length <= len(module) - start:
            out.append(bytes(module[start:start + length]))
    return out


def parse_strings(package: bytes) -> dict[int, str]:
    """String id -> text, from one string package (UCS-2 blocks; the SCSU ones are kept as bytes decoded latin-1)."""
    strings: dict[int, str] = {}
    info_offset = struct.unpack_from("<I", package, 8)[0]
    pos, sid = info_offset, 1
    while pos < len(package):
        block = package[pos]
        pos += 1
        if block == 0x00:                                           # end
            break
        if block in (0x14, 0x15):                                   # one UCS-2 string (0x15: with font)
            pos += 1 if block == 0x15 else 0
            end = _ucs2_end(package, pos)
            strings[sid] = package[pos:end].decode("utf-16-le", "replace")
            pos, sid = end + 2, sid + 1
        elif block in (0x16, 0x17):                                 # several UCS-2 strings
            pos += 1 if block == 0x17 else 0
            count = struct.unpack_from("<H", package, pos)[0]
            pos += 2
            for _ in range(count):
                end = _ucs2_end(package, pos)
                strings[sid] = package[pos:end].decode("utf-16-le", "replace")
                pos, sid = end + 2, sid + 1
        elif block in (0x10, 0x11):                                 # one SCSU string
            pos += 1 if block == 0x11 else 0
            end = package.index(b"\0", pos)
            strings[sid] = package[pos:end].decode("latin-1")
            pos, sid = end + 1, sid + 1
        elif block in (0x12, 0x13):                                 # several SCSU strings
            pos += 1 if block == 0x13 else 0
            count = struct.unpack_from("<H", package, pos)[0]
            pos += 2
            for _ in range(count):
                end = package.index(b"\0", pos)
                strings[sid] = package[pos:end].decode("latin-1")
                pos, sid = end + 1, sid + 1
        elif block == 0x20:                                         # duplicate of an earlier string
            strings[sid] = strings.get(struct.unpack_from("<H", package, pos)[0], "")
            pos, sid = pos + 2, sid + 1
        elif block == 0x21:                                         # skip 2
            sid += struct.unpack_from("<H", package, pos)[0]
            pos += 2
        elif block == 0x22:                                         # skip 1
            sid += package[pos]
            pos += 1
        elif block == 0x30:                                         # ext1
            pos += package[pos + 1] - 1
        elif block == 0x31:                                         # ext2
            pos += struct.unpack_from("<H", package, pos + 1)[0] - 1
        elif block == 0x32:                                         # ext4
            pos += struct.unpack_from("<I", package, pos + 1)[0] - 1
        else:
            raise HiiError(f"unknown string block 0x{block:02X}")
    return strings


def _ucs2_end(data: bytes, pos: int) -> int:
    while pos + 1 < len(data) and data[pos:pos + 2] != b"\0\0":
        pos += 2
    return pos


# --- Forms --------------------------------------------------------------------------------------------------

def _ops(package: bytes) -> Iterator[tuple[int, int, bool, bytes]]:
    """(offset, opcode, scope, operands) for every opcode in a form package."""
    pos = 4
    while pos + 2 <= len(package):
        op, b = package[pos], package[pos + 1]
        length = b & 0x7F
        if length < 2:
            raise HiiError(f"bad opcode length at 0x{pos:X}")
        yield pos, op, bool(b & 0x80), package[pos + 2:pos + length]
        pos += length


_SIZES = {0: 1, 1: 2, 2: 4, 3: 8}


def _uint(data: bytes, offset: int, size: int) -> int:
    return int.from_bytes(data[offset:offset + size], "little")


def _expression(op: int, d: bytes) -> tuple:
    name = EXPRESSIONS[op]
    if name == "eq_id_val":
        return name, *struct.unpack_from("<HH", d)
    if name == "eq_id_id":
        return name, *struct.unpack_from("<HH", d)
    if name == "eq_id_list":
        qid, count = struct.unpack_from("<HH", d)
        return name, qid, struct.unpack_from(f"<{count}H", d, 4)
    if name == "question_ref1":
        return name, struct.unpack_from("<H", d)[0]
    if name in ("uint8", "uint16", "uint32", "uint64"):
        return "const", int.from_bytes(d, "little")
    return (name,)


def parse_forms(package: bytes, strings: dict[int, str], module: str = "") -> FormSet:
    """One form package -> FormSet."""
    s = lambda sid: strings.get(sid, "") if sid else ""            # noqa: E731
    formset: FormSet | None = None
    form: Form | None = None
    scopes: list[tuple[str, object]] = []                          # what each open scope belongs to
    question: Statement | None = None
    pending: Condition | None = None                                # condition whose expression is being read

    def open_conditions() -> list[Condition]:
        return [obj for kind, obj in scopes if kind == "cond"]     # type: ignore[misc]

    for _, op, scope, d in _ops(package):
        if pending is not None and op not in EXPRESSIONS and op != OP_END:
            pending = None                                          # the expression is complete
        if op in EXPRESSIONS:
            if pending is not None:
                pending.expr.append(_expression(op, d))
            if scope:
                scopes.append(("expr", None))
            continue
        if op == OP_END:
            if scopes:
                kind, obj = scopes.pop()
                if kind == "question" and obj is question:
                    question = None
                if kind == "form":
                    form = None
            continue

        if op == OP_FORM_SET:
            guid = str(uuid.UUID(bytes_le=d[:16])).upper()
            title, helptext = struct.unpack_from("<HH", d, 16)
            formset = FormSet(guid, s(title), s(helptext), module, sha256=hashlib.sha256(package).hexdigest())
            kind, obj = "formset", formset
        elif formset is None:
            raise HiiError("form package without a form set")
        elif op == OP_VARSTORE:
            guid = str(uuid.UUID(bytes_le=d[:16])).upper()
            vid, size = struct.unpack_from("<HH", d, 16)
            name = d[20:].split(b"\0", 1)[0].decode("ascii", "replace")
            formset.varstores[vid] = VarStore(vid, guid, name, size)
            kind, obj = "other", None
        elif op == OP_VARSTORE_EFI:
            vid = struct.unpack_from("<H", d)[0]
            guid = str(uuid.UUID(bytes_le=d[2:18])).upper()
            size = struct.unpack_from("<H", d, 22)[0]
            name = d[24:].split(b"\0", 1)[0].decode("ascii", "replace")
            formset.varstores[vid] = VarStore(vid, guid, name, size)
            kind, obj = "other", None
        elif op in (OP_FORM, OP_FORM_MAP):
            form_id = struct.unpack_from("<H", d)[0]
            title = s(struct.unpack_from("<H", d, 2)[0]) if op == OP_FORM else ""
            form = Form(form_id, title)
            formset.forms.append(form)
            kind, obj = "form", form
        elif op in CONDITIONS:
            pending = Condition(CONDITIONS[op], [])
            kind, obj = "cond", pending
        elif form is not None and op in (OP_SUBTITLE, OP_TEXT, OP_RESET_BUTTON):
            prompt, helptext = struct.unpack_from("<HH", d)
            st = Statement({OP_SUBTITLE: "subtitle", OP_TEXT: "text", OP_RESET_BUTTON: "reset"}[op],
                           s(prompt), s(helptext), conditions=list(open_conditions()))
            if op == OP_TEXT:
                st.text = s(struct.unpack_from("<H", d, 4)[0])
            form.statements.append(st)
            kind, obj = "statement", st
        elif form is not None and op in QUESTIONS:
            question = _question(op, d, s)
            question.conditions = list(open_conditions())
            form.statements.append(question)
            kind, obj = "question", question
        elif op == OP_ONE_OF_OPTION and question is not None:
            text, flags, vtype = struct.unpack_from("<HBB", d)
            size = {0: 1, 1: 2, 2: 4, 3: 8, 4: 1}.get(vtype, 0)
            value = _uint(d, 4, size) if size else 0
            question.options.append(Option(s(text), value, bool(flags & 0x10)))
            if flags & 0x10 and question.default is None:
                question.default = value
            kind, obj = "other", None
        elif op == OP_DEFAULT and question is not None:
            default_id, vtype = struct.unpack_from("<HB", d)
            size = {0: 1, 1: 2, 2: 4, 3: 8, 4: 1}.get(vtype, 0)
            if default_id == 0 and size and len(d) >= 3 + size:
                question.default = _uint(d, 3, size)
            kind, obj = "other", None
        else:
            kind, obj = "other", None
        if scope:
            scopes.append((kind, obj))
    if formset is None:
        raise HiiError("no form set in the package")
    return formset


def _question(op: int, d: bytes, s) -> Statement:
    prompt, helptext, qid, vid, info, qflags = struct.unpack_from("<HHHHHB", d)
    st = Statement(QUESTIONS[op], s(prompt), s(helptext), question_id=qid, varstore=vid, offset=info)
    rest = d[11:]
    if op in (OP_ONE_OF, OP_NUMERIC):
        st.flags = rest[0]
        st.size = _SIZES[rest[0] & 0x0F]
        st.minimum, st.maximum, st.step = (_uint(rest, 1 + i * st.size, st.size) for i in range(3))
    elif op == OP_CHECKBOX:
        st.flags = rest[0]
        st.size = 1
        st.default = 1 if rest[0] & 0x01 else 0
    elif op == OP_STRING:
        st.minimum, st.maximum, st.flags = rest[0], rest[1], rest[2]
        st.size = rest[1] * 2
    elif op == OP_ORDERED_LIST:
        st.maximum, st.flags = rest[0], rest[1]
    elif op == OP_REF:
        if len(rest) >= 2:
            st.target_form = struct.unpack_from("<H", rest)[0]
        if len(rest) >= 20:
            target = uuid.UUID(bytes_le=rest[4:20])
            st.target_formset = "" if target.int == 0 else str(target).upper()
    return st


def read_module(module_bytes: bytes, module: str = "") -> list[FormSet]:
    """Every form set in a module, with the module's en-US strings."""
    forms = find_form_packages(module_bytes)
    if not forms:
        return []
    strings: dict[int, str] = {}
    for pkg in find_string_packages(module_bytes):
        for sid, text in parse_strings(pkg).items():
            strings.setdefault(sid, text)
    return [parse_forms(pkg, strings, module) for pkg in forms]
