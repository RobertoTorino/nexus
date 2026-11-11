# Icons

The icons of the project, per suite, and where each is used. Pictures are shown from their own files; icons drawn
in code are rendered to `bc250-bazzite/docs/design/icons/`. Written by `tools/make_icons.py`: change the listing
there and run it. The paths of the BC250 Bazzite Suite's section are relative to its folder, `bc250-bazzite/`.

## BC250 Bazzite Suite

### The suite's icon

| Icon | File | Used for |
| --- | --- | --- |
| <img src="bc250-bazzite/portal/images/bc250-bazzite-suite.webp" width="48" alt=""> | `portal/images/bc250-bazzite-suite.webp` (512 px) | The portal's header, as large as a tile's icon (a click opens the wiki), its window icon, and the portal's release in Nexus Release Tool. |
| <img src="bc250-bazzite/portal/images/bc250-bazzite-suite-1024.webp" width="48" alt=""> | `portal/images/bc250-bazzite-suite-1024.webp` | The portal's intro. |
| <img src="bc250-bazzite/portal/images/bc250-bazzite-suite-128.png" width="48" alt=""> | `portal/images/bc250-bazzite-suite-128.png` | The portal's menu entry and Desktop icon. |
| <img src="bc250-bazzite/portal/images/apps/portal.webp" width="48" alt=""> | `portal/images/apps/portal.webp` (128 px) | The portal's own tile. |
| <img src="bc250-bazzite/docs/images/wiki-icon.webp" width="48" alt=""> | `docs/images/wiki-icon.webp`, `.png` | The wiki's header logo, its home page's footer and its favicon. |

### The category icons

Every app has the icon of its category: `icons/categories.toml` assigns them, `tools/sync_icons.py` copies each
category's icon (`icons/<category>/`, at 1024, 512, 256 and 128 px) to these places:

- `apps/<app>/images/<icon>.webp` (512 px): the app's window header (96 px), its window and tray icon, and the
  logo at the top of its chapter in the wiki.
- `apps/<app>/images/<icon>-128.png`: the app's menu entry and Desktop icon.
- `portal/images/apps/<key>.webp` (256 px): the app's icon in a tile's menu and in the notice, and in the wiki's app
  tables.
- `portal/images/categories/<category>.webp` (512 px): the app's tile in the portal, drawn large.
- In the wiki, the category's own icon (256 px) in the table of categories.

| Icon | Category | Apps |
| --- | --- | --- |
| <img src="bc250-bazzite/icons/gaming/gaming-128.png" width="64" alt=""> | Gaming | RPCS3 Manager (`rpcs3`)<br>Console Link (`consoles`)<br>BC-250 XB Remote Play (`clb`)<br>shadPS4 Manager (`shadps4`)<br>Bazzite DatStation (`datstation`)<br>PPSSPP Manager (`ppsspp`)<br>PCSX2 Manager (`pcsx2`)<br>Xenia Manager (`xenia`)<br>Vita3K Manager (`vita3k`) |
| <img src="bc250-bazzite/icons/graphics/graphics-128.png" width="64" alt=""> | Graphics | BC-250 Upscaler Manager (`upscaler`)<br>BC-250 ACE Queues (`ace`)<br>BC-250 Mesh Shaders (`mesh`) |
| <img src="bc250-bazzite/icons/sustainable/sustainable-128.png" width="64" alt=""> | Sustainable | BC-250 Bazzite Test (`check`)<br>BC-250 GPU Manager (`gpu`)<br>BC-250 CU Bisect (`compute`)<br>CU Unlock (the CU Bisect app's Unlock) (`cu-unlock`)<br>BC-250 Cores Bisect (`cores`)<br>Cores Unlock (the Cores Bisect app's Unlock) (`cores-unlock`)<br>BC-250 GPU OC Bisect (`oc`)<br>BC-250 Persistent ACPI (`acpi`)<br>BC-250 Memory Manager (`vram`)<br>BC-250 Fan Control (`fan`) |
| <img src="bc250-bazzite/icons/utilities/utilities-128.png" width="64" alt=""> | Utilities | System Overlay (`overlay`)<br>BC-250 BIOS Reader (`bios`)<br>BC-250 USB Wi-Fi (`wdriver`)<br>BC-250 CEC Manager (`cec`)<br>Bazzite SFTP Tools (`sftp`)<br>USB IPS3.5 (`ips35`)<br>USB HD Cam (`hdcam`)<br>USB HD Control (`hdcontrol`)<br>SSD Check (`ssd`) |

### The portal's symbols

Drawn with QPainter in `portal/bc250_portal/glyphs.py`, in the theme's text color (shown here on Gunmetal) or red.

| Icon | Name | Used for |
| --- | --- | --- |
| <img src="bc250-bazzite/docs/design/icons/portal-install.png" width="48" alt=""> | Install | Install in a tile's menu: an arrow down into a tray. |
| <img src="bc250-bazzite/docs/design/icons/portal-install-update.png" width="48" alt=""> | Install, update | The same entry, Update, in red when an update is waiting. |
| <img src="bc250-bazzite/docs/design/icons/portal-reinstall.png" width="48" alt=""> | Reinstall | Reinstall in the menu of an app whose version the portal does not know (red), a circular arrow. |
| <img src="bc250-bazzite/docs/design/icons/portal-reinstall-badge.png" width="48" alt=""> | Reinstall badge | On a tile in the portal: the app needs a reinstall. |
| <img src="bc250-bazzite/docs/design/icons/portal-uninstall.png" width="48" alt=""> | Uninstall | Uninstall in a tile's menu: a waste bin. |

### Icons in the apps

| Icon | File | Used for |
| --- | --- | --- |
| <img src="bc250-bazzite/apps/pcsx2/pcsx2_manager/arrow-down.svg" width="16" alt=""> | `apps/<app>/<package>/arrow-down.svg` | The arrow of a choice box in PCSX2 Manager, RPCS3 Manager and shadPS4 Manager (a copy in each). |

### The desktop style's icons

Icons the apps take from the desktop's style or icon theme, so they look different on every desktop; shown here as
Qt's Fusion style draws them.

| Icon | Name | Used for |
| --- | --- | --- |
| <img src="bc250-bazzite/docs/design/icons/qt-warning.png" width="48" alt=""> | `SP_MessageBoxWarning` | BC-250 Bazzite Test: a warning in the results; the warning before a run. |
| <img src="bc250-bazzite/docs/design/icons/qt-information.png" width="48" alt=""> | `SP_MessageBoxInformation` | BC-250 Bazzite Test: an info result. Nexus Deps: the About button. |
| <img src="bc250-bazzite/docs/design/icons/qt-reload.png" width="48" alt=""> | `view-refresh`, else `SP_BrowserReload` | Nexus Deps: the Check button. |

### Material Design icons in the wiki

Drawn by MkDocs Material in the wiki's colors.

| Icon | Name | Used for |
| --- | --- | --- |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/stethoscope.svg" width="24" alt=""> | `material-stethoscope` | Home: the card "Diagnostics". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/speedometer.svg" width="24" alt=""> | `material-speedometer` | Home: the card "Tuning". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/lock-open-variant.svg" width="24" alt=""> | `material-lock-open-variant` | Home: the card "Unlocks". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/gamepad-variant.svg" width="24" alt=""> | `material-gamepad-variant` | Home: the cards "Gaming" and "PlayStation". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/television.svg" width="24" alt=""> | `material-television` | Home: the card "Living room". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/download.svg" width="24" alt=""> | `material-download` | Home: the Download button. |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/tray-arrow-down.svg" width="24" alt=""> | `material-tray-arrow-down` | The page icon of Install. |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/eye-off-outline.svg" width="24" alt=""> | `material-eye-off-outline` | The page icon of Privacy. |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/shield-lock-outline.svg" width="24" alt=""> | `material-shield-lock-outline` | The page icon of Security. |

### Symbols in text

Characters of the font, used as icons in labels and buttons.

| Symbol | App | Used for |
| --- | --- | --- |
| ✔ ⚠ | BC-250 Persistent ACPI | The state: installed, incomplete. |
| ▶ | BC-250 BIOS Reader | The selected prompt. |
| → ← ↑ ↓ | BC-250 BIOS Reader | The keys in the legend. |
| ▶ ■ ◀ | BC-250 Bazzite Test | Run all tests, Stop, Back. |
| ⚠ | BC-250 Bazzite Test | The integrity banner, a score's warnings. |
| 💡 | BC-250 Bazzite Test | A hint in the findings. |
| ✔ • ! ✖ | BC-250 Bazzite Test | In-game: the checks' ok, info, warning, error. |
| ↓ ↑ | BC-250 Bazzite Test | Live status: download and upload. |
| 🎮 | BC-250 Bazzite Test | Live status: the game that runs. |
| ✕ | BC-250 Bazzite Test | The round close button (drawn, not a font glyph). |
| ✖ ⚠ ● | BC-250 GPU Manager | Safe points: an error, a warning, a test that runs. |
| ✓ ✗ | Console Link | The controller test's checks. |
| △ ○ □ ◇ ◆ ★ | Bazzite DatStation | The front page's features: Quiz, History, Region Codes, User Guides, PS News, Scores & Trophies. |
| ★ | Bazzite DatStation | Stars, a perfect round, trophies. |
| ← | Bazzite DatStation | Back. |
| ✓ ! | USB HD Cam | A check found or missing. |
| ↑ ↓ › | sFTP Tools | Uploads and downloads on the Transfers card; a folder that A opens. |
| ✓ ↓ ↑ | Smart Screen | A value on the screen; the network tile: download and upload. |
| ✓ ! | USB HD Control | A check known or not. |
| △ □ ✕ ○ | USB HD Control | The face buttons. |
| ↓ ↑ | USB IPS3.5 | The network tile: download and upload. |
| ↓ ↑ | System Overlay | Network: download and upload. |
| ✓ ✗ | Nexus Deps | CVE: none found, found. |
| ⚠ ✓ ✗ | Bazzite SFTP Tools | Password: a warning, requirements met, not met. |
| ← ↑ ↓ | Bazzite SFTP Tools | Download; uploads and downloads in the transfer queue. |
| ↑ ↓ | Nexus Release Tool | Earlier commands, in the command line's placeholder. |
| ● | Every app on core | The dot of a status box (`bc250_core/widgets.py`). |
| ● | Portal | Outside the suite. |
| ✓ ✗ | Nexus Installer Tests | A test passed, failed. |

## Bazzite Console Suite

### Suite artwork

| Icon | File | Used for |
| --- | --- | --- |
| <img src="bazzite-console/icons/bazzite-console-128.png" width="48" alt=""> | `icons/bazzite-console-<size>.png` (1024, 512, 256 and 128 px) | The suite's PlayStation 5 artwork, the source for its portal and wiki icons. |
| <img src="bazzite-console/portal/images/bazzite-console-suite.webp" width="48" alt=""> | `portal/images/bazzite-console-suite.webp` (512 px) | The portal header, window icon and release in Nexus Release Tool. |
| <img src="bazzite-console/portal/images/bazzite-console-suite-1024.webp" width="48" alt=""> | `portal/images/bazzite-console-suite-1024.webp` | The portal's intro. |
| <img src="bazzite-console/portal/images/bazzite-console-suite-128.png" width="48" alt=""> | `portal/images/bazzite-console-suite-128.png` | The portal's menu entry and Desktop icon. |
| <img src="bazzite-console/portal/images/apps/portal.webp" width="48" alt=""> | `portal/images/apps/portal.webp` (128 px) | The portal's own tile. |
| <img src="bazzite-console/docs/images/wiki-icon.png" width="48" alt=""> | `docs/images/wiki-icon.png` (256 px) | The wiki favicon. |
| <img src="bazzite-console/docs/images/wiki-icon.webp" width="48" alt=""> | `docs/images/wiki-icon.webp` | The wiki header and home-page footer. |

### Category artwork

Each category has its own PlayStation 5 artwork. `tools/sync_icons.py` writes the copies used by the apps and portal.

| Icon | File | Used for |
| --- | --- | --- |
| <img src="bazzite-console/icons/gaming/gaming-128.png" width="48" alt=""> | `icons/gaming/` | The Gaming category. |
| <img src="bazzite-console/icons/graphics/graphics-128.png" width="48" alt=""> | `icons/graphics/` | The Graphics category. |
| <img src="bazzite-console/icons/media/media-128.png" width="48" alt=""> | `icons/media/` | The Media category: the portal's launcher cards for YouTube, Twitch, X, Instagram, Discord, TikTok, WhatsApp, Netflix, Spotify and Stremio. |
| <img src="bazzite-console/icons/sustainable/sustainable-128.png" width="48" alt=""> | `icons/sustainable/` | The Sustainable category. |
| <img src="bazzite-console/icons/utilities/utilities-128.png" width="48" alt=""> | `icons/utilities/` | The Utilities category: SFTP Tools (`sftp`), USB HD Cam (`hdcam`), USB HD Control (`hdcontrol`) and SSD Check (`ssd`). |

### Bazzite Test icons

Bazzite Test uses the Sustainable category icon, as selected in `icons/categories.toml`.

| Icon | File | Used for |
| --- | --- | --- |
| <img src="bazzite-console/icons/sustainable/sustainable-128.png" width="48" alt=""> | `icons/sustainable/` | The Sustainable category. |
| <img src="bazzite-console/apps/bazzite/images/bazzite-test.webp" width="48" alt=""> | `apps/bazzite/images/bazzite-test.webp` | Bazzite Test's window, tray and wiki icon. |
| <img src="bazzite-console/portal/images/apps/bazzite.webp" width="48" alt=""> | `portal/images/apps/bazzite.webp` | The Bazzite Test tile and wiki table icon. |
| <img src="bazzite-console/portal/images/categories/sustainable.webp" width="48" alt=""> | `portal/images/categories/sustainable.webp` | The app's category tile. |

### Wiki home images

| Image | File | Used for |
| --- | --- | --- |
| <img src="bazzite-console/docs/images/home/console.webp" width="96" alt=""> | `docs/images/home/console.webp` | The PlayStation 5 console on the wiki home page. |
| <img src="bazzite-console/docs/images/home/controller.webp" width="96" alt=""> | `docs/images/home/controller.webp` | The game controller on the wiki home page. |

## Windows Portable Suite

### The suite's icon

| Icon | File | Used for |
| --- | --- | --- |
| <img src="windows-portable/icons/windows-portable-256.png" width="48" alt=""> | `windows-portable/icons/windows-portable-<size>.png` (1024, 512, 256 and 128 px) | The icon of the Windows Portable Suite, the owner's drawing (26-10-2026): the set its portal's and wiki's copies are made from. |
| <img src="windows-portable/icons/windows-portable-white.png" width="48" alt=""> | `windows-portable/icons/windows-portable-white.png` (1024 x 514) | The white handheld, the owner's picture (29-10-2026, cropped to the handheld): the hero of the suite's wiki home, as the board is the BC250 wiki's. |
| <img src="windows-portable/apps/test/images/windows-portable-test.webp" width="48" alt=""> | `windows-portable/apps/test/images/windows-portable-test.webp` (512 px), `-128.png` | Windows Portable Test, the suite's test app: the suite's icon (the test app is the suite's base, as BC-250 Bazzite Test is the BC250 suite's), its window header and window icon, and its Start-menu shortcut. Lossless copies of the drawing, written by this tool. |
| <img src="windows-portable/portal/images/windows-portable-suite.webp" width="48" alt=""> | `windows-portable/portal/images/windows-portable-suite.webp` (512 px), `-128.png` | The Windows Portable Suite's portal: its window icon and its Start-menu shortcut, and the portal's release in Nexus Release Tool. Lossless copies of the drawing, written by this tool. |
| <img src="windows-portable/docs/images/wiki-icon.webp" width="48" alt=""> | `windows-portable/docs/images/wiki-icon.webp`, `.png` (256 px) | The suite's wiki: the header logo (`.webp`) and the favicon (`.png`), written by this tool. |
| <img src="windows-portable/docs/images/home/device.webp" width="48" alt=""> | `windows-portable/docs/images/home/device.webp` (1024 x 514) | The suite's wiki home: the handheld under the headline, a WebP copy of the owner's white handheld. |
| <img src="windows-portable/docs/images/home/portal.webp" width="48" alt=""> | `windows-portable/docs/images/home/portal.webp` (1280 x 720) | The suite's wiki home, One portal for every app: the portal at the Ally's 1280 x 720, rendered offscreen with the suite's apps.toml (Windows Portable Test installed), as WebP. |
| <img src="windows-portable/docs/images/apps/test.webp" width="48" alt=""> | `windows-portable/docs/images/apps/<key>.webp` (256 px) | An app's chapter in the suite's wiki: its icon at the top, a WebP copy of the app's drawing. |
| <img src="windows-portable/portal/images/apps/test.webp" width="48" alt=""> | `windows-portable/portal/images/apps/<key>.webp` (256 px) | The icon on an app's tile in the portal: Windows Portable Test's is the suite's drawing, written by this tool; another app's is a copy of its own icon. |

### The category icons

Every app but Windows Portable Test has the icon of its category: `windows-portable/icons/<category>/` at 1024, 512,
256 and 128 px (PNG), copied by this tool from the portal's `apps.toml` to the app's `images/<app id>.webp` (512 px)
and `-128.png`, its tile `portal/images/apps/<key>.webp` (256 px) and its chapter's icon `docs/images/apps/<key>.webp`
(256 px). A new picture for a category is converted by `tools/sync_icons.py --suite windows-portable` (the
dashboard's Convert icons), as `windows-portable/icons/categories.toml` says: PNG, the Gaming pictures 2:1.

| Icon | Category | Apps |
| --- | --- | --- |
| <img src="windows-portable/icons/gaming/gaming-128.png" width="64" alt=""> | Gaming: the owner's pictures of the handheld (29-10-2026), wide (2:1: 1024 x 512 down to 128 x 64): the tile and the wiki show them as they are, the window, program and Start-menu icons centered on a transparent square | PCSX2 Manager (`pcsx2`)<br>PPSSPP Manager (`ppsspp`)<br>RPCS3 Manager (`rpcs3`)<br>shadPS4 Manager (`shadps4`)<br>Vita3K Manager (`vita3k`)<br>Xenia Manager (`xenia`)<br>Remote Play (`rplay`)<br>DatStation (`datstat`)<br>Upscale Boost (`upscale`) |
| <img src="windows-portable/icons/utilities/utilities-128.png" width="64" alt=""> | Utilities: the owner's picture of a circuit board (01-11-2026), square (1024 x 1024 down to 128 x 128) | USB HD Cam (`hdcam`)<br>BIOS Reader (`bios`)<br>sFTP Tools (`sftp`)<br>Smart Screen (`smart`)<br>Support Checker (`support`)<br>HD Controller (`hdcontrol`)<br>SSD Check (`ssd`) |

### Material Design icons in the wiki

Drawn by MkDocs Material in the wiki's colors.

| Icon | Name | Used for |
| --- | --- | --- |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/stethoscope.svg" width="24" alt=""> | `material-stethoscope` | Home: the card "Sustainable". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/gamepad-variant.svg" width="24" alt=""> | `material-gamepad-variant` | Home: the card "Gaming". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/toolbox.svg" width="24" alt=""> | `material-toolbox` | Home: the card "Utilities". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/download.svg" width="24" alt=""> | `material-download` | Home: the Download button. |

## Nexus

### The Nexus icon

| Icon | File | Used for |
| --- | --- | --- |
| <img src="nexus/images/nexus-256.png" width="48" alt=""> | `nexus/images/nexus-<size>.png` (1024, 512, 256 and 128 px) | The icon of Nexus, the owner's drawing (25-10-2026): the set the copies are made from. |
| <img src="nexus/docs/images/nexus.webp" width="48" alt=""> | `nexus/docs/images/nexus.webp`, `.png` (256 px) | The Nexus page's header logo and its home page's footer (`.webp`), and its favicon (`.png`): the 256 px drawing, transparent (owner, 27-10-2026: no more dark tile), both written by this tool. |
| <img src="nexus/docs/images/nexus-hero.webp" width="48" alt=""> | `nexus/docs/images/nexus-hero.webp` (1024 px) | The Nexus page's home: the icon under the headline, a WebP copy of the 1024 px drawing. |
| <img src="dev/nrt/images/nexus-release-tool.webp" width="48" alt=""> | `dev/<name>/images/<app id>.webp` (512 px), `-128.png` | The Nexus apps (owner, 26-10-2026: a Nexus app takes Nexus's icon, not a category's): Nexus Dashboard (`dev/dash`), Nexus Release Tool (`dev/nrt`), Nexus Demo Recorder (`dev/demo`), Nexus Installer Tests (`dev/itests`), Nexus Sound Lab (`dev/sounds`) and Nexus Deps (`dev/deps`), each its window header and window icon, its menu entry and Desktop icon. Lossless copies of the drawing, written by this tool. |

### Material Design icons on the Nexus page

Drawn by MkDocs Material in the page's colors.

| Icon | Name | Used for |
| --- | --- | --- |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/file-tree.svg" width="24" alt=""> | `material-file-tree` | Home: the card "Nexus". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/view-grid.svg" width="24" alt=""> | `material-view-grid` | Home: the card "A suite". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/application.svg" width="24" alt=""> | `material-application` | Home: the card "An app". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/chip.svg" width="24" alt=""> | `material-chip` | Home: the card "BC250 Bazzite Suite". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/controller.svg" width="24" alt=""> | `material-controller` | Home: the cards "Bazzite Console Suite" and "Windows Portable Suite". |
| <img src="https://cdn.jsdelivr.net/npm/@mdi/svg@7.4.47/svg/download.svg" width="24" alt=""> | `material-download` | Home: the Nexus index button. |
