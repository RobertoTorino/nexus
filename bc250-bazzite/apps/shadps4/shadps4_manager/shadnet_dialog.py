# SPDX-License-Identifier: GPL-3.0-or-later
"""The shadNet account window: which of shadPS4's users signs in, with which account on which server; creating an
account and trying a sign-in (off the GUI thread); saving it all in shadPS4's own files, from where shadPS4 signs in
when a game starts."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QWidget)

from bc250_core import window_title
from bc250_core.updates import UpdateChecker
from bc250_core.widgets import hint_label

from . import shadnet, style, userdata

SHADNET_PAGE = "https://github.com/shadps4-emu/shadNet"


class ShadNetDialog(QDialog):
    def __init__(self, shad_home: Path, config: dict, users: list[userdata.User], parent: QWidget | None = None,
                 connect: shadnet.Connect = shadnet._connect, running=userdata.shadps4_running):
        """*connect*: opens the connection to the server, *running*: whether shadPS4 runs (tests pass fakes)."""
        super().__init__(parent)
        self.setWindowTitle(window_title("shadNet"))
        self.setMinimumWidth(520)
        self.shad_home = shad_home
        self.users = users
        self.connect = connect
        self.running = running
        self.worker = UpdateChecker(self)
        self.worker.finished.connect(self._done)

        self.use = QCheckBox("Sign in to shadNet when a game starts")
        self.server = QLineEdit(userdata.shadnet_server(config))
        self.server.setPlaceholderText(shadnet.DEFAULT_SERVER)
        self.user = QComboBox()
        for n, user in enumerate(users, start=1):
            self.user.addItem(f"{user.name} (player {n})", user.user_id)
        self.npid = QLineEdit()
        self.npid.setMaxLength(16)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.email = QLineEdit()
        self.key = QLineEdit()
        self.key.setPlaceholderText("only when the server asks for one")
        form = QFormLayout()
        form.addRow("Server", self.server)
        form.addRow("shadPS4 user", self.user)
        form.addRow("shadNet name", self.npid)
        form.addRow("Password", self.password)
        form.addRow("Email", self.email)
        form.addRow("Registration key", self.key)

        self.create_button = QPushButton("Create account")
        self.create_button.setToolTip("Create this account on the server (needs the email address)")
        self.create_button.clicked.connect(self.on_create)
        self.try_button = QPushButton("Try sign-in")
        self.try_button.setToolTip("Sign in once to the server with this name and password, and out again")
        self.try_button.clicked.connect(self.on_try)
        self.save_button = style.primary_button("Save", "Keep these settings in shadPS4's own files")
        self.save_button.clicked.connect(self.on_save)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        for button in (self.create_button, self.try_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(hint_label(
            "shadNet is shadPS4's online service: online trophies, friends and online play in the games it "
            "supports. shadPS4 signs in by itself when a game starts. No account yet? Fill in a name, a password "
            f"and your email, and press Create account. {style.link(self, SHADNET_PAGE, 'About shadNet')}"))
        lay.addWidget(self.use)
        lay.addLayout(form)
        lay.addWidget(hint_label(
            "shadPS4 keeps the password as it is in its users.json, and shadNet sends it over the network "
            "unencrypted: use a password you use nowhere else."))
        lay.addWidget(self.result_label)
        lay.addLayout(buttons)
        style.apply(self)

        self.user.currentIndexChanged.connect(self._show_user)
        self.use.toggled.connect(self._update_buttons)
        for field in (self.server, self.npid, self.password, self.email):
            field.textChanged.connect(self._update_buttons)
        # The user that has an account, else player 1.
        start = next((n for n, u in enumerate(users) if u.npid), 0)
        self.user.setCurrentIndex(start)
        self._show_user()

    def chosen(self) -> userdata.User | None:
        return self.users[self.user.currentIndex()] if self.users else None

    def _show_user(self) -> None:
        user = self.chosen()
        self.use.setChecked(bool(user and user.shadnet))
        self.npid.setText(user.npid if user else "")
        self.password.setText(user.password if user else "")
        self.email.setText(user.email if user else "")
        self._update_buttons()

    def _account(self) -> tuple[shadnet.Server, str, str]:
        """The server, name and password, checked; ShadNetError with what is wrong."""
        server = shadnet.parse_server(self.server.text() or shadnet.DEFAULT_SERVER)
        npid = self.npid.text().strip()
        if why := shadnet.check_npid(npid):
            raise shadnet.ShadNetError(why)
        if not self.password.text():
            raise shadnet.ShadNetError("Fill in the password.")
        return server, npid, self.password.text()

    def _update_buttons(self) -> None:
        idle = not self.worker.running
        account = bool(self.npid.text().strip() and self.password.text())
        self.create_button.setEnabled(idle and account and bool(self.email.text().strip()))
        self.try_button.setEnabled(idle and account)
        self.save_button.setEnabled(idle and bool(self.users) and (account or not self.use.isChecked()))

    def _say(self, text: str, ok: bool = True) -> None:
        self.result_label.setText(text)
        self.result_label.setStyleSheet("" if ok else "color:#c62828;")

    def _start(self, text: str, job) -> None:
        if self.worker.start(job):
            self._say(text)
            self._update_buttons()

    def _done(self, result: tuple[bool, str]) -> None:
        ok, message = result
        self._say(message, ok)
        self._update_buttons()

    def on_create(self) -> None:
        try:
            server, npid, password = self._account()
        except shadnet.ShadNetError as error:
            self._say(str(error), False)
            return
        email, key, connect = self.email.text().strip(), self.key.text().strip(), self.connect

        def job() -> tuple[bool, str]:
            try:
                shadnet.create_account(server, npid, password, email, key, connect)
            except shadnet.ShadNetError as error:
                return False, str(error)
            return True, f"The account {npid} was created on {server}. Press Save to use it."
        self._start(f"Creating {npid} on {server}…", job)

    def on_try(self) -> None:
        try:
            server, npid, password = self._account()
        except shadnet.ShadNetError as error:
            self._say(str(error), False)
            return
        connect = self.connect

        def job() -> tuple[bool, str]:
            try:
                shadnet.try_sign_in(server, npid, password, connect)
            except shadnet.ShadNetError as error:
                return False, str(error)
            return True, f"{npid} signed in to {server}."
        self._start(f"Signing in to {server}…", job)

    def on_save(self) -> None:
        user = self.chosen()
        if user is None:
            return
        on = self.use.isChecked()
        try:
            server = shadnet.parse_server(self.server.text() or shadnet.DEFAULT_SERVER)
            if on and (why := shadnet.check_npid(self.npid.text().strip())):
                raise shadnet.ShadNetError(why)
        except shadnet.ShadNetError as error:
            self._say(str(error), False)
            return
        if self.running():
            self._say("shadPS4 is running: close it first, as it writes its own settings back when it ends.", False)
            return
        try:
            userdata.save_shadnet(self.shad_home, user.user_id, self.npid.text().strip(), self.password.text(),
                                  self.email.text().strip(), on, str(server))
        except userdata.UserDataError as error:
            self._say(str(error), False)
            return
        self.accept()

    def done(self, code: int) -> None:
        self.worker.stop()
        super().done(code)
