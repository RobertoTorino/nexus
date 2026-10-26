# SPDX-License-Identifier: GPL-3.0-or-later
"""Disk speed test (test 43): settings and page controls."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

DISK_GLOB = "bc250-disk-*.csv"


class DiskSettings(QObject):
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.write = False
        self.write_gib = 8

    def set(self, **kw) -> None:
        for k, v in kw.items():
            setattr(self, k, v)
        self.changed.emit()


class DiskControls(QWidget):
    def __init__(self, settings: DiskSettings, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings = settings
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        self.write = QCheckBox("Disk speed test (43): also test writes")
        self.write.setToolTip("Writes a temporary file to /var/tmp (removed afterwards) to measure write speed and "
                              "find where the SLC cache runs out. Without it the test only reads.")
        self.write.toggled.connect(lambda v: settings.set(write=v))
        row.addWidget(self.write)
        row.addWidget(QLabel("Write size (GiB):"))
        self.size = QSpinBox()
        self.size.setRange(1, 256)
        self.size.setToolTip("How much to write. The SLC cache is found only if it is smaller than this: "
                             "a few GiB on cheap/QLC drives, tens of GiB on large TLC drives. Needs this much + 5 GiB free.")
        self.size.valueChanged.connect(lambda v: settings.set(write_gib=v))
        row.addWidget(self.size)
        row.addStretch(1)

        graph = QPushButton("Show graph")
        graph.setToolTip("Plot the write speed and drive temperature of the latest disk write test.")
        graph.clicked.connect(self._show_graph)
        row.addWidget(graph)
        calc = QPushButton("Open CSV")
        calc.setToolTip("Open the CSV of the latest disk write test in LibreOffice Calc.")
        calc.clicked.connect(self._open_csv)
        row.addWidget(calc)

        settings.changed.connect(self._sync)
        self._sync()

    def _show_graph(self) -> None:
        from .graph import find_csvs, show_graph
        files = find_csvs(DISK_GLOB)
        show_graph(self, files[0] if files else None, files,
                   "No disk write test CSV found yet. Run the disk speed test (43) with writes enabled first.")

    def _open_csv(self) -> None:
        from .graph import find_csvs, open_in_calc
        files = find_csvs(DISK_GLOB)
        open_in_calc(self, files[0] if files else None,
                     "No disk write test CSV found yet. Run the disk speed test (43) with writes enabled first.")

    def _sync(self) -> None:
        for w in (self.write, self.size):
            w.blockSignals(True)
        self.write.setChecked(self.settings.write)
        self.size.setValue(self.settings.write_gib)
        self.size.setEnabled(self.settings.write)
        for w in (self.write, self.size):
            w.blockSignals(False)
