# SPDX-License-Identifier: GPL-3.0-or-later
"""What the window's pages share: the explanation of a page behind a round "i" instead of a paragraph on top of it
(owner, 01-11-2026: a window never carries long lines of explanation; where a line of hint text would take the
room, an info symbol opens the text), and a step's log, which shows in Commands with the command output (owner,
01-11-2026: one output tab instead of a Logs tab that was mostly empty)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QHBoxLayout, QWidget

from bc250_core.widgets import InfoButton, Terminal, hint_label


def info_row(short: str, text: str) -> QHBoxLayout:
    """One short line on the left and the "i" with the whole explanation on the right, as a page's first row."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    line = hint_label(short)
    line.setWordWrap(False)
    row.addWidget(line, 1)
    row.addWidget(InfoButton(text, "What this tab does"))
    return row


class StepLog(Terminal):
    """A step's log (what Apply, Pin, Bump, Retract or a board test wrote), kept here as a page's own record and
    relayed to the Commands tab as it is written: set_text() for a step that writes its log at once, appendPlainText()
    for lines that come while something runs. *relay* is the window's: it shows the text in Commands and opens that
    tab when *opens* and the page is the one open."""

    def __init__(self, page: QWidget, name: str, relay: Callable[[QWidget, str, str, bool], None], opens: bool = True):
        super().__init__()
        self.page, self.name, self.relay, self.opens = page, name, relay, opens

    def set_text(self, text: str) -> None:
        super().set_text(text)
        self.relay(self.page, self.name, text, self.opens)

    def appendPlainText(self, text: str) -> None:  # noqa: N802 (Qt's name)
        super().appendPlainText(text)
        self.relay(self.page, self.name, text, self.opens)
