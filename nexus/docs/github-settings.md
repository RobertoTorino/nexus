<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# GitHub settings

The repository's settings on GitHub, and why. They suit a repository where one person pushes straight to `main`
and releases come from tags. Use them as a starting point for a new project.

## Features

**Settings → General**, the section **Features** (scroll down past the repository name and social preview).

| Feature | Setting | Why |
|---|---|---|
| Wikis | Off | The documentation is the wikis, the Nexus page (`nexus/docs/`) and each suite's (its `docs/`), built and checked by `mkdocs build --strict`. A GitHub wiki is a separate repository outside CI, and search engines skip it on small repositories. |
| Issues | On | Bug reports and feature requests, through the forms in `.github/ISSUE_TEMPLATE/`. |
| Discussions | Off | Issues cover it. Turn it on for questions and reports that are not bugs. |
| Projects | Off | Not used. |

Also under **Settings → General**, in **Pull Requests**: tick **Automatically delete head branches**.

## The About box

The ⚙ next to **About** on the repository's front page, not in Settings.

- **Website:** tick **Use your GitHub Pages website**, so the address of the Nexus page shows on the front page.
- **Topics:** the keywords people search and browse by, such as `bazzite`, `bc250`, `amd`, `linux-gaming`,
  `fedora-atomic`, `universal-blue` and `pyqt6`. Only topics that really describe the project.

## Rulesets

**Settings → Rules → Rulesets.** Rules that guard against mistakes without getting in the way of daily work.

**Release tags:** one tag ruleset (**New ruleset → New tag ruleset**; its name is yours, such as
`nexus-target-tags`).

- Target tags: **Add target → Include by pattern** `*-v*`. That covers every app and portal tag (`portal-v1.1.3`,
  `governor-v0.1.1`). Then, in the same ruleset's **Target tags**, **Add target → Exclude by pattern** `nexus-v*`:
  the Nexus index (GitHub's Latest, `nexus-v0.1.0`) is removed and made anew after every release, so its tag must
  stay deletable. The list then shows both lines, the include and the exclude.
- An exclusion only narrows the ruleset it is in. A ruleset of its own with only `nexus-v*` excluded targets no tag
  at all and changes nothing: the one with `*-v*` still protects the index tag, and the Nexus index workflow then
  fails with *Repository rule violations found … Cannot delete this tag*.
- Rules: **Restrict updates** and **Restrict deletions**. Leave **Restrict creations** off, or new release tags
  are blocked too.
- Bypass list: empty. To really move a tag, set the ruleset to Disabled for a moment.

The pins in `bc250-bazzite/portal/apps.toml` name a tag and the sha256 of its asset, so a released tag must never move.

**The main branch:** **New branch ruleset**.

- Target: **Include default branch**.
- Rules: **Restrict deletions** and **Block force pushes**, nothing else.
- Bypass list: empty.

Direct pushes keep working. Rules that require pull requests or passing checks would block them, so they stay off.

## Environments

**Settings → Environments.** The release workflows (`release.yml`, and each suite's own `release-<suite>.yml`)
run in no environment, so a release needs no approval on GitHub: a tag on a commit that its suite's CI passed is
built and published at once. An environment `release` left
from before is no longer used and can be deleted.

What guards a release: only someone who may push to the repository can push a tag, and a release workflow builds
only a commit that its suite's CI passed.

## Actions

**Settings → Actions → General.**

- **Actions permissions:** **Allow RobertoTorino, and select non-RobertoTorino, actions and reusable workflows**,
  with only **Allow actions created by GitHub** ticked. The workflows use only `actions/*`, so they keep working;
  a third-party action fails until it is allowed on purpose.
- **Require actions to be pinned to a full-length commit SHA:** off. The workflows refer to actions by version
  (`actions/checkout@v4`); this setting would fail every run until each `uses:` line names a commit hash.
- **Workflow permissions:** **Read repository contents**. A workflow that needs more asks for it in its own
  `permissions:` block (`release.yml` and `release-windows-portable.yml` write releases, `nexus-index.yml` the
  Nexus index release, `docs.yml` publishes the wikis).

## Security

**Settings → Advanced Security.**

- **Private vulnerability reporting:** on. The [Security policy](https://robertotorino.github.io/nexus/bc250-bazzite-suite/SECURITY/) and the issue form's
  "Security problem" link send people to it; with it off, that link fails.
- **Dependabot alerts** and **Dependabot security updates:** on.
- **Dependabot version updates:** set in `.github/dependabot.yml`. Once a week one pull request updates the
  actions the workflows use; nothing changes until it is merged.

## Dependabot's pull requests

Dependabot opens two kinds of pull request:

- **Version updates**, from `.github/dependabot.yml`: once a week, one pull request for all the actions the
  workflows use (*ci: bump the actions group with 5 updates*).
- **Security updates**, from the setting above: when a security advisory names a dependency anywhere in the
  repository, whether or not `dependabot.yml` lists it, such as a Rust crate in Console Link's `native/` folder
  (*Bump pyo3 from 0.25.1 to 0.29.0 in /apps/console-link/native*).

A pull request starts from `main` as it was that day. `main` moves on while it waits, but its checks still show the
result on that old commit. Go through these steps before merging one:

1. **Is it still needed?** Look at the file it changes on `main` (`Cargo.toml` and `Cargo.lock`, a workflow). If
   `main` already has that version or a newer one, close it: comment `@dependabot close`, or use **Close pull
   request** at the bottom of its Conversation tab. **Archive** in GitHub's notifications only hides the
   notification; the pull request stays open.
2. **Bring it up to date:** comment `@dependabot rebase`. *No conflicts* only means git can combine the files, not
   that the result was tested. GitHub calls a pull request *unstable* while a check fails.
3. **Wait for CI on the rebased commit.** A failure from the old base that `main` has since fixed goes away. A
   failure that stays comes from the update: leave the pull request open and fix the code first, or close it.
4. **Merge** once every check is green, then `git pull`, because the merge commit exists only on GitHub until then.
5. **Write the CHANGELOG entry**, which Dependabot doesn't do: the root `CHANGELOG` for a workflow, the app's own
   for its dependency. An app's dependency reaches users only with that app's next release.

A command to Dependabot is the whole comment, nothing else: `@dependabot rebase`, not `@dependabot rebase on PR #2.`

If Dependabot answers *the branch … is protected* or *Something went wrong on our end*, the branch ruleset covers
more than `main`. A rebase force-pushes Dependabot's branch, and **Block force pushes** stops it; **Restrict
deletions** keeps the branch after the merge too. Set the ruleset's target to **Include default branch** only, as
in [Rulesets](#rulesets), then comment `@dependabot rebase` again.

The release workflows run only for a tag, so CI does not test a change to them. The next release is the first run on the new
action versions; watch it.

From a terminal, signed in with `gh` (see [The GitHub CLI](#the-github-cli)):

```bash
gh pr list --author app/dependabot             # Dependabot's open pull requests
gh pr checks <number>                          # its checks
gh pr comment <number> --body "@dependabot rebase"
gh pr merge <number>
gh pr close <number> --comment "main already has this version"
```

Other comments Dependabot answers: `@dependabot recreate` (starts the pull request over, dropping edits),
`@dependabot ignore this major version` and `@dependabot ignore this dependency` (no more pull requests for it).

## GitHub's API limit

GitHub's API answers a limited number of requests an hour: **60 without signing in**, counted per network address
(everything on your network that asks GitHub without signing in shares them), and **5,000 when signed in**.
Answers that did not change since the last look ("304 Not Modified") do not count.

Nexus Releases asks the API whether the newest push built: every 30 seconds while a build runs, every 5
minutes otherwise. A running build with a busy hour of other requests can use up the 60. The window shows how many
are left, beside its GitHub button (*GitHub API: 4,894 of 5,000 left until 04:16, signed in*); when none are left
the button says *GitHub: limit reached, back at …* and waits until then.

**Nothing is broken when the limit is reached**, and there is nothing to fix: GitHub answers again after the time
shown. To get the 5,000, sign in once with the GitHub CLI:

```bash
brew install gh
gh auth login
```

Nexus Releases then uses that login (`gh auth token`; a `GITHUB_TOKEN` or `GH_TOKEN` variable takes its place). The
token is only sent to GitHub's API and never stored by the app. The limit as it stands right now:

```bash
curl -s https://api.github.com/rate_limit                                            # without signing in
curl -s -H "Authorization: Bearer $(gh auth token)" https://api.github.com/rate_limit # signed in
```

## The GitHub CLI

`gh` reads and steers the workflows from a terminal, signed in as above. It works from the checkout, so start it
there. These are the commands a release needs most.

The runs of the last push, and one run's jobs (`<run id>` is the number in the list):

```bash
gh run list --limit 10
gh run view <run id>
gh run watch <run id>                       # follows it until it ends
```

The runs on one commit. `--commit` needs the full SHA, not the short one `git log` shows, so let git expand it:

```bash
gh run list --workflow CI --commit "$(git rev-parse HEAD)"
gh run list --workflow Release --commit "$(git rev-parse bfd16e3)" --limit 30
```

Whether CI passed on a commit, as `tools/tag-release.sh` and the release workflow ask it:

```bash
python3 tools/ci_state.py "$(git rev-parse HEAD)"
```

Why a run failed: the log of its failed steps only, or one job's full log (`<job id>` from `gh run view`):

```bash
gh run view <run id> --log-failed
gh run view --job <job id> --log
```

A job that hangs keeps its log until it ends; cancel the run to read it. Then run what failed again, on the same
commit:

```bash
gh run cancel <run id>
gh run rerun <run id> --failed
```

When CI failed or hung on a release commit, each release on that commit stopped too. Once CI passes, run them again
in one go:

```bash
gh run list --workflow Release --commit "$(git rev-parse bfd16e3)" --status failure --limit 30 \
  --json databaseId -q '.[].databaseId' | xargs -n1 gh run rerun --failed
```

A release, its files and its notes:

```bash
gh release view governor-v0.1.8
gh release download governor-v0.1.8 --pattern SHA256SUMS --output -
```
