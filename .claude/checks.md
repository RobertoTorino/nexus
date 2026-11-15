<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Checks before handing work over

The long form of the root [CLAUDE.md](../CLAUDE.md)'s Checks: every check as CI runs it, from the repository root.
The same checks as CI (`.github/workflows/ci-nexus.yml`). `tools/ci-local.sh` runs them as CI does (Python 3.12,
each job with only its own requirements, in a container), which `./test.sh` in the full venv on a newer Python cannot
show; run it before saying work is ready. The BC250 Bazzite Suite is a repository of its own with its own checks
(its `CLAUDE.md`). On Windows, `tools/ci-local.sh` runs in podman's machine (Fedora in WSL) as its user, not root:
`podman machine ssh "su - user -c 'cd /mnt/c/Projects/nexus && bash tools/ci-local.sh'"`. Run it from PowerShell, not
Git Bash: podman points ssh's known-hosts file at `NUL`, which Git Bash writes as a real file named NUL in the current
folder (the root .gitignore leaves it out of `git add`); remove one with `Remove-Item -LiteralPath
'\\?\C:\Projects\nexus\NUL'`.

```bash
tools/ci-local.sh                                   # ci-nexus.yml's jobs, as GitHub runs them (podman); --all: every one
tools/pre-push.sh                                   # CI's quick checks against origin/main (git's pre-push hook, tools/git-setup.sh once per checkout)
./test.sh                                           # every test suite of this system, offscreen
python3 tools/check_versions.py --nexus             # versions = VERSION: core and dev/
python3 tools/check_prose.py --top 20               # the text that reads worst (not a CI check); --base REF fails when a file got worse
python3 tools/features.py --check                   # every app in nexus/features.toml, the Nexus page's Apps and features current
python3 tools/make_design.py --check                # DESIGN.md and its samples current
python3 tools/make_icons.py --check                 # ICONS.md current
find tools dev test.sh -name '*.sh' -print0 | xargs -0 -n1 bash -n
find tools dev test.sh -name '*.sh' -print0 | xargs -0 shellcheck -x -S error
shellcheck -x -S warning tools/*.sh test.sh tools/hooks/pre-push
shellcheck -S warning dev/*/*.sh
mkdocs build --strict -f nexus/mkdocs.yml          # the Nexus page
mkdocs build --strict -f windows-portable/mkdocs.yml   # the Windows Portable Suite's wiki, when the suite is cloned here
```

On Windows, for the Windows Portable Suite (a repository of its own, cloned into this checkout as
`windows-portable/`; its CI is its own `ci.yml`), from PowerShell at the root of this checkout; `--base origin/main`
is then the suite's `origin/main`:

```powershell
.venv-windows\Scripts\python.exe tools\check_versions.py --suite windows-portable
.venv-windows\Scripts\python.exe windows-portable\tools\check_manifest.py --base origin/main
Get-ChildItem windows-portable\tools\installer-tests\*.ps1 | ForEach-Object { powershell -NoProfile -ExecutionPolicy Bypass -File $_.FullName }
.venv-windows\Scripts\python.exe windows-portable\tools\build_release.py wp-test-v<VERSION> <folder>   # needs pyinstaller and pillow in the venv
powershell -NoProfile -ExecutionPolicy Bypass -File windows-portable\tools\installer-tests\test.ps1 -Release <folder>\wp-test-v<VERSION>.zip
```

A suite's apps each have an installer test, `<suite>/tools/installer-tests/<name>.sh` (`<name>.ps1` in a Windows
suite), run by the suite's own CI; Nexus Installer Tests lists the scripts in that folder by itself. The installer
tests need `fakeroot` (Linux). Every tool, as a prerequisite or optional, is in the Nexus page's [The development
machine](../nexus/docs/machine.md). On Bazzite, `brew install shellcheck fakeroot node` (Node.js runs the design
panel's script in `tools/tests/test_design_panel.py`; the test skips without it); brew's folder
`/home/linuxbrew/.linuxbrew/bin` may need adding to PATH in a non-interactive shell. CI also checks the layout rules
of the root CLAUDE.md: no CRLF in the index, every `.sh` is 100755, every former repo folder has its four files,
workflows only in the root `.github/`. The pytest matrix of `ci-nexus.yml` covers every folder with `tests/`:
`core`, `tools` and each `dev/<name>` (`tools/tests/test_layout.py` checks it). CI results can be read without `gh`
through the public API: `curl -s https://api.github.com/repos/RobertoTorino/nexus/actions/runs?per_page=3`.
