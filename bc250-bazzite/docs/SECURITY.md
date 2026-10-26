<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

<span class="page-icon">:material-shield-lock-outline:</span>

# Security

## Reporting a vulnerability

Please don't open a public issue for a security problem. Use **Security → Report a vulnerability** in this
repository instead, so it can be fixed before it's public. You'll get an answer within a week.

## Verifying a download

Every release comes with a `SHA256SUMS` file. Check the download before you install it:

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

The app also checks its own test files before every run and refuses to run tests when they were changed.

## Dependencies and known vulnerabilities

The suite answers for its own code and for the Python packages its apps install. Bazzite's own packages, including
the system tools some apps run (such as `systemctl`, `sudo` or `cec-ctl`), are updated and patched by Bazzite.

The [Dependency Checker](apps/package.md) shows where the suite's dependencies stand:

- **Python packages** are read from the environment each installed app runs in: the suite's shared one, or the
  app's own. A card shows the version in each environment, whether it meets the app's requirement, and the latest
  version on PyPI.
- **Known vulnerabilities:** each installed version is looked up in [OSV.dev](https://osv.dev), the open database
  that collects the GitHub, PyPA and NVD advisories. A green **✓ CVE** means no known vulnerability. A red
  **✗ CVE** lists each one by its CVE ID, linked to [Snyk's vulnerability database](https://security.snyk.io/),
  with the release that fixes it, and the card says which version to update to and for which apps. **CVE ?** means
  the check could not run, for example without a network; it never counts as clean.
- **External tools** are checked for availability only: whether each one is installed, which apps need it, and
  whether it needs root. Their versions are not looked up, because they come with Bazzite or from their makers,
  and OSV.dev has no reliable record of those builds.

The checker changes nothing. It sends the names and versions of the Python packages to PyPI and OSV.dev, and
nothing else.

When a package of an app has a known vulnerability, the card names the version with the fix. The fix reaches the
app through an app release that requires that version. If no release does yet, report it as described above.

## Root and passwords

- The apps run as your own user. Their installers refuse to run with sudo, and so do the bisect scripts. Only the
  steps that need root ask for your password, through sudo in a terminal or pkexec in a desktop dialog.
- Apps whose scripts run as root are installed root-owned under `/opt`, so a normal user cannot change code that
  sudo runs. Bazzite Test never runs a tool as root from a folder you can write to, such as `~/.local/bin`.
- The tools that only work as root are marked **Needs root.** in the Dependency Checker.
- The portal asks before it installs or opens an app that changes how the board runs (unlocks, clocks, voltages,
  firmware tables, the VRAM split, the patched driver). All of them are software-only and can be undone.
