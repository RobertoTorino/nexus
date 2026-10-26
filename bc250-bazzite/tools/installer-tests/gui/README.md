<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# BC-250 Installer Tests

![BC-250 Installer Tests icon](images/bc250-installer-test-gui-128.png)

A local PyQt6 GUI for running the shell tests in `bc250-bazzite/tools/installer-tests`. Tests run one at a time, with their live
output shown in the window. Every `*.sh` test is listed except `shims.sh`, which is a helper.

Install the GUI dependency and start it from the suite checkout:

```bash
python3 -m pip install -r bc250-bazzite/tools/installer-tests/gui/requirements.txt
bc250-bazzite/tools/installer-tests/gui/run.sh
```

To add a launcher, app menu entry and Desktop icon for this checkout, run
`bc250-bazzite/tools/installer-tests/gui/install.sh`. Use `--uninstall` to remove them; the checkout stays in place.
Use `--no-desktop-shortcut` to install only the launcher and app menu entry. Moving the checkout requires
running the installer again.

`run.sh` prefers the suite's local or shared virtual environment; set `PYTHON` to use another interpreter.
The tests need the same local prerequisites as their shell versions, including `bash` and `fakeroot`. They use fixed
temporary directories under `/tmp`; do not run the same installer test concurrently in another process.

The GUI is a development helper. It does not install or change any suite apps.
