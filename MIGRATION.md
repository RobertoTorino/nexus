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

1. **The Bazzite Console Suite, done 13-11-2026:** `github.com/RobertoTorino/bazzite-console`, standalone, with its
   own tooling, its own core and its own development apps (owner, 13-11-2026: "it is and stays a standalone repo ...
   it should run on its own using its own tooling"). Nexus knows nothing of it. It was coupled to the Nexus checkout
   for a few hours that day, as step 2 is, and that was undone.
2. **The Windows Portable Suite, done 13-11-2026 in the working trees:** `github.com/RobertoTorino/windows-portable`,
   without a copy of the tools. It is cloned into the Nexus checkout as `windows-portable/` and its workflows check
   Nexus out the same way (`.github/actions/suite`, the suite's `NEXUS_REF`). Its notes, with its hold, are in its
   own MIGRATION.md.
3. **The BC250 Bazzite Suite, done 14-11-2026 in the working trees:** `github.com/RobertoTorino/bc250-bazzite`,
   standalone like step 1, not coupled like step 2 (owner, 14-11-2026: "identical to bazzite-console"): its own
   tooling, core and development apps, a plain copy without the git history, which stays here. The owner's choices
   that day: a clean cut (installed portals of before keep looking for releases in Nexus; the boards install the
   portal again from the new repository) and the new wiki address only (robertotorino.github.io/bc250-bazzite/, the
   old one under the Nexus page is gone). Nexus knows nothing of it beyond the links on the Nexus page and the Nexus
   index's pointer to its releases; its releases up to then stay on Nexus's Releases page. Then a test that
   everything still works as intended.

What step 2 left, for the Windows Portable Suite while it is on hold (the BC250 suite has its own tooling now, so
none of it is needed for it):

- **The Nexus Release Tool releases only the suites of Nexus's own repository,** and there are none now: in Nexus it
  lists core and Nexus's own release. For a suite in a repository of its own it would have to commit and push in the
  suite's folder, start that repository's `release.yml` and read that repository's runs and releases. Until then
  such a suite is released by hand: `tools/tag-release.sh` tags it in its repository, and its `release.yml` takes
  the release commit (`gh workflow run release.yml -f commit=<sha>`).
- **The pre-push hook checks only Nexus's repository** (`tools/git-setup.sh` sets it there; `tools/pre-push.sh`
  reads the suites of the commit that is pushed). A suite in a repository of its own has no hook yet: its CI checks
  the same.
- **The Nexus release and the Nexus index** read one repository's releases (`tools/nexus_release.py`,
  `tools/nexus_index.py`). The index keeps the Windows Portable Suite's section from the releases made in Nexus
  before the move, and points to the BC250 Bazzite Suite's repository for its releases.
- **The catalogs that list every suite** (DESIGN.md, the Nexus page's Apps and features chapter from
  `nexus/features.toml`) hold the Windows Portable Suite's rows alone; the BC250 suite's left with it.
  `tools/features.py --check` checks nothing in a checkout without that suite and says so; the suite's CI runs it.
- **`tools/ci-local.sh`** runs Nexus's workflow alone; a suite's own workflows are not run locally.
