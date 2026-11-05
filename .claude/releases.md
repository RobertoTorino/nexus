<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Releases

The long form of the root [CLAUDE.md](../CLAUDE.md)'s Releases: what a release is, Nexus's version, the CHANGELOG
kinds, and which steps are the owner's. Read it when a task touches the release tools, Nexus Release Tool, the
workflows, a VERSION or a CHANGELOG's release entries.

## A Nexus release

A **Nexus release** (owner, 30-10-2026) is the one release of the repository: Nexus's version with the suite ticked
in the tool, when it changed, started by the owner with the Nexus Release Tool's one action, Start new release
(`.github/workflows/release-nexus.yml` calls that suite's own release workflow, which builds, publishes and pins; its
portal ends as a draft the owner device-tests and publishes from the tool). Each suite is released on its own (owner,
05-11-2026): Start passes the suite as the workflow's `suites` input, the run carries only that one, and a draft of one
suite never holds up the other's release. A suite takes part once its
release workflow has `workflow_call`: both suites do (the Windows Portable Suite's `release-windows-portable.yml`
since 30-10-2026, the BC250 Bazzite Suite's `release.yml` since 04-11-2026, stage 3), so every suite releases with
the same steps (owner, 04-11-2026). A tag pushed by hand still releases that one app or portal. The plan and its
stages are in MIGRATION.md.

The owner does every step of a release; Claude does none of them, and doesn't offer to:

- bumping a `VERSION` (and the copies `tools/check_versions.py` checks), or `portal/VERSION`;
- tagging (`<app>-v<x.y.z>` or `portal-v<x.y.z>`, after the suite's prefix, with `tools/tag-release.sh`, which waits until CI passed on the
  commit), which starts `.github/workflows/release.yml` (it, too, builds only a commit CI passed);
- building or publishing release assets (`tools/build_release.py`) and the GitHub releases themselves;
- pinning a release in the suite's `portal/apps.toml` (`bc250-bazzite/tools/pin_app.py`, the `tag` and `sha256`
  lines);
- the release entries in the CHANGELOGs.

`tools/nrt.sh` starts the owner's front end for the file edits of a release, Nexus Release Tool (`dev/nrt/`,
a Nexus app with its suites' portals in its first column, the one to release ticked: `main_window.py` on
`plan.py`; a suite's board checks are its own
`tools/check-release.sh`, the BC250 suite's at `bc250-bazzite/tools/check-release.sh`; a Windows suite's
`tools/check-release.ps1`, run on the handheld). Claude may change it and
its tests, but never uses it on the repository.

Claude may change the release tools and their tests, and runs `bc250-bazzite/tools/installer-tests/release.sh` as a
test (it works in a temp folder and publishes nothing). When finished work will need a release or a version bump, the
handover says which app and why; the owner decides the number.

## Versions

- **VERSION is the single source** of each app's version (all started at 0.1.0). Copies in code (`__version__`,
  shell `VERSION=`, pyproject) must match: `tools/check_versions.py`.
- **The dev/ apps' versions** (owner, 04-11-2026): never released or tagged, so not in Nexus Release Tool; the
  owner sets them with Nexus Dashboard's **Dev app versions** tile (`tools/dev_versions.py`): VERSION, the
  `__version__` copy and a "Version x.y.z." CHANGELOG entry, as core's. Claude doesn't run it.
- **Nexus's version** (owner, 28-10-2026): the root `VERSION`, with the root CHANGELOG, is Nexus's own; the owner
  bumps it (the Nexus Release Tool's step 1 row **nexus**). It is never tagged by hand: `nexus-index.yml` publishes GitHub's
  Latest release, the Nexus index, as `nexus-v<VERSION>` titled `Nexus v<VERSION>`. A suite's release (an app or a
  portal) moves it too, since the index lists every suite: a suite's release is minor, a new suite major (owner,
  28-10-2026); Nexus Release Tool offers it with every app and portal release.
- **Semantic versioning** (owner, 15-10-2026): in an app's, core's, the portal's or the root (Nexus's, from
  28-10-2026) CHANGELOG, every entry starts
  with its kind: `Breaking.` (removed, or no longer working as before: major), `Added.` (a new feature: minor) or
  `Fixed.` (a bug or security fix: patch). 0.x apps too: a feature takes 0.1.4 to 0.2.0. Nexus Release Tool offers the
  highest kind since the last tag first; `tools/tests/test_changelog_kinds.py` checks it. The number stays the
  owner's.
