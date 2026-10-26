# SPDX-License-Identifier: GPL-3.0-or-later
"""Help page content."""

from __future__ import annotations

from PyQt6.QtWidgets import QTextBrowser, QWidget

from . import APP_NAME, HELIXSR_RELEASES_URL, HELIXSR_URL, OPTISCALER_URL, REPO_URL, __version__
from .acquire import FALLBACK_VERSION
from .backend import HELIXSR_DLL, INI, KERNELS, SECOND_UPSCALER_DLL, UPSCALER_DLL, WEIGHTS


def help_html(payload_dir: str, deployments_file: str,
              work_dir: str = "~/.local/share/bc250-upscaler/work") -> str:
    """The Help page. The paths and URLs are filled into the paragraphs afterwards."""
    values = dict(app_name=APP_NAME, version=__version__, helixsr_url=HELIXSR_URL, releases_url=HELIXSR_RELEASES_URL,
                  optiscaler_url=OPTISCALER_URL, repo_url=REPO_URL, upscaler_dll=UPSCALER_DLL, helixsr_dll=HELIXSR_DLL,
                  weights=WEIGHTS, kernels=KERNELS, ini=INI, payload_dir=payload_dir,
                  deployments_file=deployments_file, work_dir=work_dir, second=SECOND_UPSCALER_DLL,
                  fallback=FALLBACK_VERSION)
    parts = [
        '<h1>{app_name} <small>v{version}</small></h1>',
        ('<p>Installs <a href="{helixsr_url}">HelixSR</a>, the FSR/DLSS hybrid upscaler for Direct3D 12 tuned '
         "for the <b>AMD BC-250</b>, into games on <b>Bazzite</b>. HelixSR runs NVIDIA's DLSS Model E network "
         'as plain compute shaders on an AMD GPU; games talk to it as FSR 3.1. This app only copies, renames '
         'and deletes files inside the game folders you point it at and inside its own payload folder. Nothing'
         ' on the system is touched, no root is needed.</p>'),
        '<h2>How HelixSR is installed (what the app does for you)</h2>',
        '<ol>',
        ("<li>The game's FSR 3.1 upscaler DLL, <code>{upscaler_dll}</code> (Unreal Engine games keep it under "
         '<code>Engine/Plugins/…/ThirdParty/Win64</code>) or <code>{helixsr_dll}</code>, is renamed to '
         '<code>*.original.dll</code>. That file is the backup <i>and</i> is still used: HelixSR forwards '
         'frame generation and other FidelityFX effects to it.</li>'),
        ("<li>HelixSR's <code>{helixsr_dll}</code> is copied in under the game's original file name, together "
         'with <code>{weights}</code> and <code>{kernels}</code>.</li>'),
        '<li>Optionally a <code>{ini}</code> is written next to it.</li>',
        ('<li>Start the game normally and select <b>AMD FSR</b> as the upscaler. No launch options are '
         'needed.</li>'),
        '</ol>',
        ("<p><b>Remove</b> undoes it: HelixSR's files are deleted and the <code>.original.dll</code> gets its "
         'name back.</p>'),
        '<h2>Setup</h2>',
        ("<p><b>Download and build</b> does the HelixSR README's setup for you: it fetches the latest HelixSR "
         'release zip from <a href="{releases_url}">GitHub</a> (2 MB) and checks its SHA-256, reads the exact '
         "sources and SHA-256 sums the release's own setup scripts pin, downloads what this PC still needs <i>in parallel</i> and verifies "
         "each file: NVIDIA's DLSS 310.7.0 DLL (59 MB, from NVIDIA's GitHub under NVIDIA's license), "
         "Microsoft's DirectX Shader Compiler (25 MB) and, on read-only systems such as Bazzite, a portable "
         'Python (67 MB, with numpy). Then it builds the network with its output on the page (5-6 minutes, the '
         'shader compiler runs through your Proton) and the result is imported as the payload: for HelixSR 1.x '
         'it runs <code>helixsr-setup.sh --yes</code>, which builds <code>{weights}</code> and '
         '<code>{kernels}</code> (from 1.8 on inside the DLL); for HelixSR 2.x it runs what that script runs '
         "before its game installer, HelixSR's own builder, so the setup never installs into your games. "
         'Frame generation is not built (<code>--no-fg</code>). '
         'The DLSS DLL is deleted afterwards. Everything is downloaded into <code>{work_dir}</code> and '
         "<code>~/.local/share/HelixSR</code> (the script's own cache, reused next time).</p>"),
        ('<p>If a game you own already ships DLSS 310.7.0, tick <b>Use a nvngx_dlss.dll already on this PC</b>'
         ' and let <b>Find in Steam</b> locate it (checksums are compared, only the exact build HelixSR pins '
         "is offered): that skips NVIDIA's download. The downloads are not what takes time; the build is.</p>"),
        ('<p><b>Releases</b> compares the payload with the latest HelixSR release on GitHub, at start (one small '
         'request, can be turned off) or with <b>Check now</b>. A newer HelixSR shows on the Overview too; '
         '<b>Download and build</b> again updates the payload; afterwards the app offers to put the new build into '
         'the games that have an older one (<b>Update older games</b> on the Overview does the same). This app '
         'itself is updated through the BC250 Bazzite Suite portal.</p>'),
        ('<p><b>Download and build</b> does not start with less than about 1.5 GB free where it downloads and '
         'builds.</p>'),
        ('<p>The app sets up HelixSR 1.x and 2.x. When a later major version is out, <b>Releases</b> says so and '
         'the app keeps getting the newest release it supports.</p>'),
        ('<p><b>Version</b> picks what <b>Download and build</b> gets: the latest HelixSR release, or HelixSR '
         "{fallback}, the version HelixSR's developer recommends when the latest one does not work for you (please"
         ' then open an issue at <a href="{helixsr_url}/issues">HelixSR</a> with the <code>helixsr.log</code> from '
         'the game folder). Switching builds the network files for that version and replaces the payload; deploy '
         'again per game afterwards (the Overview marks them <i>Older build</i> or <i>Newer build</i>). The '
         "<code>{ini}</code> page grays out the settings the payload's HelixSR version does not read.</p>"),
        ("<p>From HelixSR 1.8.0 on, the setup builds the network into HelixSR's DLL: there are no separate "
         '<code>{weights}</code> and <code>{kernels}</code>, and Deploy copies only the DLL (and the ini). '
         'Network files left next to it by an older release are removed.</p>'),
        '<h2>Overview</h2>',
        ('<p>The <b>payload</b> is your copy of a HelixSR release: the DLL, the two network files and the ini,'
         ' kept in <code>{payload_dir}</code>. It is filled by the Setup page, or by hand: extract a release, '
         'run <code>./helixsr-setup.sh</code> in that folder once and <b>Import release folder…</b>. The '
         "network files contain NVIDIA's network: they are for your own PC and are never part of this app or "
         'its releases. <b>Import release zip…</b> takes the download as is, but the network files are still '
         'missing until the setup has run and the folder is imported.</p>'),
        ('<p><b>Deployments</b> lists every place the app put HelixSR, with its live state: <i>In place</i>, '
         '<i>Older build</i> (the payload has been updated since; deploy again to update the game), <i>Network'
         ' files missing</i>, <i>Original restored</i> (a game update or Steam put the game\'s own DLL back) or '
         '<i>Removed</i>. The list is kept in <code>{deployments_file}</code>; <b>Forget entry</b> drops a line '
         'without touching the game.</p>'),
        ('<p><b>Update older games</b> puts the payload\'s HelixSR into every deployment marked <i>Older build</i> '
         'or <i>Original restored</i>. The <code>{ini}</code> there is kept, and so is the game\'s backup. A game '
         'that is running is left alone. Deployments of a newer build (the fallback) are not touched.</p>'),
        '<h2>Games</h2>',
        ('<p>Every Steam game on this PC, each looked through in the background for an AMD FSR 3.1 DLL. The games '
         'that have one come first: <i>Not installed</i>, <i>HelixSR x.y.z installed</i>, an older build with '
         '<i>is available</i>, or <i>The game put its own DLL back</i>. The others are grayed out; games that only '
         'offer DLSS, XeSS or FSR 2 can still use HelixSR through OptiScaler: <b>Open on Deploy page</b>.</p>'),
        ('<p><b>Run with HelixSR</b> (or a double-click) puts HelixSR into the game when it is not there, again '
         "after a game update put the game's own DLL back, or when the payload has a newer build, then starts the "
         'game through Steam. It asks before the first install into a game, and does nothing while the game runs: '
         'HelixSR goes in before the game starts. Choose <b>AMD FSR</b> in the game.</p>'),
        '<h2>Deploy</h2>',
        ('<p>Pick a game from the Steam libraries found on this PC (<code>steamapps/common</code> of every '
         'library in <code>libraryfolders.vdf</code>) or <b>Browse…</b> to any folder (Heroic, Lutris, '
         "Bottles). The folder is scanned for FSR 3.1 upscaler DLLs; each one shows whether it is the game's "
         'own file, HelixSR, and whether the network files are next to it. Select the one the game loads '
         '(usually the only one) and <b>Deploy HelixSR</b>.</p>'),
        ('<p><b>Stand-alone folder for OptiScaler</b> is for games that do not ship FSR 3.1 as a separate DLL '
         '(DLSS, XeSS, FSR 2 / 3.0 games). <a href="{optiscaler_url}">OptiScaler</a> routes their upscaler '
         'calls to an FSR 3.1 DLL. The app writes HelixSR under both FidelityFX names into a folder of its own'
         ' (default <code>&lt;game&gt;/HelixSR</code>) and shows the <code>OptiScaler.ini</code> lines that '
         'point OptiScaler there (Windows paths; <code>Z:</code> is the Linux root under Proton). Install '
         'OptiScaler for the game as its documentation describes, paste the lines, and pick <b>FSR HelixSR '
         "(3.1.5)</b> in OptiScaler's FFX Upscaler menu.</p>"),
        ("<p><b>Install OptiScaler next to the game's .exe</b> (on when the payload has OptiScaler: HelixSR 1.7.0 "
         'to 1.8.1 ship the official one, 1.9.0 and newer do not; the fallback on the Setup page brings it, and the '
         'payload keeps it when you switch back to the latest): the app does that part too. Scan finds the folder of the game\'s .exe; '
         "OptiScaler goes there as <code>dxgi.dll</code> (or under the name of an OptiScaler the game already "
         'has) with <code>fakenvapi</code>, and its <code>OptiScaler.ini</code> points at the HelixSR folder. '
         "Start the game and select <b>DLSS</b>. A file of the game it replaces, and an <code>OptiScaler.ini</code> "
         "the game already had, are kept in the HelixSR folder's <code>backup</code>; <b>Remove</b> puts them "
         'back. Under Proton OptiScaler only loads with <code>WINEDLLOVERRIDES="dxgi=n,b"</code> in the '
         "game's Steam launch options, so for a Steam game the app adds it to them. Steam writes its settings "
         'again when it closes, so the app asks to close Steam for this and starts it again afterwards; in Game '
         'Mode Steam stays open and the line is copied to the clipboard for the game\'s Properties in Steam. '
         '<b>Remove</b> puts the launch options back, unless you changed them since.</p>'),
        ("<p><b>Second upscaler</b> (optional, OptiScaler folder only): pick another FidelityFX upscaler DLL, for "
         "example AMD's <code>amd_fidelityfx_upscaler_dx12.dll</code> with FSR 4. It is copied into the folder as "
         "<code>{second}</code> and <code>UpscalerDll</code> in its helixsr.ini points at it, so OptiScaler's FFX "
         "Upscaler menu lists its upscalers after HelixSR and the one you pick runs in that DLL.</p>"),
        ("<p>Deploying again over an existing deployment updates HelixSR's files and keeps the game's "
         'original.</p>'),
        '<h2>helixsr.ini</h2>',
        '<table cellpadding="4" cellspacing="0" border="1" width="100%">',
        '<tr><th>Section</th><th>Key</th><th>Default</th><th>Meaning</th></tr>',
        ("<tr><td>[Sharpening]</td><td>Mode</td><td>off</td><td><i>off</i> (as DLSS), <i>game</i> = the game's"
         ' FSR sharpness (or Sharpness if it sends none), <i>override</i> = always Sharpness</td></tr>'),
        ('<tr><td>[Sharpening]</td><td>Sharpener</td><td>off</td><td>HelixSR 1.8+: <i>off</i> (as DLSS 4), '
         "<i>nvidia</i> = NVIDIA's sharpening filter, <i>rcas</i> = AMD FSR's</td></tr>"),
        '<tr><td>[Sharpening]</td><td>Sharpness</td><td>0.3</td><td>0-1, FidelityFX RCAS scale</td></tr>',
        ("<tr><td>[Sharpening]</td><td>UseGameSlider</td><td>false</td><td>HelixSR 1.8+: follow the game's "
         'sharpness slider when it has one</td></tr>'),
        ('<tr><td>[Sharpening]</td><td>MotionAdaptive, MotionThreshold, MotionLimit, '
         'MotionReduction</td><td>true, 2, 16, 0.6</td><td>Less sharpening on fast-moving pixels: where the '
         'reduction starts and is complete (output pixels per frame), and how much is removed</td></tr>'),
        ('<tr><td>[ModelE]</td><td>Enabled</td><td>true</td><td>Run the Model E network; otherwise a '
         'placeholder upscale</td></tr>'),
        ('<tr><td>[ModelE]</td><td>Network</td><td>auto</td><td><i>auto</i>: the main network at every ratio '
         "(about 30 % faster than NVIDIA's Ultra Performance network on GPUs without matrix cores); "
         '<i>nvidia</i>: as DLSS selects; <i>main</i> / <i>ultraperformance</i></td></tr>'),
        ('<tr><td>[ModelE]</td><td>InvertJitter, InvertMotionVectors</td><td>false</td><td>For games whose '
         'jitter or motion vectors come out mirrored</td></tr>'),
        ('<tr><td>[ModelE]</td><td>MotionVectorFrontEnd</td><td>false</td><td>Convert render-resolution motion'
         " vectors to display resolution first (used anyway when the game's vectors include the "
         'jitter)</td></tr>'),
        ('<tr><td>[Log]</td><td>Enabled</td><td>true</td><td>Writes <code>helixsr.log</code> next to the DLL; '
         'it names the network that runs and reports missing network files</td></tr>'),
        ('<tr><td>[Forwarding]</td><td>Dll</td><td>(auto)</td><td>DLL for the other FidelityFX effects (frame '
         'generation): <code>amd_fidelityfx_dx12.original.dll</code> if present, else '
         '<code>amd_fidelityfx_framegeneration_dx12.dll</code></td></tr>'),
        ('<tr><td>[Forwarding]</td><td>UpscalerDll</td><td>(empty)</td><td>A second FidelityFX upscaler DLL '
         "(e.g. AMD's with FSR 4) listed after HelixSR in OptiScaler's menu</td></tr>"),
        '</table>',
        ("<p>The page edits these values and shows the resulting file; the comments of the payload's own "
         '<code>{ini}</code> are kept, only values change. <b>Save as payload default</b> makes it the file '
         'Deploy starts from; <b>Write to game</b> replaces the ini of a chosen deployment. Sharpening off '
         'costs nothing; on, about 0.4 ms at 4K on the BC-250.</p>'),
        '<h2>Good to know</h2>',
        '<ul>',
        ('<li>HelixSR is Direct3D 12 only and for RDNA 1 and newer; it is developed and tested on the BC-250 '
         '(gfx1013, Mesa RADV, Proton). Vulkan games are not supported.</li>'),
        ("<li>Steam verifies game files on updates and may put the game's own DLL back. The Overview then "
         'shows <i>Original restored</i> and the backup stays; <b>Run with HelixSR</b> or <b>Update older '
         'games</b> puts HelixSR back.</li>'),
        ('<li>Per-stage GPU timings: launch option <code>HELIXSR_PROFILE=1 %command%</code> writes them to '
         '<code>helixsr.log</code>.</li>'),
        ('<li>Payload: <code>{payload_dir}</code>. Deployments: <code>{deployments_file}</code>. Window size '
         'and page are kept per user. Removing the app with <code>install.sh --uninstall</code> leaves the '
         'payload alone.</li>'),
        '</ul>',
        ('<p>Source and issues: <a href="{repo_url}">{repo_url}</a>. HelixSR itself: <a '
         'href="{helixsr_url}">{helixsr_url}</a> (HelixSR Freeware License; this app ships none of it).</p>'),
    ]
    return "\n".join(part.format(**values) for part in parts) + "\n"

class HelpView(QTextBrowser):
    def __init__(self, payload_dir: str, deployments_file: str, work_dir: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setHtml(help_html(payload_dir, deployments_file, work_dir) if work_dir
                     else help_html(payload_dir, deployments_file))
