<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# CLAUDE.md (Bazzite Console Suite)

The rules of the **Bazzite Console Suite**, Control your PlayStation 5 running Bazzite. The repository's
[CLAUDE.md](../CLAUDE.md) holds the shared rules for releases, changelogs, checks, line endings and the repository
layout. Status and plans belong in [MIGRATION.md](../MIGRATION.md), not in this suite's README or wiki.

## What this is

The suite's folder is `bazzite-console/`, its system is `bazzite`, and its tags start with `ps5-`. The portal's
`apps.toml` lists only apps released for this suite. **Bazzite Test** (`apps/bazzite/`, package `bazzite_test`) is
the first tile, always installed and the only required app. App keys, release tags, installer tests and wiki
chapters use the same short folder name.

The portal and its apps are for PlayStation 5 hardware running Bazzite. They read system and device information;
they do not assume that hardware features or paths from another Bazzite device apply here. This suite is maintained
independently from the BC250 Bazzite Suite.

## Layout

- `portal/`: the portal, its pinned app manifest, tests, requirements and installer.
- `apps/<name>/`: one app per folder, with its Python package, `images/`, `tests/`, `install.sh`, requirements and
  `VERSION`, `CHANGELOG`, `LICENSE` and `.gitignore`.
- `tools/`: suite-specific manifest/release helpers and installer tests.
- `docs/` and `mkdocs.yml`: the suite's wiki; `icons/`: category icons and their app copies.
- `SYSTEM` and `TAG_PREFIX`: `bazzite` and `ps5-`.

Every app uses `bc250_core` from the checkout while developing and ships the version it was tested with in a
release. The mandatory test app is the first portal tile and no other app is required.

## Design and naming

This is a Bazzite suite and follows the Bazzite design: purple for the wiki and the shared Bazzite app theme.
The portal, wiki and category icons use artwork made for this suite. The Bazzite Test app's Python package is
`bazzite_test`; its app folder and manifest key are `bazzite`.

## Checks

From the repository root, `./test.sh` includes this suite on Bazzite. Its own CI runs the suite's tests and installer
tests without making changes to another suite's workflow.
