<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contributing

Bug reports, ideas and pull requests are welcome. Report security problems privately, through GitHub's private
vulnerability reporting (the repository's Security tab), not in an issue or a pull request. Each suite has its own
repository, with its own contributing rules.

## Licenses

Each app keeps its own `LICENSE`, and what you contribute to a folder is under that folder's license:

- GPL-3.0-or-later: `core/`, `tools/`, the Nexus apps in `dev/` and the Nexus page.

Icons and sounds are under the license of the folder they are in, the same as the code. Contribute only what you may
license that way: your own work, or work under a compatible license, with its source and license named in the pull
request. Say so when something was made with generative AI tools.

## Icons

Every app of a suite in a category has the same icon. A new or changed icon goes in the suite's
`icons/<category>/`; `python3 tools/sync_icons.py --suite <suite>` writes the copies the apps, the portal and the
wiki use (Nexus Dashboard's Convert icons does the same from a window). The Nexus icon and the Nexus apps' copies of
it are written by `python3 tools/make_icons.py`.

## Before a pull request

- Add a CHANGELOG entry: the app's own for a change to one app (or core's), the root `CHANGELOG` for a change to
  the whole repository. The format is a `Changelog: DD-MM-YYYY HH:MM:SS` line (Europe/Amsterdam time), a blank line, then plain
  sentences starting with `Breaking.`, `Added.` or `Fixed.`.
- Leave `VERSION` files as they are: versions and releases are the maintainer's.
- Run the checks CI runs: `tools/ci-local.sh` (podman), or at least `./test.sh`.
