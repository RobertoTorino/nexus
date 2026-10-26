# SPDX-License-Identifier: GPL-3.0-or-later
"""Internet speed test (test 44): page controls."""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from .graph import SPEEDTEST_HISTORY_NAME


class SpeedtestControls(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        note = QLabel("Internet speed test (44): not part of Run all; uses ~1 GB of data. Needs Ookla's "
                      "<a href='https://www.speedtest.net/apps/cli'>speedtest CLI</a> or speedtest-cli.")
        note.setOpenExternalLinks(True)
        note.setWordWrap(True)
        row.addWidget(note, 1)
        graph = QPushButton("Show graph")
        graph.setToolTip("Compare all speed test runs: download/upload, idle vs loaded latency, jitter, packet loss.")
        graph.clicked.connect(self._show_graph)
        row.addWidget(graph)
        calc = QPushButton("Open CSV")
        calc.setToolTip("Open the speed test history CSV in LibreOffice Calc.")
        calc.clicked.connect(self._open_csv)
        row.addWidget(calc)

    def _show_graph(self) -> None:
        from .graph import find_csvs, show_graph
        files = find_csvs(SPEEDTEST_HISTORY_NAME)
        show_graph(self, files[0] if files else None, files,
                   "No speed test history found yet. Run the internet speed test (44) first.")

    def _open_csv(self) -> None:
        from .graph import find_csvs, open_in_calc
        files = find_csvs(SPEEDTEST_HISTORY_NAME)
        open_in_calc(self, files[0] if files else None,
                     "No speed test history found yet. Run the internet speed test (44) first.")
