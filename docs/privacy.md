<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

<span class="page-icon">:material-eye-off-outline:</span>

# Privacy

The BC250 Bazzite Suite collects nothing about you. It has no accounts, no statistics, no analytics, no crash
reports and no advertising, and there is no server of ours that anything could be sent to. What the apps store
stays on the board, in your home folder. The few things that go over the network are listed below, with when and to
whom.

Everything about the suite itself is public: the code, the plans and the issues are on
[GitHub](https://github.com/RobertoTorino/nexus). Personal data is the exception, and the apps keep
it out of what they show and save where they can.

## What goes over the network

Each request names the app and its version (for example `bc250-shadps4-manager/0.1.5`) and nothing about you.
The servers see your IP address, as any website you open does.

**GitHub** (`github.com`, `api.github.com`, `raw.githubusercontent.com`), for releases:

- The [portal](portal.md) downloads the apps you install from the suite's releases, and at start asks whether a
  newer portal release is out.
- The shadPS4, RPCS3, PPSSPP, PCSX2 and Xenia Managers and the Decky Loader Manager ask for the
  emulator's or Decky's newest release when their window opens, and download the release you install.
- [BC-250 Upscaler Manager](apps/upscaler.md), [BC-250 Mesh Shaders](apps/mesh.md) and the
  [GPU Governor Manager](apps/gpu.md) look for a newer release of what they install at start; each can be
  told not to in its settings.

**Sony** (`fwupdater.dl.playstation.net`): [USB HD Control](apps/hdcontrol.md#the-firmware-update) asks Sony's
update server for the controllers' latest firmware when its window opens (at most once a day; it can be told not
to), and downloads the firmware when you update a controller.

**PyPI and OSV.dev**: the [Dependency Checker](apps/package.md) sends the names and versions of the
Python packages in the apps' environments, to learn whether newer ones or known vulnerabilities exist. Its
Bazzite card and weekly reminder read Bazzite's update state on the board itself and send nothing. Installing an
app downloads its Python packages from PyPI.

**Only when you ask for it:**

- [Console Link](apps/consoles.md#privacy) talks to your own consoles on your own network, and to PlayStation
  (PSN) only for **Find my account ID**; the sign-in happens in your browser. Its window masks your account ID,
  online ID and the consoles' addresses.
- [Console LinkB](apps/clb.md#privacy) talks to Microsoft's Xbox services when you sign in, refresh, wake a
  console or stream; the sign-in happens in your browser. Its log masks the account's tokens, your gamertag, the
  consoles' IDs and network addresses.
- [shadPS4 Manager](apps/shadps4.md#shadnet): shadPS4 signs in to the shadNet server you set, with the
  account you set. shadPS4 keeps the password as it is and shadNet sends it unencrypted: use one you use nowhere
  else.
- [Bazzite SFTP Tools](apps/sftp.md) connects only to the host you enter.
- [Bazzite DatStation](apps/datstation.md#privacy) loads the PlayStation Blog's feed on its PS News page.
- [BC-250 Bazzite Test](apps/check.md): its network test resolves and pings `google.com` and asks
  `www.example.com` for a page header; the optional speed test uses Ookla's servers and about 1 GB of data.
- [USB IPS3.5](apps/ips35.md#settings) shows the weather only for a place you choose: the name you search for,
  then that place's coordinates every 30 minutes while its Weather tile is shown, go to Open-Meteo
  (`geocoding-api.open-meteo.com`, `api.open-meteo.com`), which needs no account.
- [USB HD Cam](apps/hdcam.md#the-firmware) downloads the camera's firmware from GitHub
  (`raw.githubusercontent.com`) only when you click Download.
- [BC-250 ACE Queues](apps/ace.md) and [BC-250 Mesh Shaders](apps/mesh.md) download Mesa's source
  from `archive.mesa3d.org` when they build their driver.

Links you click (a release page, the wiki, a PlayStation page) open in your browser, under that site's own privacy
terms.

## What stays on the board

Each app keeps its settings in `~/.config/<app>` and its data and logs in `~/.local/share/<app>`; each chapter has
the exact list. Nothing of it is uploaded. Uninstalling with `--purge` removes the settings and logs too.

Some of it can identify you: host and user names, serial numbers, MAC and IP addresses, account IDs. Where an app
shows or saves such details, it masks them: [Bazzite Test](apps/check.md) masks them in saved logs (on by default,
in **Settings › Privacy**), [Console Link](apps/consoles.md#privacy) in its window and log, and
[Console LinkB](apps/clb.md#privacy) in its log. Before you share a log or a screenshot, for example in an issue,
look it over for anything you would rather keep to yourself.

## This wiki

The wiki is served by GitHub Pages, so GitHub's
[privacy statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement)
applies to your visit, as it does on any GitHub page. The wiki itself adds nothing: no analytics and no cookies,
and its fonts and scripts come from the wiki, not from other sites. The theme keeps a little state, such as the
search, in your browser's session storage, which stays in your browser and is gone when you close it.

## A privacy problem

An app release with a privacy problem is withdrawn: the portal stops offering it and removes it from the boards
(see [the portal](portal.md)). To report one, open an issue on
[GitHub](https://github.com/RobertoTorino/nexus/issues), or, when it should not be public before it
is fixed, use **Security → Report a vulnerability** as the [security policy](SECURITY.md) says. Leave personal
data out of the report.
