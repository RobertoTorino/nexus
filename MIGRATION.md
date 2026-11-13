<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Migration status

Working notes for moving the seven BC-250 tools into this suite. Not part of the manual or the READMEs, which
describe only what exists.

## The rewrite of the text (owner, 12-11-2026)

**The rewrite of every wiki, README and window text is on hold** (owner, 12-11-2026: "Most of the text in this
project is very badly written"; first in the backlog, waiting for the owner's corrections of the pilot). Measured on
12-11-2026: 188,000 words in the four wikis, 16,000 in 76 READMEs and about 84,000 in the apps' windows. The
CHANGELOGs and this file are history and stay as they are; new entries follow the standard once it exists.

The steps the owner agreed to (12-11-2026), in this order:

1. **The pilot, done 12-11-2026 in the working tree:** BC-250 Fan Control's wiki chapter, README, window text and
   guard messages (its CHANGELOG has the entry). The "Changes the board" box is not rewritten: it is the portal's
   `board_change`, word for word, and changing it is a portal change. The owner reads the pilot and corrects it.
2. **`.claude/writing.md`, not started:** the corrected pilot as a page of rules with before and after pairs from
   this repository, linked from CLAUDE.md, so that all new text follows it on both systems.
3. **`tools/check_prose.py`, done 12-11-2026:** findings per 1000 words, the worklist worst first, `--base` for a
   CI check later (no workflow runs it yet). The repository scored 30.9 on 12-11-2026, the pilot 4 to 6.
4. **The rewrite itself, later:** one app per unit (its chapter, window text and README together, with the source
   at hand, so the wiki's labels keep matching the window), a second pass that compares old and new for changed
   facts only, and a script that confirms every command, path, number, link and heading anchor survived, then
   `mkdocs build --strict` and the app's tests. Button and field labels stay, so few tests change.
5. **Handover per suite:** each suite its own change with its own CHANGELOG entries. The wikis and READMEs need no
   release; an app whose window text changes needs one, the owner's.

## One repository per suite (owner, 13-11-2026)

The owner decided on 13-11-2026 to go back to one repository per suite, with the tooling kept in Nexus for every
suite (a suite keeps its own tooling only where that is not possible). The steps, in the owner's order:

1. **The Bazzite Console Suite, done 13-11-2026:** `github.com/RobertoTorino/bazzite-console`, first with a copy of
   the tools, of the Nexus apps and of core, made before this plan. Brought in line the same day, in the working
   trees: no copy of the tools or the Nexus apps, cloned into the Nexus checkout as `bazzite-console/`, its
   workflows on `.github/actions/suite`. It keeps a core of its own (`core/bazzite_console_core`), which names its
   own folders and addresses. **Moving its apps to Nexus's core is on hold** (owner's decision, not made,
   13-11-2026): `bc250_core` names the BC250 suite's folders (`~/.config/bc250-bazzite-suite/`), so it first has to
   take a suite's names from the app.
2. **The Windows Portable Suite, done 13-11-2026 in the working trees:** `github.com/RobertoTorino/windows-portable`,
   without a copy of the tools. It is cloned into the Nexus checkout as `windows-portable/` and its workflows check
   Nexus out the same way (`.github/actions/suite`, the suite's `NEXUS_REF`). Its notes, with its hold, are in its
   own MIGRATION.md.
3. **The BC250 Bazzite Suite, next:** `github.com/RobertoTorino/bc250-bazzite`, the same way. Then a test that
   everything still works as intended.

What step 2 left for step 3, because the BC250 suite needs it and the Windows Portable Suite, on hold, does not:

- **The Nexus Release Tool releases only the suites of Nexus's own repository.** It commits, pushes and starts
  `release-nexus.yml` in the Nexus checkout; a suite in a repository of its own is not listed. For such a suite it
  has to commit and push in the suite's folder, start that repository's `release.yml` and read that repository's
  runs and releases. Until then such a suite is released by hand: `tools/tag-release.sh` tags it in its repository,
  and its `release.yml` takes the release commit (`gh workflow run release.yml -f commit=<sha>`).
- **The pre-push hook checks only Nexus's repository** (`tools/git-setup.sh` sets it there; `tools/pre-push.sh`
  reads the suites of the commit that is pushed). A suite in a repository of its own has no hook yet: its CI checks
  the same.
- **The Nexus release and the Nexus index** read one repository's releases (`tools/nexus_release.py`,
  `tools/nexus_index.py`). The index keeps the Windows Portable Suite's section from the releases made in Nexus
  before the move; releases made in a suite's own repository are not in it.
- **The catalogs that list every suite** (DESIGN.md, the Nexus page's Apps and features chapter from
  `nexus/features.toml`, the `SYMBOLS` of ICONS.md) still hold the Windows Portable Suite's rows. `tools/features.py
  --check` checks nothing in a checkout without that suite and says so; the suite's CI runs it.
- **`tools/ci-local.sh`** runs Nexus's and the BC250 suite's workflows; a suite's own workflows are not run locally.
- **The root `requirements-dev.txt`** names the BC250 suite's folders; the Windows Portable Suite has its own
  `windows-portable/requirements-dev.txt` for the same venv.

