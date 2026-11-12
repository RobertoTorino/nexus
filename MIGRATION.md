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

## The Windows Portable Suite on hold (owner, 09-11-2026: from 10-11-2026)

**Development of the Windows Portable Suite is on hold from 10-11-2026** (owner, 09-11-2026: the last day with the
ROG XBOX Ally X). The released apps and wp-portal-v10.3.0 stay as they are; no new features or releases until the
owner takes it up again. The wiki carries a banner saying so on every page (`windows-portable/tools/mkdocs/overrides/main.html`,
Material's announce bar; take it out when work resumes). The BC250 Bazzite Suite and Nexus go on.

