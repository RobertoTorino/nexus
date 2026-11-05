# SPDX-License-Identifier: GPL-3.0-or-later
"""Print results (Settings > Print results): the results card in a preview first (owner, 04-11-2026), then Save…
(a PNG where you choose, as before), Copy (the picture on the clipboard, to paste in a chat or a forum post) or Share.

Share is a menu (owner, 05-11-2026): Send to a phone paired with KDE Connect (kdeconnect-cli; one entry per phone
that is reachable now), Email… (xdg-email opens the mail app with the card attached), and Show in file manager
(Dolphin with the card selected, whose own Share menu has everything KDE offers: Imgur, Telegram, Nextcloud,
Bluetooth). KDE's share framework itself has no Python interface. Share writes the card to SHARE_NAME in the app's
results folder on the Desktop first, overwritten each time."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel, QMenu, QPushButton, QVBoxLayout,
                             QWidget)

SHARE_NAME = "results-card.png"
PREVIEW = QSize(720, 560)       # the card scaled down to fit in this, never up
EMAIL_SUBJECT = "BC-250 Bazzite Test results"
TIMEOUT_S = 10

# argv -> (exit code, output); tests pass a fake
Run = Callable[[list[str]], tuple[int, str]]


def run(argv: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return done.returncode, (done.stdout + done.stderr).strip()


def phones(run_: Run = run) -> list[tuple[str, str]]:
    """The KDE Connect devices reachable now, as (id, name); none without kdeconnect-cli."""
    if shutil.which("kdeconnect-cli") is None:
        return []
    code, out = run_(["kdeconnect-cli", "--list-available", "--id-name-only"])
    if code != 0:
        return []
    found = []
    for line in out.splitlines():
        device, _, name = line.strip().partition(" ")
        if device and name:
            found.append((device, name))
    return found


class ResultsCardDialog(QDialog):
    """The card at a readable size with Save…, Copy, Share and Close. *save* is the window's Save (the file dialog
    and the latest-results preview); *folder* is where Share writes the card."""

    shared = pyqtSignal(str)                    # a line for the status bar

    def __init__(self, card: QPixmap, save: Callable[[QPixmap], None], folder: Path, run_: Run = run,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Results card")
        self.card, self.save_card, self.folder, self.run = card, save, folder, run_
        layout = QVBoxLayout(self)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shown = card if card.width() <= PREVIEW.width() and card.height() <= PREVIEW.height() else card.scaled(
            PREVIEW, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.picture.setPixmap(shown)
        layout.addWidget(self.picture, 1)
        buttons = QDialogButtonBox()
        self.save_button = buttons.addButton("Save…", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setToolTip("Save the card as a PNG where you choose")
        self.copy_button = buttons.addButton("Copy", QDialogButtonBox.ButtonRole.ActionRole)
        self.copy_button.setToolTip("Put the card on the clipboard, to paste it in a chat or a forum post")
        self.share_button = QPushButton("Share")
        self.share_button.setToolTip("Send it to your phone, email it, or share it from the file manager")
        self.share_menu = QMenu(self.share_button)
        self.share_menu.aboutToShow.connect(self.fill_share_menu)
        self.share_menu.triggered.connect(self._share_action)
        self.share_button.setMenu(self.share_menu)
        buttons.addButton(self.share_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.save_button.clicked.connect(self._save)
        self.copy_button.clicked.connect(self.copy)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.save_card(self.card)

    def copy(self) -> None:
        QApplication.clipboard().setPixmap(self.card)
        self.shared.emit("Results card copied: paste it where you want to share it.")

    def fill_share_menu(self) -> None:
        """The menu, read again each time it opens: a phone may have come in reach since."""
        self.share_menu.clear()
        found = phones(self.run)
        for device, name in found:
            self.share_menu.addAction(f"Send to {name} (KDE Connect)").setData(("phone", device, name))
        if not found:
            none = self.share_menu.addAction("Send to phone: no phone in reach (KDE Connect)")
            none.setEnabled(False)
        self.share_menu.addAction("Email…").setData(("email", "", ""))
        self.share_menu.addSeparator()
        self.share_menu.addAction("Show in file manager").setData(("files", "", ""))

    def card_file(self) -> Path:
        """The card written for sharing: SHARE_NAME in the results folder, overwritten each time."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / SHARE_NAME
        if not self.card.save(str(path), "PNG"):
            raise OSError(f"Could not write the card to {path}.")
        return path

    def _share_action(self, action) -> None:
        if action.data():
            self.share(*action.data())

    def share(self, how: str, device: str = "", name: str = "") -> str:
        """Share the card *how* ("phone", "email" or "files"); returns the line it says, or the error."""
        try:
            path = self.card_file()
        except OSError as exc:
            return self._say(str(exc), error=True)
        if how == "phone":
            code, out = self.run(["kdeconnect-cli", "--share", str(path), "-d", device])
            return self._say(f"Results card sent to {name}." if code == 0 else
                             f"KDE Connect could not send the card to {name}: {out or code}", error=code != 0)
        if how == "email":
            code, out = self.run(["xdg-email", "--subject", EMAIL_SUBJECT, "--attach", str(path)])
            return self._say("The mail app opens with the results card attached." if code == 0 else
                             f"No mail app opened: {out or code}. The card is at {path}.", error=code != 0)
        if self.show_in_files(path):
            return self._say(f"The file manager shows the card ({path}): right-click it, then Share.")
        return self._say(f"The file manager did not open. The card is at {path}.", error=True)

    def show_in_files(self, path: Path) -> bool:
        """The file manager with the card selected (org.freedesktop.FileManager1), else its folder opened."""
        from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        message = QDBusMessage.createMethodCall("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1",
                                                "org.freedesktop.FileManager1", "ShowItems")
        message.setArguments([[QUrl.fromLocalFile(str(path)).toString()], ""])
        reply = QDBusConnection.sessionBus().call(message)
        if reply.type() != QDBusMessage.MessageType.ErrorMessage:
            return True
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def _say(self, text: str, error: bool = False) -> str:
        if error:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Share", text)
        self.shared.emit(text)
        return text
