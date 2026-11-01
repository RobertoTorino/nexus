# SPDX-License-Identifier: GPL-3.0-or-later
"""The setup screens as the window lists them, Qt-free: the pages (the BIOS's tabs: Main, Advanced, ..., then the
pages other modules add, then the menus no link leads to), a form's entries (subtitles, settings with their value,
links to other menus) and the whole of what is known about one setting (its help, why it is hidden, its value and
where that comes from, its default, its options and where it is stored). What the BC250 suite's BIOS Reader shows
in its setup screen, for the portable window."""

from __future__ import annotations

from dataclasses import dataclass

from .bios import DEFAULT, DEVICE, FILE, SETUP_FORMSET, Identity, Screens, value_text
from .hii import Form, FormSet, Statement

UNLINKED, UNLINKED_FORM = "Not linked", 0x10000      # the extra page; the id is outside the 16-bit form ids
# Text items the BIOS fills in while it runs: the app shows the BIOS's own identity there.
IDENTITY_TEXTS = {"BIOS Vendor": "vendor", "Project Version": "version", "BIOS Version": "version",
                  "Build Date and Time": "date", "Build Date": "date"}
SOURCES = {DEVICE: "this device", FILE: "the file", DEFAULT: "the default"}
TITLE = 48                      # characters of a page's title
# Pages a BIOS holds for a moment that may never come, said beside their title (owner, 01-11-2026: the PCI page read
# as an error on the device): by the module they come from.
NOTES = {"PciOutOfResourceSetupPage": "AMI's page for a boot that runs out of PCI resources: the BIOS shows it only "
                                      "then, and every BIOS file holds it; it is not an error on this device"}


@dataclass
class Page:
    """One tab: a form of a form set."""
    formset: FormSet
    form: Form
    title: str
    hidden_reason: str = ""


@dataclass
class Entry:
    """One line of a form: a subtitle (no statement), a setting, a text or a link to another menu."""
    prompt: str
    value: str = ""
    statement: Statement | None = None
    hidden: bool = False                # the BIOS does not show it, or its menu
    grayed: bool = False

    @property
    def link(self) -> bool:
        return self.statement is not None and self.statement.kind == "ref"


def pages(screens: Screens, show_hidden: bool = False) -> list[Page]:
    """The tabs: the links on the main form set's first form (Main, Advanced, ...), then every other form set that no
    link leads to (AMD CBS, network pages): the BIOS adds those while it runs; the menus no link leads to last. The
    hidden ones only with *show_hidden*."""
    bios = screens.bios
    out: list[Page] = []
    linked: set[str] = set()
    main = bios.formset(SETUP_FORMSET) or (bios.formsets[0] if bios.formsets else None)
    for fs in bios.formsets:
        for form in fs.forms:
            for st in form.statements:
                if st.kind == "ref" and st.target_formset and st.target_formset != fs.guid:
                    linked.add(st.target_formset)
    if main is not None and main.root is not None:
        for st in main.root.statements:
            target = main.form(st.target_form) if st.kind == "ref" and not st.target_formset else None
            if target is not None:
                out.append(Page(main, target, st.prompt or target.title, screens.form_state(main, target.id)))
    for fs in bios.formsets:
        if fs is not main and fs.root is not None and fs.guid not in linked:
            out.append(Page(fs, fs.root, short(fs.title or fs.root.title)))
    if (unlinked := unlinked_page(screens)) is not None:
        out.append(unlinked)
    return [page for page in out if show_hidden or not page.hidden_reason]


def short(title: str, most: int = TITLE) -> str:
    """A title's first line, cut at a word to *most* characters: AMD's overclocking module is titled with its whole
    warning ("WARNING - DAMAGE CAUSED BY USE OF YOUR AMD PROCESSOR ...")."""
    line = title.strip().split("\n", 1)[0].strip()
    if len(line) <= most:
        return line
    return line[:most].rsplit(" ", 1)[0].rstrip(" ,.-") + " …"


def unlinked_page(screens: Screens) -> Page | None:
    """A page that links every form no menu leads to, grouped by form set."""
    orphans = screens.unlinked_forms()
    if not orphans:
        return None
    form = Form(UNLINKED_FORM, UNLINKED)
    group = None
    for fs, target in orphans:
        if fs is not group:
            group = fs
            form.statements.append(Statement("subtitle", fs.title or fs.module))
        form.statements.append(Statement("ref", target.title or f"Form 0x{target.id:X}",
                                         target_form=target.id, target_formset=fs.guid))
    return Page(orphans[0][0], form, UNLINKED, "these menus are not linked from any menu")


def form_hidden(screens: Screens, fs: FormSet, form: Form) -> str:
    return "" if form.id == UNLINKED_FORM else screens.form_state(fs, form.id)


def entries(screens: Screens, fs: FormSet, form: Form, show_hidden: bool = False,
            identity: Identity | None = None) -> list[Entry]:
    """The lines of *form*, the hidden ones only with *show_hidden*; empty subtitles (spacers) left out."""
    menu_hidden = bool(form_hidden(screens, fs, form))
    out: list[Entry] = []
    for st in form.statements:
        state = screens.item_state(fs, st)
        if state.hidden and not show_hidden:
            continue
        if st.kind == "subtitle":
            if st.prompt.strip():
                out.append(Entry(st.prompt))
            continue
        prompt = st.prompt
        if not prompt.strip() and st.kind == "ref":    # a link the BIOS names while it runs: named by its menu
            opened = target(screens, fs, st)
            prompt = short(opened[1].title) if opened is not None else ""
        if not prompt.strip():
            continue
        value = ""
        if st.kind == "text":
            value = text_value(st, identity or screens.bios.identity)
        elif st.is_question:
            value = setting_value(screens, fs, st)
        out.append(Entry(prompt, value, st, state.hidden or menu_hidden, state.grayed))
    return out


def note(fs: FormSet) -> str:
    """What a page of *fs* is, when it is one the BIOS shows only in a rare case ("" for the others)."""
    return NOTES.get(fs.module, "")


def text_value(st: Statement, identity: Identity) -> str:
    field = IDENTITY_TEXTS.get(st.prompt)
    found = getattr(identity, field) if field else ""
    return found or st.text


def setting_value(screens: Screens, fs: FormSet, st: Statement) -> str:
    if st.kind == "string":
        text = screens.string_value(fs, st)
        return text if text is not None else "?"
    if st.kind in ("oneof", "checkbox", "numeric"):
        store = fs.varstores.get(st.varstore)
        if store is not None and store.name == "PlatformLang":         # holds a language code, not a number
            return screens.ascii_value(fs, st) or "?"
        return value_text(st, screens.raw_value(fs, st))
    return ""


def target(screens: Screens, fs: FormSet, st: Statement) -> tuple[FormSet, Form] | None:
    """The menu a link opens."""
    target_fs = screens.bios.formset(st.target_formset) if st.target_formset else fs
    form = target_fs.form(st.target_form) if target_fs is not None else None
    return (target_fs, form) if target_fs is not None and form is not None else None


def detail(screens: Screens, fs: FormSet, form: Form, st: Statement) -> str:
    """Everything about one line, as plain text: the information icon shows it."""
    parts = [st.help.strip()] if st.help.strip() else []
    state = screens.item_state(fs, st)
    if hidden := form_hidden(screens, fs, form):
        parts.append(f"Hidden in the BIOS, with its menu: {hidden}.")
    if state.reason:
        parts.append(f"{'Hidden in the BIOS' if state.hidden else 'In the BIOS'}: {state.reason}.")
    if st.is_question and st.kind in ("oneof", "checkbox", "numeric"):
        raw = screens.raw_value(fs, st)
        default = screens.default_value(fs, st)
        source = screens.source(fs, st)
        rows = [f"Value: {value_text(st, raw)} (from {SOURCES[source]})" if raw is not None and source else
                f"Value: not known ({_missing(fs, st)})"]
        if default is not None:
            rows.append(f"Default: {value_text(st, default)}")
        if st.kind == "numeric":
            rows.append(f"Range: {st.minimum} … {st.maximum}")
        rows.append(f"Stored at: {screens.store_label(fs, st)} ({st.size} byte{'s' * (st.size > 1)})")
        parts.append("\n".join(rows))
        if st.kind == "oneof" and st.options:
            parts.append("Options:\n" + "\n".join(f"  {o.text}{' (default)' if o.default else ''}"
                                                   for o in st.options))
    elif st.kind == "ref":
        parts.append("The A button opens this menu.")
    return "\n\n".join(parts)


def summary(screens: Screens, fs: FormSet, form: Form, st: Statement) -> str:
    """The line under the list: the setting's value with where it comes from, and its default."""
    if not (st.is_question and st.kind in ("oneof", "checkbox", "numeric")):
        return st.help.strip().split("\n", 1)[0]
    raw = screens.raw_value(fs, st)
    default = screens.default_value(fs, st)
    source = screens.source(fs, st)
    text = (f"{value_text(st, raw)}, from {SOURCES[source]}" if raw is not None and source else
            "Its value is not known")
    if default is not None and source != DEFAULT:
        text += f"  ·  default {value_text(st, default)}"
    reason = screens.item_state(fs, st).reason or form_hidden(screens, fs, form)
    return text + (f"  ·  {reason}" if reason else "")


def _missing(fs: FormSet, st: Statement) -> str:
    store = fs.varstores.get(st.varstore)
    return f"the file has no {store.name}" if store else "no variable"
