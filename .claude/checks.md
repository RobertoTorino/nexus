<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Checks before handing work over

The long form of the root [CLAUDE.md](../CLAUDE.md)'s Checks: every check as CI runs it, from the repository root.
The same checks as CI (`.github/workflows/ci-nexus.yml` and `ci.yml`). `tools/ci-local.sh` runs them as CI does
(Python 3.12, each job with only its own requirements, in a container), which `./test.sh` in the full venv on a
newer Python cannot show; run it before saying work is ready. The BC250 suite's checks (its tests, installer tests,
`tools/ci-local.sh`) run on Bazzite and in CI. On Windows, `tools/ci-local.sh` runs in podman's machine (Fedora in
WSL) as its user, not root (the installers refuse root):
`podman machine ssh "su - user -c 'cd /mnt/c/Projects/nexus && bash tools/ci-local.sh'"`. Run it from PowerShell, not
Git Bash: podman points ssh's known-hosts file at `NUL`, which Git Bash writes as a real file named NUL in the current
folder (the root .gitignore leaves it out of `git add`); remove one with `Remove-Item -LiteralPath
'\\?\C:\Projects\nexus\NUL'`.

```bash
tools/ci-local.sh                                   # every job of the Linux suites and Nexus workflows (podman)
tools/pre-push.sh                                   # CI's quick checks against origin/main (git's pre-push hook, tools/git-setup.sh once per checkout)
./test.sh                                           # every test suite of this system, offscreen
python3 tools/check_versions.py                     # versions = VERSION, every suite
python3 bc250-bazzite/tools/check_manifest.py --base origin/main  # the suite's apps.toml rules, the bump since the last portal release
python3 bazzite-console/tools/check_manifest.py --base origin/main  # the suite's apps.toml rules and portal bump
python3 tools/check_changelogs.py --base origin/main  # no CHANGELOG lost an entry since the last push
find bc250-bazzite bazzite-console tools test.sh -name '*.sh' -print0 | xargs -0 -n1 bash -n
find bc250-bazzite bazzite-console tools test.sh -name '*.sh' -print0 | xargs -0 shellcheck -x -S error
shellcheck -x -S warning bc250-bazzite/portal/install.sh bc250-bazzite/apps/check/install.sh \
  bazzite-console/portal/install.sh bazzite-console/apps/bazzite/install.sh bazzite-console/tools/check-release.sh \
  tools/*.sh bc250-bazzite/tools/*.sh bc250-bazzite/tools/installer-tests/*.sh \
  bazzite-console/tools/*.sh bazzite-console/tools/installer-tests/*.sh test.sh bc250-bazzite/install.sh tools/hooks/pre-push
S=bc250-bazzite   # the shellcheck -S warning lists of ci.yml, every app's scripts under $S/apps/<name>/
shellcheck -S warning $S/apps/cores/bc250-cores-bisect.sh $S/apps/cores/bc250-cores-unlock.sh \
  $S/apps/cores/install.sh $S/apps/cores/packaging/bazzite/*.sh
shellcheck -S warning $S/apps/oc/bc250-gpu-oc-bisect.sh $S/apps/oc/install.sh
shellcheck -S warning $S/apps/acpi/bc250-acpi-override.sh $S/apps/acpi/install.sh \
  $S/apps/overlay/install.sh $S/apps/bios/install.sh $S/apps/vram/install.sh $S/apps/fan/install.sh \
  $S/apps/cec/install.sh $S/apps/sftp/install.sh $S/apps/ips35/install.sh $S/apps/hdcam/install.sh $S/apps/hdcontrol/install.sh \
  $S/apps/consoles/install.sh $S/apps/clb/install.sh dev/*/*.sh $S/tools/check-release.sh
shellcheck -S warning $S/apps/ace/bc250-ace-queues.sh $S/apps/ace/bc250-ace-queues-run \
  $S/apps/ace/install.sh $S/apps/ace/mesa/build-in-container.sh
shellcheck -S warning $S/apps/mesh/bc250-mesh-shaders.sh $S/apps/mesh/bc250-mesh-shaders-run \
  $S/apps/mesh/install.sh $S/apps/mesh/mesa/build-in-container.sh
shellcheck -S warning $S/apps/shadps4/install.sh $S/apps/shadps4/bc250-shadps4-run
shellcheck -S warning $S/apps/rpcs3/install.sh $S/apps/rpcs3/bc250-rpcs3-run
shellcheck -S warning $S/apps/ppsspp/install.sh $S/apps/ppsspp/bc250-ppsspp-run \
  $S/apps/pcsx2/install.sh $S/apps/pcsx2/bc250-pcsx2-run $S/apps/vita3k/install.sh \
  $S/apps/vita3k/bc250-vita3k-run
shellcheck -S warning $S/apps/xenia/install.sh $S/apps/xenia/bc250-xenia-run
shellcheck -S warning $S/apps/decky/install.sh $S/apps/ncgui/install.sh \
  $S/apps/datstation/install.sh
for t in bc250-bazzite/tools/installer-tests/*.sh bazzite-console/tools/installer-tests/*.sh; do
  [ "${t##*/}" = shims.sh ] || bash "$t"
done
mkdocs build --strict -f bc250-bazzite/mkdocs.yml   # the suite's wiki, from the venv
mkdocs build --strict -f bazzite-console/mkdocs.yml # the Bazzite Console Suite's wiki
mkdocs build --strict -f nexus/mkdocs.yml          # the Nexus page
mkdocs build --strict -f windows-portable/mkdocs.yml   # the Windows Portable Suite's wiki
```

On Windows, for the Windows Portable Suite (its own CI, `ci-windows-portable.yml`), from PowerShell at the repo root:

```powershell
.venv-windows\Scripts\python.exe tools\check_versions.py --suite windows-portable
.venv-windows\Scripts\python.exe windows-portable\tools\check_manifest.py --base origin/main
Get-ChildItem windows-portable\tools\installer-tests\*.ps1 | ForEach-Object { powershell -NoProfile -ExecutionPolicy Bypass -File $_.FullName }
.venv-windows\Scripts\python.exe windows-portable\tools\build_release.py wp-test-v<VERSION> <folder>   # needs pyinstaller and pillow in the venv
powershell -NoProfile -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\test.ps1 -Release <folder>\wp-test-v<VERSION>.zip
```

Every app (and every `portal/apps.toml` entry) has an installer test, `<suite>/tools/installer-tests/<name>.sh`
(`<name>.ps1` in a Windows suite), and CI runs every one it finds in that folder (the BC250 suite's in one job, each
in a group of the log; a Windows suite's in a job of its own, the `installers` matrix); a new app adds its test and
nothing to a workflow (each suite's `tools/tests/test_installer_tests.py` checks it). Nexus Installer Tests lists the scripts in that folder by itself. The installer tests need `fakeroot` (Linux). Every tool, as a prerequisite or optional, is in the Nexus page's [The development machine](../nexus/docs/machine.md). On Bazzite, `brew install shellcheck fakeroot node` (Node.js runs the design panel's script in
`tools/tests/test_design_panel.py`; the test skips without it); brew's folder
`/home/linuxbrew/.linuxbrew/bin` may need adding to PATH in a non-interactive shell. CI also checks the layout rules of the root CLAUDE.md: no CRLF in the index, every
`.sh` is 100755, every former repo folder has its four files, workflows only in the root `.github/`. The pytest
matrices of the CI workflows cover every folder with `tests/` (`tools/tests/test_layout.py` checks it): `core`,
`tools` and each `dev/<name>` listed in `ci-nexus.yml`; each suite's `portal`, `tools` and `apps/<name>` read from
the suite's folders by the plan job of its CI (`tools/ci_matrix.py --suite <name> pytest`, and `installers` for
a Windows suite's job per app), so a new app needs no workflow edit (stage 2 of the release redesign, 04-11-2026). CI results
can be read without `gh` through the public API:
`curl -s https://api.github.com/repos/RobertoTorino/nexus/actions/runs?per_page=3`.
