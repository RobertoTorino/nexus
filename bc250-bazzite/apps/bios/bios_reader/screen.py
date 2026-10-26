# SPDX-License-Identifier: GPL-3.0-or-later
"""The setup screen: a tab row, the items of the open form on the left (prompt and [value]), help on the right and
a key legend at the bottom, in the blue and gray of a classic BIOS setup screen. Read-only: Enter opens a submenu,
Esc goes back, Left/Right switch tabs; nothing can be changed."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QKeyEvent
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QTabBar, QTextBrowser,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .bios import SETUP_FORMSET, Bios, Screens, value_text
from .hii import Form, FormSet, Statement

BAR, SCREEN, PROMPT, VALUE, SUBTITLE = "#1f3e9c", "#c6c6c6", "#0b2a8a", "#0b2a8a", "#10205a"
HIDDEN, LOCKED, SELECTED, WHITE = "#6e6e6e", "#7d7d8c", "#1f3e9c", "#ffffff"
MONO = "'DejaVu Sans Mono', 'Liberation Mono', 'Noto Sans Mono', monospace"
LEGEND = ("→←: Select Screen    ↑↓: Select Item    Enter: Open    Esc: Back    H: Show hidden items    "
          "Read-only: nothing is changed")
UNLINKED, UNLINKED_FORM = "Not linked", 0x10000      # the extra tab; the id is outside the 16-bit form ids
# Text items the BIOS fills in while it runs; the app shows the BIOS's own version data there.
DMI_TEXTS = {"BIOS Vendor": "vendor", "Project Version": "version", "Build Date and Time": "date"}


@dataclass
class Page:
    """One tab: a form of a form set."""
    formset: FormSet
    form: Form
    title: str
    hidden_reason: str = ""


class _Items(QTreeWidget):
    back = pyqtSignal()
    tab_step = pyqtSignal(int)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Backspace):
            self.back.emit()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.tab_step.emit(-1 if key == Qt.Key.Key_Left else 1)
        else:
            super().keyPressEvent(event)


class BiosScreen(QFrame):
    """Shows a Bios. set_bios() loads one; the show-hidden switch decides whether hidden items are listed."""

    show_hidden_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("biosScreen")
        self.setStyleSheet(
            f"#biosScreen {{ background: {SCREEN}; border: 2px solid {BAR}; }}"
            f"QTabBar {{ background: {BAR}; font-family: {MONO}; font-size: 11pt; }}"
            f"QTabBar::tab {{ background: {BAR}; color: {WHITE}; padding: 4px 12px; border: none; }}"
            f"QTabBar::tab:selected {{ background: {SCREEN}; color: {PROMPT}; }}"
            f"QTreeWidget {{ background: {SCREEN}; border: none; font-family: {MONO}; font-size: 10.5pt;"
            f"  color: {PROMPT}; outline: none; }}"
            f"QTreeWidget::item {{ padding: 1px 0; }}"
            f"QTreeWidget::item:selected {{ background: {SELECTED}; color: {WHITE}; }}"
            f"QTextBrowser {{ background: {SCREEN}; border: none; border-left: 2px solid {BAR};"
            f"  font-family: {MONO}; font-size: 10pt; color: {PROMPT}; padding-left: 8px; }}"
            f"#crumbs, #legend {{ font-family: {MONO}; color: {WHITE}; background: {BAR}; padding: 3px 8px; }}")
        self._bios: Bios | None = None
        self._screens: Screens | None = None
        self._pages: list[Page] = []
        self._stack: list[tuple[FormSet, Form]] = []
        self._show_hidden = False

        self.tabs = QTabBar()
        self.tabs.setExpanding(False)
        self.tabs.setDrawBase(False)
        self.tabs.currentChanged.connect(self._open_tab)
        self.crumbs = QLabel()
        self.crumbs.setObjectName("crumbs")
        self.items = _Items()
        self.items.setColumnCount(2)
        self.items.setHeaderHidden(True)
        self.items.setRootIsDecorated(False)
        self.items.setIndentation(0)
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items.header().setStretchLastSection(True)
        self.items.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.items.setColumnWidth(0, 380)
        self.items.currentItemChanged.connect(self._show_help)
        self.items.itemActivated.connect(self._activate)
        self.items.back.connect(self.go_back)
        self.items.tab_step.connect(self._step_tab)
        self.help = QTextBrowser()
        self.help.setOpenLinks(False)
        self.help.setMinimumWidth(260)
        self.legend = QLabel(LEGEND)
        self.legend.setObjectName("legend")
        self.legend.setWordWrap(True)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.items, 3)
        body.addWidget(self.help, 2)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.tabs)
        lay.addWidget(self.crumbs)
        lay.addLayout(body, 1)
        lay.addWidget(self.legend)

    # --- Loading ----------------------------------------------------------------------------------------------

    def set_bios(self, bios: Bios) -> None:
        self._bios = bios
        self._screens = Screens(bios)
        self._rebuild_tabs()

    @property
    def screens(self) -> Screens | None:
        return self._screens

    def set_show_hidden(self, show: bool) -> None:
        if show != self._show_hidden:
            self._show_hidden = show
            self._rebuild_tabs()
            self.show_hidden_changed.emit(show)

    @property
    def show_hidden(self) -> bool:
        return self._show_hidden

    def pages(self) -> list[Page]:
        """The tabs: the links on the main form set's first form (Main, Advanced, ...), then every other form set
        that no link leads to (AMD CBS, network and NVMe pages): the BIOS adds those while it runs."""
        assert self._bios is not None and self._screens is not None
        pages: list[Page] = []
        linked: set[str] = set()
        main = self._bios.formset(SETUP_FORMSET) or (self._bios.formsets[0] if self._bios.formsets else None)
        for fs in self._bios.formsets:
            for form in fs.forms:
                for st in form.statements:
                    if st.kind == "ref" and st.target_formset and st.target_formset != fs.guid:
                        linked.add(st.target_formset)
        if main is not None and main.root is not None:
            for st in main.root.statements:
                target = main.form(st.target_form) if st.kind == "ref" and not st.target_formset else None
                if target is not None:
                    reason = self._screens.form_state(main, target.id)
                    pages.append(Page(main, target, st.prompt or target.title, reason))
        for fs in self._bios.formsets:
            if fs is not main and fs.root is not None and fs.guid not in linked:
                pages.append(Page(fs, fs.root, fs.title or fs.root.title))
        unlinked = self._unlinked_page()
        if unlinked is not None:
            pages.append(unlinked)
        return pages

    def _unlinked_page(self) -> Page | None:
        """A tab that links every form no menu leads to, grouped by form set."""
        assert self._screens is not None
        orphans = self._screens.unlinked_forms()
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

    def _rebuild_tabs(self) -> None:
        index = self.tabs.currentIndex()
        current = self._pages[index].title if self.tabs.count() and 0 <= index < len(self._pages) else ""
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        self._pages = [p for p in self.pages() if self._show_hidden or not p.hidden_reason] if self._bios else []
        for i, page in enumerate(self._pages):
            label = page.title + (" (hidden)" if page.hidden_reason else "")
            self.tabs.addTab(label.replace("&", "&&"))          # "Save & Exit": no keyboard mnemonic
            if page.hidden_reason:
                self.tabs.setTabToolTip(i, f"Hidden in the BIOS: {page.hidden_reason}")
        self.tabs.blockSignals(False)
        index = next((i for i, p in enumerate(self._pages) if p.title == current), 0)
        if self._pages:
            self.tabs.setCurrentIndex(index)
            self._open_tab(index)
        else:
            self._stack = []
            self.items.clear()
            self.crumbs.setText("")
            self.help.setHtml("<p>No setup screens to show.</p>")

    # --- Navigation -------------------------------------------------------------------------------------------

    def _open_tab(self, index: int) -> None:
        if 0 <= index < len(self._pages):
            page = self._pages[index]
            self._stack = [(page.formset, page.form)]
            self._fill()

    def _step_tab(self, step: int) -> None:
        if self._pages:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % len(self._pages))

    def open_form(self, formset: FormSet, form: Form) -> None:
        self._stack.append((formset, form))
        self._fill()

    def go_back(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()
            self._fill()

    def _activate(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        fs, st = data
        if st.kind == "ref" and self._bios is not None:
            target_fs = self._bios.formset(st.target_formset) if st.target_formset else fs
            target = target_fs.form(st.target_form) if target_fs else None
            if target_fs is not None and target is not None:
                self.open_form(target_fs, target)

    def current_form(self) -> tuple[FormSet, Form] | None:
        return self._stack[-1] if self._stack else None

    # --- Items ------------------------------------------------------------------------------------------------

    def _fill(self) -> None:
        assert self._screens is not None
        fs, form = self._stack[-1]
        self.crumbs.setText("  ›  ".join(f.title or f"Form 0x{f.id:X}" for _, f in self._stack))
        self.items.clear()
        form_hidden = self._screens.form_state(fs, form.id)
        first: QTreeWidgetItem | None = None
        for st in form.statements:
            item = self._item(fs, st, form_hidden)
            if item is None:
                continue
            self.items.addTopLevelItem(item)
            if first is None and item.flags() & Qt.ItemFlag.ItemIsSelectable:
                first = item
        if first is not None:
            self.items.setCurrentItem(first)
        else:
            self._show_help(None)
        self.items.setFocus()

    def _item(self, fs: FormSet, st: Statement, form_hidden: str) -> QTreeWidgetItem | None:
        assert self._screens is not None
        state = self._screens.item_state(fs, st)
        if state.hidden and not self._show_hidden:
            return None
        if st.kind == "subtitle" and not st.prompt:
            item = QTreeWidgetItem(["", ""])
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            return item
        prompt, value = st.prompt, ""
        if st.kind == "subtitle":
            item = QTreeWidgetItem([prompt, ""])
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            item.setForeground(0, QBrush(QColor(SUBTITLE)))
            return item
        if st.kind == "text":
            value = self._text_value(st)
        elif st.kind == "ref":
            prompt = "▶ " + st.prompt
        elif st.is_question:
            value = "[" + self._value(fs, st) + "]"
        item = QTreeWidgetItem([prompt, value])
        item.setData(0, Qt.ItemDataRole.UserRole, (fs, st))
        colour = None
        if state.hidden or form_hidden:
            colour = HIDDEN
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)
            item.setFont(1, font)
        elif state.grayed:
            colour = LOCKED
        if colour:
            for col in (0, 1):
                item.setForeground(col, QBrush(QColor(colour)))
        return item

    def _value(self, fs: FormSet, st: Statement) -> str:
        assert self._screens is not None
        if st.kind == "string":
            text = self._screens.string_value(fs, st)
            return text if text is not None else "?"
        if st.kind in ("oneof", "checkbox", "numeric"):
            store = fs.varstores.get(st.varstore)
            if store is not None and store.name == "PlatformLang":       # holds a language code, not a number
                return self._screens.ascii_value(fs, st) or "?"
            return value_text(st, self._screens.raw_value(fs, st))
        return ""

    def _text_value(self, st: Statement) -> str:
        assert self._bios is not None
        field = DMI_TEXTS.get(st.prompt)
        if field:
            if self._bios.source == "dump":
                found = {"vendor": self._bios.vendor, "version": self._bios.version, "date": self._bios.date}[field]
            else:
                found = getattr(self._bios.dmi, field)
            if found:
                return found
        return st.text

    # --- Help -------------------------------------------------------------------------------------------------

    def _show_help(self, item: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None = None) -> None:
        if item is None or not item.data(0, Qt.ItemDataRole.UserRole):
            self.help.setHtml("")
            return
        fs, st = item.data(0, Qt.ItemDataRole.UserRole)
        self.help.setHtml(self.help_html(fs, st))

    def help_html(self, fs: FormSet, st: Statement) -> str:
        assert self._screens is not None and self._bios is not None
        parts = [f"<p>{escape(st.help).replace(chr(10), '<br>')}</p>" if st.help.strip() else ""]
        state = self._screens.item_state(fs, st)
        current = self.current_form()
        form_hidden = self._screens.form_state(current[0], current[1].id) if current else ""
        if form_hidden:
            parts.append(f"<p><b>Hidden in the BIOS:</b> this menu is {escape(form_hidden)}.</p>")
        if state.reason:
            label = "Hidden in the BIOS" if state.hidden else "In the BIOS"
            parts.append(f"<p><b>{label}:</b> {escape(state.reason)}.</p>")
        if st.is_question and st.kind in ("oneof", "checkbox", "numeric"):
            raw = self._screens.raw_value(fs, st)
            default = self._screens.default_value(fs, st)
            rows = [("Value", value_text(st, raw) if raw is not None else self._missing(fs, st))]
            if default is not None:
                rows.append(("Default", value_text(st, default)))
            if st.kind == "numeric":
                rows.append(("Range", f"{st.minimum} … {st.maximum}"))
            rows.append(("Stored at", f"{self._screens.store_label(fs, st)} ({st.size} byte{'s' * (st.size > 1)})"))
            parts.append("<table cellspacing=0 cellpadding=1>" + "".join(
                f"<tr><td><b>{escape(k)}</b>&nbsp;&nbsp;</td><td>{escape(v)}</td></tr>" for k, v in rows) + "</table>")
            if st.kind == "oneof" and st.options:
                opts = "".join(f"<li>{escape(o.text)}{' (default)' if o.default else ''}</li>" for o in st.options)
                parts.append(f"<p><b>Options</b></p><ul style='margin-left:-20px'>{opts}</ul>")
        elif st.kind == "ref":
            parts.append("<p>Enter opens this menu.</p>")
        return "".join(parts)

    def _missing(self, fs: FormSet, st: Statement) -> str:
        store = fs.varstores.get(st.varstore)
        name = store.name if store else "its variable"
        return f"not readable ({name} is not available{' while the system runs' if self._bios and self._bios.source == 'running' else ''})"
