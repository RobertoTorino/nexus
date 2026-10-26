# SPDX-License-Identifier: GPL-3.0-or-later
"""Help page content."""

from __future__ import annotations

from PyQt6.QtWidgets import QTextBrowser, QWidget

from . import APP_NAME, GOVERNOR_URL, REPO_URL, __version__, fmt


def help_html(config: str) -> str:
    text = ("""
<h1>%1 <small>v%2</small></h1>
<p>A small front-end for <b>cyan-skillfish-governor-smu</b>, the GPU governor of the <b>AMD BC-250</b>
(Cyan Skillfish APU, gfx1013) on <b>Bazzite</b>. The governor must already be installed; this app
edits one section of its configuration and controls its systemd service. Nothing else on the system
is touched.</p>

<h2>Overview</h2>
<p>Shows whether the service runs, whether the governor's patched <code>gpu_metrics</code> table is
mounted over sysfs, whether a GPU load sensor is available, and a chart of the GPU load (%), temperature (°C, left
axis) and clock (MHz, right axis). A missing reading leaves a gap, never a fake zero. The app keeps the last hour
of samples (one every two seconds) while it runs; <b>Window</b> picks how much of it the chart shows (2, 10, 30 or
60 minutes) and <b>Export CSV…</b> writes every kept sample (time, load, clock, temperature, socket power,
performance mode, runtime range) to a file. <b>Compare…</b> loads such a file back and draws it dashed behind
the live lines (newest sample at the right edge, like the live window) and puts both sessions' averages and
peaks under the chart (load, clock, temperature, socket power), so a profile or safe-point change can be judged
against an earlier run; <b>Clear</b> removes it.</p>
<p>The <b>gpu_metrics table</b> box decodes the table the kernel (or the governor) exposes: activities, temperatures,
socket/GFX/CPU power, the GFX, SoC, memory and fabric clocks, the throttle status and the CPU core clocks.
<i>(patched)</i> means the governor's table is mounted; <i>(raw)</i> is the kernel's own table, whose GFX activity
on a BC-250 is the broken 655% value and is not used as load.</p>
<p>The BC-250 usually has no <code>gpu_busy_percent</code> sensor, but the governor measures the load itself and,
with <b>fix-metrics</b> on, publishes it in the patched <code>gpu_metrics</code> table it mounts over sysfs. The app
reads the load from there; <code>gpu_busy_percent</code> and <code>radeontop</code> are fallbacks. Without any
source it shows <b>N/A</b>, never a misleading 0%, and the tooltip tells you what is missing. The GPU clock and temperature come from the amdgpu hwmon
sensors; with <code>fix-freq</code> on, the clock is the real SMU value.</p>

<h2>GPU Usage</h2>
<p>Edits the <code>[gpu-usage]</code> section of <code>%3</code>:</p>
<table cellpadding="4" cellspacing="0" border="1" width="100%">
<tr><th>Key</th><th>Default</th><th>Meaning</th></tr>
<tr><td><b>fix-metrics</b></td><td>true</td><td>Write the measured load into a patched <code>gpu_metrics</code>
table and bind-mount it over sysfs. Fixes the 655% GPU usage of MangoHud, the Steam overlay and radeontop.</td></tr>
<tr><td><b>fix-freq</b></td><td>false</td><td>Also patch <code>current_gfxclk_frequency</code> with the clock read
from the SMU. Fixes the wrong sysfs frequency, mainly after the 8-core unlock. Independent of fix-metrics.</td></tr>
<tr><td><b>method</b></td><td>busy-flag</td><td><i>busy-flag</i> samples the GPU's busy bit;
<i>process</i> scans every process that uses the GPU (more CPU work); <i>kernel</i> needs a patched kernel.</td></tr>
<tr><td><b>temp-read</b></td><td>drm</td><td>Where the GPU temperature is read: the DRM ioctl (keeps a DRM handle
open) or the hwmon <code>temp1_input</code> file. Same sensor.</td></tr>
<tr><td><b>flush-every</b></td><td>10</td><td>Flush the patched table every N update cycles.</td></tr>
</table>
<p>And the <code>[gpu]</code> section: <b>set-method</b> (<i>smu</i>, the default, applies clock and voltage through
the SMU directly; <i>kernel</i> goes through the amdgpu sysfs interface instead).</p>
<p><b>Apply changes</b> (on this page or on Tuning) asks for your password once (pkexec). It copies the current
file to <code>config.toml.bak-YYYYMMDD-HHMMSS</code> and writes the pending edits of both pages. Only the known
keys change; every other line of the file, including comments, is kept. The governor reads the file at start, so
the service is restarted afterwards unless you untick that option.</p>

<h2>Tuning</h2>
<p>Edits the other sections of <code>%3</code>:</p>
<table cellpadding="4" cellspacing="0" border="1" width="100%">
<tr><th>Section</th><th>Keys</th><th>Meaning</th></tr>
<tr><td><b>[frequency-range]</b></td><td>min, max</td><td>Clock limits in MHz the governor starts with. <i>No limit</i>
(0) leaves the limit open; values outside the safe-points table are clamped by the governor.</td></tr>
<tr><td><b>[load-target]</b></td><td>upper, lower</td><td>Ramp the clock up when the load is above <i>upper</i>,
down when it is below <i>lower</i>. A wide gap keeps the clock steady, a narrow one follows the load closely.
The governor's own defaults when the section is missing are 95% / 80%; the shipped file uses 65% / 50%.</td></tr>
<tr><td><b>[temperature]</b></td><td>throttling, throttling_recovery</td><td>Throttle above the first value (default
85 °C); recover below the second, which is optional (<i>Not set</i>) and must be lower.</td></tr>
<tr><td><b>[dbus]</b></td><td>enabled</td><td>Publish <code>com.cyanskillfish.Governor</code> on the system bus. The
Performance page needs it; the shipped file turns it on, the governor's built-in default is off.</td></tr>
<tr><td><b>[timing]</b></td><td>intervals.sample, intervals.adjust, ramp-rates.normal, ramp-rates.burst, burst-samples,
down-events</td><td>The control loop: how often the load is sampled and the clock adjusted (µs), how fast the clock
moves towards its target (MHz/ms), how many busy samples in a row switch to the faster burst ramp (<i>Off</i> leaves
the key out), and how many low-load adjust cycles pass before the clock steps down. Governor defaults: 2000 µs /
10 × sample, 1 / 200 × normal, off, 10; the shipped file uses 250 µs / 100 000 µs, 1 / 50, 60, 5.</td></tr>
<tr><td><b>[frequency-thresholds]</b></td><td>adjust</td><td>Dead band in MHz: a non-burst change smaller than this is
not applied (default 10).</td></tr>
</table>
<p><b>Presets</b> fill in the frequency range, load target and temperature at once (timing is left alone): <i>Shipped defaults</i> (the package's config), <i>Quiet</i> (lower
clocks, late ramp-up), <i>Responsive</i> (early ramp-up, full range) and <i>Maximum clock</i> (stays near the top).
The combo box shows <i>Custom</i> as soon as a value differs from every preset. Invalid combinations (min above
max, recovery not below throttling, adjust interval shorter than sample, burst rate not above normal) are flagged
under the form and block Apply.</p>
<p><b>Profiles</b> are named snapshots of every value on this page and the GPU Usage page (safe points are not
included), stored for your user in <code>~/.config/bc250-governor-manager/profiles.json</code>.
<i>Save current as…</i> stores what the forms show right now, applied or not. <i>Load into forms</i> fills both
pages so you can review and apply as usual; <i>Apply now</i> writes the profile to <code>config.toml</code>
(backup first, one password prompt), discards pending edits and restarts the governor. With the tray icon on, the
tray menu's <i>Apply profile</i> submenu does the same without opening the window. For a <b>keyboard shortcut</b>,
<i>Copy hotkey command</i> puts <code>bc250-governor-manager --profile 'Name'</code> on the clipboard; bind it in
System Settings → Shortcuts (KDE) or Keyboard → Custom Shortcuts (GNOME). The app runs once per user: that command
reaches the running instance over a local socket and applies the profile there (one password prompt, tray
notice), or starts the app and applies it when nothing is running. A plain second launch just raises the window.
<code>--list-profiles</code> prints the saved names.</p>

<h2>Safe points</h2>
<p>The <code>[[safe-points]]</code> of <code>%3</code> as an editable table and a frequency/voltage curve.
The governor scales along this curve and never leaves its range; <code>[frequency-range]</code> and the runtime
controls are clamped to it. <b>Add point</b> inserts halfway to the next point, <b>Remove</b> deletes the selected
row, <b>Shipped defaults</b> loads the governor's own table, <b>Revert</b> goes back to the file. Before
<b>Apply safe points</b> is enabled the list must pass the governor's rules (at least two points, unique
frequencies, voltage never dropping as frequency rises) and the hard rails shared with bc250-gpu-oc-bisect
(700–1100 mV, up to 2500 MHz). Above 2000 MHz or 1000 mV, or when a change raises the top frequency or lowers an
existing voltage, you get a warning: an unstable point freezes the board under load. Apply makes a backup and
asks for your password; finding a board's own ceiling safely is the job of
<a href="https://github.com/RobertoTorino/nexus/tree/main/bc250-bazzite/apps/oc">bc250-gpu-oc-bisect</a>.</p>
<p><b>Test a point before saving it</b> uses the governor's root-only <code>TestMode</code> D-Bus interface
(one <code>pkexec</code> prompt): the GPU is pinned to the frequency and voltage you enter and the automatic
scaling stops, while thermal throttling stays active. Nothing is written to <code>config.toml</code>. The
fields are prefilled from the selected row; a warning appears above 2000 MHz / 1000 mV or when the voltage is
below what the curve above would give. <b>Load</b> picks a GPU load generator found on PATH (vkmark, glmark2,
vkcube or glxgears, in that order of preference); it is started with the test and killed when the test ends,
and if it dies while the point is pinned the status says so. Without one, load the GPU yourself and watch the
Overview. <b>Stop test</b>, the timer (default 60 s, <i>Until stopped</i> = 0), closing the app, or any action on
the Performance page ends the test by switching performance mode off, which returns the governor to normal
scaling with its start-up range. The result line then reports how long the point was held, the peak temperature
and the clock range seen; <b>Add to table</b> puts the tested pair into the safe-points table (sorted, replacing
a point at the same frequency) so you can apply it. While a point is pinned the <b>kernel log</b>
(<code>journalctl -k -f</code>) is watched for amdgpu trouble (ring timeouts, GPU resets, <code>*ERROR*</code>
lines, SMU failures); the first such line aborts the test at once, releasing the point before the board freezes,
and is quoted in the result. A clean run says so too. Reading the kernel ring needs membership of the
<code>systemd-journal</code> (or <code>wheel</code>) group; otherwise the status says the log is not watched and
the test runs blind. A point the silicon cannot hold can still freeze the board faster than the kernel can log
it, so save your work first. Only the smu governor has D-Bus.</p>

<h2>Performance</h2>
<p>Runtime control of the governor over D-Bus, exactly what the governor's own
<code>cyan-skillfish-performance-mode</code> wrapper does. The changes apply immediately, need no password and are
lost at the next governor restart; <code>config.toml</code> is not touched. <i>Copy runtime values to the Tuning page</i>
carries the current range and thresholds over to the Tuning page so you can save them.</p>
<ul>
<li><b>Performance mode</b> is a toggle (red while on): on opens the full allowed (safe-points) range; off returns
to the range of <code>[frequency-range]</code>.</li>
<li><b>Pin clock</b> fixes the frequency and turns performance mode on.</li>
<li><b>Set range</b> applies a runtime min/max.</li>
<li><b>Set load target</b> and <b>Set temperatures</b> change the load band (lower/upper %) and the throttling /
recovery temperatures the governor scales with, without touching performance mode or a running safe-point test.
The fields follow the governor's current values and are refilled when they change; impossible pairs (lower not
below upper, recovery not below throttling) disable the button.</li>
</ul>
<p>The controls are disabled when the service is not running or the bus name is not published; the reason is shown
under the controls. Enable <code>[dbus] enabled</code> on the Tuning page and restart the governor if needed.</p>
<p><b>Per game</b> builds the launch line for the governor's <code>cyan-skillfish-performance-mode</code> wrapper:
plain performance mode, <code>--fixed-frequency</code>, <code>--range</code>, <code>--load-target</code> or
<code>--temperature</code>, prefilled with the governor's current numbers, formatted for Steam launch options
(<code>… %command%</code>), a Heroic/Lutris wrapper command, or a terminal. <b>Copy</b> puts it on the clipboard.
The wrapper applies the setting, runs the game, and turns performance mode off when it exits, which also puts the
governor back on its start-up range. It needs D-Bus enabled, like the controls above.</p>

<h2>Backups</h2>
<p>Every write makes a copy <code>config.toml.bak-YYYYMMDD-HHMMSS</code> next to the config. The page lists them,
shows the difference between a copy and the current file, and <b>Restore selected</b> puts the copy back (the current
file is backed up first, password asked once). The governor is restarted afterwards unless you untick that option.</p>

<h2>Service</h2>
<p>Start, stop, restart, enable or disable <code>cyan-skillfish-governor-smu.service</code>, with the output of
<code>systemctl status</code> and a <b>live journal</b> (<code>journalctl -u … -f</code>, last 200 lines and
everything that follows while the page is shown, up to 2000 kept). The filter box takes text or a regular
expression, case-insensitive; untick <b>Follow</b> to read without being scrolled. Reading system units needs your
user in the <code>wheel</code> or <code>systemd-journal</code> group, which is the case on Bazzite. Each service
action asks for your password.</p>
<p><b>Check for updates</b> compares the installed <code>cyan-skillfish-governor-smu</code> RPM with the latest
release of <a href="https://github.com/filippor/cyan-skillfish-governor/releases">filippor/cyan-skillfish-governor</a>
on GitHub (one request to api.github.com; also run at start unless turned off in Settings). A newer release is
shown in orange with a link to its notes. Update the package the way you installed it: COPR
<code>filippor/bazzite</code> via <code>rpm-ostree upgrade</code> when layered, or the release tarball.</p>
<p><b>Export diagnostics…</b> writes one text file for a bug report: app, governor and Bazzite versions, CPU/GPU,
<code>config.toml</code> and its backups, <code>systemctl status</code>/<code>cat</code>, the last 300 journal
lines, the D-Bus interface, kernel command line, amdgpu kernel messages, the hwmon sensors, and the raw
<code>gpu_metrics</code> table (parsed and as a hex dump). Read the file and remove what you do not want to
share before attaching it to an issue.</p>

<h2>Settings</h2>
<p>App settings, stored per user. <b>System tray</b>: show a tray icon whose tooltip carries the GPU load, clock,
temperature, performance mode and governor state; left-click shows or hides the window, the menu toggles
performance mode (when D-Bus is reachable) and quits. With <i>Closing the window keeps the app running in the
tray</i> ticked, the window close button hides to the tray instead of quitting; use the tray menu to quit.
<b>Start at login</b> writes <code>~/.config/autostart/bc250-governor-manager.desktop</code> (nothing
system-wide), optionally starting hidden in the tray with <code>--start-in-tray</code>. Bazzite's KDE Plasma
session has a native tray, so this works out of the box; a GNOME session would need the AppIndicator extension.
<b>Alerts</b> are desktop notifications via the tray icon (status bar only when the tray is off): the GPU reaching
a temperature you choose, the GPU reaching the governor's own throttling temperature (the runtime value when D-Bus
is reachable, else the one in <code>config.toml</code>), and the governor service stopping or failing after the
app has seen it running. A temperature alert fires once per crossing and re-arms 5 °C below its threshold; the
same alert repeats at most every 5 minutes.</p>

<h2>The older tt governor</h2>
<p>Started with <code>--backend tt</code> (or automatically when only <code>cyan-skillfish-governor-tt.service</code>
is loaded), the app manages <code>/etc/cyan-skillfish-governor-tt/config.toml</code> instead. That governor has
no fix-metrics, frequency range, D-Bus or GitHub releases, so the GPU Usage and Performance pages, those Tuning
sections, the <code>down-events</code> field and the update check are hidden and the GPU load sensor stays
unavailable. Everything else, including <code>[timing]</code> and <code>[frequency-thresholds]</code>, works the
same.</p>

<h2>Privileges</h2>
<p>The app runs as your normal user. Only four things need root and go through <code>pkexec</code>:
the backup, the write of <code>config.toml</code>, the <code>systemctl</code> actions and the safe-point test
(<code>busctl</code> on the root-only TestMode interface). The password is handled
by the desktop's polkit agent; the app never sees it.</p>

<h2>Install and update</h2>
<p>The release tarball contains <code>install.sh</code>. It installs the app for your user only (a private venv
with PyQt6 under <code>~/.local/share/bc250-governor-manager</code>, the launcher
<code>~/.local/bin/bc250-governor-manager</code>, a desktop entry and the icon), so it appears in the
application menu. Run it again from a newer release to update, <code>./install.sh --uninstall</code> removes it.
Nothing is layered with rpm-ostree and the governor's config is never touched.</p>

<h2>Links</h2>
<ul>
<li>This app: <a href="%4">%4</a></li>
<li>The governor (filippor, SMU branch): <a href="%5">%5</a></li>
</ul>
<p>Licensed under the GNU General Public License v3.0 or later. The Inter font (SIL Open Font License) is bundled.</p>
""")
    return fmt(text, APP_NAME, str(__version__), config, REPO_URL, GOVERNOR_URL)


class HelpView(QTextBrowser):
    def __init__(self, config_path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setHtml(help_html(config_path))
