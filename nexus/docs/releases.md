<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Releases

**Nexus Releases** (`dev/releases/` in the repository) is the release front end of every suite: a window that makes
the file edits of a release for you, the versions, the CHANGELOG entries, the pins and the portal bump, and runs a
suite's board checks. It commits, tags and pushes only when you press its git buttons: after each step it shows the
git commands to run. It edits the checkout it lives in, so it is not in a portal's releases and has none of its own.
When the checkout holds several suites, the first column lists them, each portal with its icon and the tag of its
version, and the ticked one is the suite the steps, the pins and the board tests work on: click a row to release
that suite instead (the window opens on the one ticked last); the git buttons, the wikis and GitHub are the repository's whatever the suite. Each suite's tags start
with its prefix: the Windows Portable Suite's are `wp-test-v0.1.0` and `wp-portal-v0.1.0`.

What a release of the BC250 Bazzite Suite involves, step by step, is in its wiki:
[apps.toml and releases](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#appstoml-and-releases).

## Start it

From the repository's root, with the checkout's venv for the system (`.venv-linux` or `.venv-windows`, see
[Development](https://robertotorino.github.io/nexus/bc250-bazzite-suite/development/)). Nothing is copied when you install it: the menu entry always starts the app of the
checkout you installed it from. After moving the checkout, install it again.

On Linux:

```bash
tools/release.sh                                # open it (dev/releases/run.sh)
tools/release.sh --list                         # the same overview in the terminal, with the system python3
dev/releases/install.sh                         # app menu entry and Desktop icon
dev/releases/install.sh --no-desktop-shortcut   # app menu entry only
dev/releases/install.sh --uninstall             # remove them; the checkout stays
```

On Windows, in PowerShell:

```powershell
dev\releases\run.ps1                                                          # open it
dev\releases\run.ps1 --list                                                   # the overview in the terminal
powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1             # Start-menu entry and Desktop shortcut
powershell -ExecutionPolicy Bypass -File dev\releases\install.ps1 --uninstall # remove them; the checkout stays
```

From Git Bash, `tools/release.sh` and `tools/release.sh --install` do the same. `--uninstall --purge` also removes
the settings.

## The window

- **1. Release apps:** the **Needs release** column marks in orange every app that ships something new since its last
  tag: a changed file in its folder (tests and `requirements-dev.txt` do not count), in the core it bundles, or in
  its manual chapter, committed or not. Hover it for the files. Step 2 says the same for the portal. Those apps are
  ticked when the window opens; untick what waits (**Tick what needs a release** ticks them all again) and enter the
  versions. The version offered first follows [semantic versioning](https://robertotorino.github.io/nexus/bc250-bazzite-suite/development/architecture/#versions-changelogs-and-releases) from the CHANGELOG
  entries since the last tag (`Breaking.` major, `Added.` minor, `Fixed.` patch); its tooltip says why. A version
  that was never tagged (the first release) can be released as it is. **Apply** writes `VERSION`, every copy `tools/check_versions.py` checks and a
  `Release x.y.z.` CHANGELOG entry with your notes, which become the release notes on GitHub. The release notes
  of an app that bundles the core also name the core version. When `apps.toml`
  pins a tag of that app that was never released, the pin moves to the new version. When `apps.toml` changed since
  the last portal release, for that or another reason (an app added or removed), CI wants a portal bump in the same push:
  Apply makes it too (the lowest portal version CI accepts, with a CHANGELOG entry that lists the changed pins) and
  says so; the portal release itself stays step 2. It runs `bc250-bazzite/tools/check_manifest.py`. Then commit, push, and push the app tags (steps 1 and 2 of [the suite's release steps](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#appstoml-and-releases)),
  with **git add**, **git commit**, **git push** and **git tag** at the bottom: on Linux the push runs
  `tools/ci-local.sh` first and pushes only when CI's jobs pass. **Apply** is the pill in the header beside
  **Refresh** (*New app releases*); from another tab it opens step 1. Once applied, it is greyed out: what it
  wrote is on top of each CHANGELOG, and an app left unticked then is not ticked again. It works again when another
  app is to be released, or when you tick one.
- **2. Pin and release Portal:** the app releases to pin show here from step 1's Apply on, with where each one stands
  on GitHub (*not tagged yet* until its tag is pushed). **Pin** is greyed out until every ticked one is built; then it
  reads each release's `SHA256SUMS` and pins its tag and checksum in `apps.toml` (step 3 of the suite's release
  steps). The window shows the lowest portal version CI accepts against
  the last portal release (its tag; the last push, `origin/main`, while there is none), and offers the higher of that and what semantic versioning gives since the last
  portal tag (its CHANGELOG entries, and the apps added, removed or moved in `apps.toml`); **Bump** writes it, the portal's version on the first line and Nexus's on the second, with a CHANGELOG entry that lists the pinned app
  releases, and runs `bc250-bazzite/tools/check_manifest.py` (step 4). Then commit, test on a BC-250 ([before its tag](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#testing-a-portal-release-before-its-tag)), and only then push
  and tag the portal (step 5). The window lists these commands in that order. While step 1's releases are
  not tagged yet, Bump portal lists step 1's commands with the bump in them instead (amending the release commit
  when it is already made and not pushed), and the portal release follows once the apps are pinned. A suite made
  for Windows (its `SYSTEM` file says `windows`) has no board and no `check-release.sh`: its commands test the
  portal on the handheld from the checkout instead (`portal\run.ps1 --windowed`, which installs the pinned apps
  from their GitHub releases), and after the tag download the published release (`gh release download`) to
  install it as the portal's README says.
  Applying or bumping the same release again replaces its newest "Release x.y.z." entry, so it is written once,
  unless that entry is already pushed (it is in the last push, `origin/main`): a pushed entry is history, so the
  new one goes on top of it.
- **3. Retract app:** withdraws a release (see [Withdrawing a release](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#withdrawing-a-release)).
  For a Windows suite, its commands test the withdrawal with `portal\run.ps1` on the handheld, as above.
- **Test on this board** holds the tests of a release on a BC-250. **Test app updates** and **Test Portal
  release** run the two [board tests](https://robertotorino.github.io/nexus/bc250-bazzite-suite/portal/#testing-a-portal-release-before-its-tag) in a terminal, with the suite's `bc250-bazzite/tools/check-release.sh`: the portal from the
  checkout before the push, and the published portal release after GitHub has built it. **Test withdrawal** does
  the first on a board with a withdrawn app installed. **Installer tests** opens BC-250 Installer Tests from the
  checkout. **Record portal tour** records the portal's video tour from the checkout as it is now, for the wiki and
  YouTube (`bc250-bazzite/tools/record-tour.sh`, about a minute, its output in Logs), into
  `~/Videos/bc250-portal-tour-v<portal version>.mp4`, and opens it in your video player. The tests run on the
  ticked suite's own system: the BC250 suite's on Linux (the board). For a Windows suite they run on Windows (the
  handheld), with its `tools\check-release.ps1` in a PowerShell window: **Test app updates** and **Test withdrawal**
  start the portal from the checkout (`check-release.ps1 local`), **Test Portal release** downloads the published
  portal release, checks it against its SHA256SUMS, installs it and starts it (`check-release.ps1 release`), and
  **Installer tests** runs every installer test of the suite in turn (`check-release.ps1 installer`). **Record
  portal tour** is the BC250 suite's, on Linux. A button greyed out says on which system its tests run. Then
  **Close issues**: it lists the open issues on GitHub, such as the weekly Upstream review, each with a tick box.
  **Run** closes the ticked ones with `gh issue close` in the Commands tab, with a comment when you write one; it
  needs a gh login (`gh auth login`). A double click opens an issue on GitHub.
- **Test local apps**, on the same tab: the ticked suite's portal and every app window of it in the checkout, as an
  icon (the portal first; the Windows Portable Suite's portal too, which starts full screen as on the handheld:
  View exits it).
  When the portal is already open, its icon warns instead of starting: a second portal never opens (starting it only
  brings the open window to the front), so close it first. A click starts that app from the checkout,
  to try a change before its release: `python -m <package>` with the checkout's venv and its `core`, as `run.sh`
  starts Nexus Releases. An app that changes how the board runs asks first, as in the portal; started from the
  checkout it uses the scripts in the checkout. Each app writes its output to
  `~/.cache/nexus-releases/run/<package>.log`. When an app stops with an error, the end of its log shows on the page.
  The apps keep running when you close the window. The last icons are the ticked suite's wiki and the Nexus page
  (another suite's wiki shows when that suite is ticked; each keeps its port): **BC250 Bazzite Suite wiki
  (local)** serves this wiki from the checkout with `mkdocs serve` (the
  development venv has MkDocs) and opens it in the browser at `http://127.0.0.1:8765/nexus/bc250-bazzite-suite/`, with
  its design panel open; **Nexus wiki (local)** does the same for the Nexus page, at port 8766, and **Windows
  Portable Suite wiki (local)** for that suite's wiki, at port 8767. Each rebuilds on
  every save; its log is `mkdocs-<wiki>-local.log` there. When one is already running, a click only opens the page
  again. The wikis, like the apps, keep running when you close the window, and Nexus Releases has no button that
  stops them. A wiki started before the checkout changed (after a pull, or a change to its `mkdocs.yml` or the
  design panel) can still show the old setup: stop it, then click its icon again. `pkill -f "mkdocs serve"` stops
  every wiki on Linux; on Windows, in PowerShell:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*mkdocs serve*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`.
  With **Wikis on the network** ticked, the icons serve the wikis on every address of the computer, at
  ports 8785 and 8786, so a handheld, a laptop or the TV opens them too: the addresses for those devices show on
  the page once a wiki started. The computer's firewall has to let them in (see the Nexus page's
  [Design](design.md) chapter).
- **Logs** shows the log of the step last open, the whole window wide: what Apply, Pin, Bump portal, Retract
  or a test on this board wrote. A step that writes its log opens Logs; open the step again to go on.
- **git pull**, **git add**, **git commit**, **git push** and **git tag**, under the tabs, commit, push and tag without typing a command, with
  the checks in between. **git pull** brings in what was pushed from the other machine (`git pull --rebase
  --autostash`: your own commits go on top of it, and changes you have not committed stay as they are). It reads
  **git pull (2)** when the remote's main, as git last fetched it, has two commits this checkout lacks, and **git
  pull (new)** when the GitHub pill sees a push on main that is no commit here. Pull when you start working on a
  machine, and when **git push** says the remote has commits this checkout does not. **git add** stages every change and new file and runs `tools/fix-modes.sh`, which sets
  the exec bits CI checks. **git commit** runs `tools/check_versions.py` and `check_manifest.py` first, of the
  suites the staged changes touch (`--suite bc250-bazzite` and `bc250-bazzite/tools/check_manifest.py` for a BC250
  change; `--nexus`, core and `dev/`, when no suite changes), and commits only when they pass: one suite's failing
  check never holds another suite's commit, as its CI never holds another suite's tags; Apply and Bump portal fill in its message, and tick **Amend** when their commands
  add to the last commit (only a commit that is not pushed yet). **git push** runs `tools/ci-local.sh` first on
  Linux and pushes only when CI's jobs pass. **git tag** runs `tools/tag-release.sh` (below) with the tags of the
  step open: on tab 2 the portal's release, on the other tabs step 1's app releases that have no tag yet; it
  works once what is staged is committed and HEAD is pushed. **git push** and **git tag** ask first, with the commits or tags they send and
  the command. When the GitHub token on the machine is a `gh` login or a classic token, which reach every
  repository of your account, they say so: a fine-grained token for this repository only is safer. Each button
  works only when it has something to do, and none while a command runs; their output appears in **Commands**.
- **The command line** in **Commands** runs a command in the checkout, so you need no separate terminal for the
  commands the steps show. Type it and press Enter; its output appears above the line as it runs. **Commands**
  lists the commands the last step showed (Apply, Bump portal or Retract), one per line: pick one to put it on
  the line, then check it and press Enter. Up and Down bring back earlier commands, also from earlier sessions.
  **Stop** or Ctrl+C interrupts a command, along with anything it started in the background; `clear` or **Clear**
  empties the output.
  Each command runs with `bash -lc` in the folder the last `cd` left; variables you set do not carry over to the
  next command. A command cannot read input, so nothing can ask you something: git does not prompt for a password,
  opens no editor (commit with `-m`) and pages nothing. For a command that must ask, use a terminal. After each
  command the window reads the checkout again, as **Refresh** does. On Windows it needs Git Bash's `bash` on the
  PATH. Every command, its whole output and how it ended (its exit code) are also kept in a file of the day,
  `~/.cache/nexus-releases/commands/commands-<YYYY-MM-DD>.log` (on Windows under your user folder,
  `.cache\nexus-releases\commands`), so what a step said can be read again afterwards, or sent along when one went
  wrong.
- **Applying a release again** (after a check stopped its commit) leaves one release entry in the CHANGELOG: the
  new "Release x.y.z." takes the place of the same release's entry on top, with the notes of the second Apply.

**GitHub** in the header shows whether GitHub built your last push: every workflow run (CI, Release, Manual) on
its commit, tags included. It reads **building** while one runs, then **passed** or **failed**; hover for each
run, click to open the run that failed (or still runs) on GitHub. A run GitHub canceled because a later run of the
same workflow on the same commit took its place (the Nexus index, which each release run of a push starts) is no
failure: hover says **replaced by a later run**. It looks every 30 seconds while a build runs and
every 5 minutes otherwise, and **Refresh** looks at once. When a run it saw running finishes, a desktop
notification says whether it passed. It needs no GitHub token: answers that did not change do not count against
GitHub's limit of 60 requests an hour.

The **ticker** under the pills says where the runs of that push stand, so you need not open GitHub to follow a
build: those of the suite ticked in the Portals column and Nexus's own (CI Nexus, Manual), not another suite's CI or
releases. For each run that is still going it shows how many of its jobs are done, each job that runs with the step it
is at (*pytest (core): Run tests (4/7)*) and the time since the run started; a run that failed names its job and
step; a run that passed says so. The dot is blue while something runs, red when a run failed and green when all
passed. Hover for every job of every run; click to open the job that runs (or failed) on GitHub. The jobs need a gh
login (`gh auth login`): it then reads them every 10 seconds while a run goes. Without one it shows the runs only,
so the 60 requests an hour stay for the **GitHub** pill.

**GitHub status** beside it says whether GitHub itself works, as [githubstatus.com](https://www.githubstatus.com/)
reports it: a green dot while every part of GitHub is up, a red dot while the page reports a problem (an incident,
or a part such as Actions or Pages degraded or down). A build that waits in *queued* for long is often such a
problem. Hover for the incident and the parts affected; click to open the status page. It looks every 5 minutes,
and **Refresh** looks at once.

**Claude tokens today** says how many tokens Claude Code on this computer used since midnight, read from its own
transcripts (`~/.claude`, or the folder `CLAUDE_CONFIG_DIR` names). Hover for the last 5 hours, the input, output and
cache tokens, and each model; click to open [Claude's usage page](https://claude.ai/settings/usage), which shows
your plan's limits. Other computers and claude.ai are not counted. Without Claude Code the pill is not shown. It
looks every 5 minutes, and **Refresh** looks at once.

The releases step 2 waits for are followed from the same runs, those of the suite's release workflow (**Release**,
**Release Windows Portable**). The **GitHub** column of the pin table says where each release to pin stands: *no
run seen* (is the tag pushed?), *building…*, *ready* or *failed*; **Pin** waits
for a release that is still building, or says that its workflow failed, instead of failing on a checksum that is
not there yet. When the release of an app to pin is ready, a desktop notification says so (*ready to pin*), also
when the run started and ended between two looks, or before the window opened; each release is told once. Under
the portal version, a line says where the portal's own release stands: *not tagged yet* after Bump portal and the
commit (nothing reaches the users until `tools/tag-release.sh portal-v<x.y.z>` is run, after the test on a
board), then *building*, *released* (Test release installs it) or *failed*; its notification says *ready* when
GitHub built it.

Like the ticker, the notifications of a build that passed or failed follow the suite ticked in the Portals column:
its CI and releases and Nexus's own workflows, not another suite's CI, which every push starts too. The **GitHub**
pill itself still counts every run of the push. The notifications are the desktop's own: on Linux through `notify-send`, on Windows from the Nexus Releases icon
in the notification area, which appears with the first notification and goes when the window closes. A click on
the notification or the icon brings the window to the front. On Windows they name Nexus Releases as their source,
with its icon, not Python: when it starts, the app registers its Windows app ID for your user (in the registry,
`HKCU\Software\Classes\AppUserModelId\Nexus.NexusReleases`); `install.ps1 --uninstall` removes it.

A red line at the top of the window means a release tag points at a commit whose `VERSION` is not the tag's
version: the tag was made before the version bump was committed, and `release.yml` cannot build it. Delete the tag
(the line shows how), commit and push the bump, and tag again with `tools/tag-release.sh`.

`tools/tag-release.sh <tag> [...]` tags HEAD and pushes the tags, but refuses while HEAD does not hold each tag's
version (the bump is not committed yet), while that folder has uncommitted changes, while HEAD is not pushed to
`origin/main`, or when CI did not pass on HEAD: it asks GitHub (`tools/ci_state.py`) and waits while CI still runs,
up to an hour. A portal tag also waits for the app releases it pins: each one tagged on GitHub and pinned with its
sha256 (step 2), as the portal's release needs them. A plain `git tag` tags whatever HEAD is at that moment, also the commit from before the bump or one
CI failed. `release.yml` asks the same before it builds anything: a tag on a commit CI did not pass gives no
release. It then builds and publishes the release without an approval on GitHub (see
[GitHub settings](github-settings.md#environments)).

`tools/release.sh --list` lists every app with its version, its last tag and its pin, without Qt.

## The releases on GitHub

Every suite publishes its releases in the one repository, so each release's title names its suite and app, from
the portal's name and `apps.toml`: *BC250 Bazzite Suite: Portal 12.0.0*, *BC250 Bazzite Suite: Xenia Manager
0.11.0*, *Windows Portable Suite: Windows Portable Test 0.1.1* (`build_release.py` of each suite writes it).

Only a tag builds and publishes a release: an app or portal tag starts its suite's release workflow (**Release**,
**Release Windows Portable**). A push to main starts every suite's CI, whatever suite it is for, and on the Actions
page each run is titled with the push's commit message: after a push of *Release portal-v12.1.1*, **CI Windows
Portable** shows as *Release portal-v12.1.1* too, but it only tests. Its steps **Build the release zip, not
published** build a suite's zip on GitHub's test machine, so the next step can install it; nothing is uploaded.

A repository has one **Latest** release, and Nexus holds several suites, so no suite's portal is it. Latest is the
Nexus index, named after Nexus's own version: *Nexus v0.1.0*, tagged `nexus-v0.1.0`. It has a section per suite
with its newest portal, the download links and the install steps, or the newest release of each app while a suite
has no portal release yet (`tools/nexus_index.py`). Every release is published with `--latest=false`; after each
release workflow that succeeded, and after a push to main that changes the root `VERSION`, `nexus-index.yml` makes
the index again: it removes every earlier index release and its tag and makes the index anew on the newest commit,
marked Latest. So there is one index, Latest always has the time of the newest release of any suite and is first on
the Releases page. It can also be started by hand from the Actions tab (Nexus index, Run workflow). The release
tags ruleset must exclude `nexus-v*`, or the workflow cannot remove the old index tag
([GitHub settings](github-settings.md#rulesets)).

**Nexus's version** is the root `VERSION`, the single source, with the root `CHANGELOG`: its entries start with
their kind (`Breaking.`, `Added.`, `Fixed.`), as an app's do. Step 1 lists it as **nexus**, beside core. It needs
a release when the root CHANGELOG has entries since its last `Release x.y.z.` entry, and when a suite has a release
since then: the index lists every suite's newest portal, so its number moves with them, and a Latest that keeps its
number never looks as if a suite changed. A suite's release is an app or a portal whose `VERSION` differs from what
it was when Nexus's `VERSION` last changed, tagged already or about to be; the column names them
(*yes: wp-portal-v1.3.0*). The version offered first is the highest of what the entries ask for and what the suites
ask for: a suite's release is **minor**, a new suite **major**.

Ticking an app in step 1 ticks **nexus** too (untick it to leave Nexus for later), and step 2's **Nexus too** does
the same for Bump portal, with Nexus's version beside it. Apply and Bump portal write `VERSION` and the
`Release x.y.z.` entry; without notes the entry says what the suites bring (*Release 0.4.0. Brings
wp-portal-v1.3.0.*). There is nothing to tag, because the push to main makes the index `nexus-v<x.y.z>`.

`/releases/latest`, which the suites' READMEs and wikis link to, opens the index, and app release notes start by
pointing to it. Installed portals do not use it: they find their releases by their tag prefix (`portal-v`,
`wp-portal-v`).
