# Design

The colours of the suite, where they are defined and what they are for. Text colours show a sample sentence in that
colour; background colours (surfaces, fills, borders and lines) show a block. The samples are SVG files in
`docs/design/colors/`. A text sample sits on a dark or a light backdrop, whichever its colour reads on; a colour with
an opacity (written `#rrggbbaa` here, `#aarrggbb` in the Qt code) shows over a checkerboard. The icons are in
[ICONS.md](ICONS.md). Written by `tools/make_design.py`: change the listing there and run it.

## The apps

The theme, the state colours and the style sheets are in `core/bc250_core/theme.py` (bundled per app; the apps that
are not on core yet carry a copy). The theme is one choice for every app: Gunmetal, Silver or Warm.

### Gunmetal (dark, the default)

Text colours:

- `#d9dde2` Text on every surface.

  ![Sample text in #d9dde2](docs/design/colors/text-d9dde2.svg)

- `#82868b` Muted text: versions, hints, placeholders, disabled buttons (text and window mixed).

  ![Sample text in #82868b](docs/design/colors/text-82868b.svg)

- `#ffffff` Text on the accent (selected rows and items).

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

- `#7e97ad` Links.

  ![Sample text in #7e97ad](docs/design/colors/text-7e97ad.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#2b2f34](docs/design/colors/block-2b2f34.svg) | `#2b2f34` | Window and dialog background; the selected tab. |
| ![#22262a](docs/design/colors/block-22262a.svg) | `#22262a` | Text fields, lists, tables, tooltips, progress bars and scroll bars. |
| ![#292d32](docs/design/colors/block-292d32.svg) | `#292d32` | Every other row of a list or table. |
| ![#4a5058](docs/design/colors/block-4a5058.svg) | `#4a5058` | Button face, top of its sheen; scroll bar handles. |
| ![#3b4048](docs/design/colors/block-3b4048.svg) | `#3b4048` | Button face, bottom of its sheen. |
| ![#606872](docs/design/colors/block-606872.svg) | `#606872` | Palette light (the button face 30 % lighter). |
| ![#14171a](docs/design/colors/block-14171a.svg) | `#14171a` | Borders and shadows. |
| ![#7e97ad](docs/design/colors/block-7e97ad.svg) | `#7e97ad` | Accent: selection, focus, hover outline, progress, the selected tab's top edge. |

### Silver (light)

Text colours:

- `#1e2226` Text on every surface.

  ![Sample text in #1e2226](docs/design/colors/text-1e2226.svg)

- `#7a7d81` Muted text: versions, hints, placeholders, disabled buttons.

  ![Sample text in #7a7d81](docs/design/colors/text-7a7d81.svg)

- `#ffffff` Text on the accent.

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

- `#5f7f9c` Links.

  ![Sample text in #5f7f9c](docs/design/colors/text-5f7f9c.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#d5d8dc](docs/design/colors/block-d5d8dc.svg) | `#d5d8dc` | Window and dialog background; the selected tab. |
| ![#eceef0](docs/design/colors/block-eceef0.svg) | `#eceef0` | Text fields, lists, tables, tooltips, progress bars and scroll bars. |
| ![#e2e5e8](docs/design/colors/block-e2e5e8.svg) | `#e2e5e8` | Every other row of a list or table. |
| ![#eef0f2](docs/design/colors/block-eef0f2.svg) | `#eef0f2` | Button face, top of its sheen; scroll bar handles. |
| ![#c4c8cd](docs/design/colors/block-c4c8cd.svg) | `#c4c8cd` | Button face, bottom of its sheen. |
| ![#ffffff](docs/design/colors/block-ffffff.svg) | `#ffffff` | Palette light (the button face 30 % lighter). |
| ![#8d9298](docs/design/colors/block-8d9298.svg) | `#8d9298` | Borders and shadows. |
| ![#5f7f9c](docs/design/colors/block-5f7f9c.svg) | `#5f7f9c` | Accent: selection, focus, hover outline, progress, the selected tab's top edge. |

### Warm (dark)

Text colours:

- `#e3dfd8` Text on every surface.

  ![Sample text in #e3dfd8](docs/design/colors/text-e3dfd8.svg)

- `#8c8984` Muted text: versions, hints, placeholders, disabled buttons.

  ![Sample text in #8c8984](docs/design/colors/text-8c8984.svg)

- `#1b1a18` Text on the accent.

  ![Sample text in #1b1a18](docs/design/colors/text-1b1a18.svg)

- `#b59a6e` Links.

  ![Sample text in #b59a6e](docs/design/colors/text-b59a6e.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#35332f](docs/design/colors/block-35332f.svg) | `#35332f` | Window and dialog background; the selected tab. |
| ![#292826](docs/design/colors/block-292826.svg) | `#292826` | Text fields, lists, tables, tooltips, progress bars and scroll bars. |
| ![#302e2b](docs/design/colors/block-302e2b.svg) | `#302e2b` | Every other row of a list or table. |
| ![#57534d](docs/design/colors/block-57534d.svg) | `#57534d` | Button face, top of its sheen; scroll bar handles. |
| ![#45423d](docs/design/colors/block-45423d.svg) | `#45423d` | Button face, bottom of its sheen. |
| ![#716c64](docs/design/colors/block-716c64.svg) | `#716c64` | Palette light (the button face 30 % lighter). |
| ![#181716](docs/design/colors/block-181716.svg) | `#181716` | Borders and shadows. |
| ![#b59a6e](docs/design/colors/block-b59a6e.svg) | `#b59a6e` | Accent: selection, focus, hover outline, progress, the selected tab's top edge. |

### State colours

The same in every theme: a state shows as a coloured edge or dot on the theme's surfaces.

Text colours:

- `#2e7d32` Green: Passed, a valid entry.

  ![Sample text in #2e7d32](docs/design/colors/text-2e7d32.svg)

- `#c62828` Red: Failed, errors and problems in every app (the emulator managers' status lines, Suite Releases' bad tags, the upscaler's problems, a folder that is missing).

  ![Sample text in #c62828](docs/design/colors/text-c62828.svg)

- `#ffffff` Bright text (palette BrightText); text on the state colours.

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#2e7d32](docs/design/colors/block-2e7d32.svg) | `#2e7d32` | Green, ok: a state's edge or dot; an unlocked CU; a pressed controller button. |
| ![#ef6c00](docs/design/colors/block-ef6c00.svg) | `#ef6c00` | Orange, warn. |
| ![#c62828](docs/design/colors/block-c62828.svg) | `#c62828` | Red, bad; the red buttons of the bisect apps and of Clean up logs. |
| ![#b71c1c](docs/design/colors/block-b71c1c.svg) | `#b71c1c` | The red buttons' hover (the bisect apps). |
| ![#1565c0](docs/design/colors/block-1565c0.svg) | `#1565c0` | Blue, info. |
| ![#3a3f4b](docs/design/colors/block-3a3f4b.svg) | `#3a3f4b` | Grey, neutral. |
| ![#6a1b9a](docs/design/colors/block-6a1b9a.svg) | `#6a1b9a` | Purple, the logo's purple. |
| ![#fdd835](docs/design/colors/block-fdd835.svg) | `#fdd835` | Yellow, running: never confused with a failed (red) state. |
| ![#8b0000](docs/design/colors/block-8b0000.svg) | `#8b0000` | Active red: the GPU Governor's active button. |
| ![#a00000](docs/design/colors/block-a00000.svg) | `#a00000` | Active red on hover. |
| ![#424242](docs/design/colors/block-424242.svg) | `#424242` | Off: a locked CU, a core without a state. |
| ![#1d4f91](docs/design/colors/block-1d4f91.svg) | `#1d4f91` | Steam artwork: the accent when an icon gives no bright colour. |

## The wiki

`docs/stylesheets/suite.css`, Material's slate scheme with the suite's purple.

### Wiki

Text colours:

- `#ffffff` Header, hero, cards and footer text; table headings; buttons on the dark and accent sections.

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

- `#a98bff` Suite soft: links in the dark scheme; hover on the dark section; footer column headings.

  ![Sample text in #a98bff](docs/design/colors/text-a98bff.svg)

- `#c9bfee` Suite mist: card text and footer links.

  ![Sample text in #c9bfee](docs/design/colors/text-c9bfee.svg)

- `#1e1340` Suite deep: a button's text on hover in the dark and accent sections.

  ![Sample text in #1e1340](docs/design/colors/text-1e1340.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#5835ce](docs/design/colors/block-5835ce.svg) | `#5835ce` | Suite primary: Material's primary colour, table headings, page icons, the hero and Get started gradients. |
| ![#7a5ce0](docs/design/colors/block-7a5ce0.svg) | `#7a5ce0` | Primary, light. |
| ![#4426a8](docs/design/colors/block-4426a8.svg) | `#4426a8` | Primary, dark. |
| ![#8a2be2](docs/design/colors/block-8a2be2.svg) | `#8a2be2` | Suite secondary: the accent (hover rings on linked images), the end of the gradients. |
| ![#8a2be21a](docs/design/colors/block-8a2be21a.svg) | `#8a2be21a` | The accent at 10 %. |
| ![#1e1340](docs/design/colors/block-1e1340.svg) | `#1e1340` | Suite deep: header and tabs, the hero's top, the Download button. |
| ![#120c22](docs/design/colors/block-120c22.svg) | `#120c22` | Suite ink: the dark section and the home page's footer; the hero pictures' shadow (45 %). |
| ![#17141f](docs/design/colors/block-17141f.svg) | `#17141f` | Page background (the dark scheme). |
| ![#8b4fd8](docs/design/colors/block-8b4fd8.svg) | `#8b4fd8` | The stage pill under the claim. |
| ![#ffffff](docs/design/colors/block-ffffff.svg) | `#ffffff` | Button background on hover in the dark and accent sections; at 12 % behind the header links. |
| ![#000000](docs/design/colors/block-000000.svg) | `#000000` | The footer's bottom bar (35 %); button shadows (25 %). |

## The apps' own colours

On top of the theme, in the apps' `style.py` or where they are used.

### Gaming apps

Console Link, Console LinkB, Decky, HD Control, PCSX2, PPSSPP, RPCS3, shadPS4, Vita3K and Xenia.

Text colours:

- `#5b93da` Links on a dark window (Console Link, Console LinkB, Decky, PCSX2, PPSSPP, RPCS3, shadPS4, Vita3K, Xenia; HD Control's lit parts).

  ![Sample text in #5b93da](docs/design/colors/text-5b93da.svg)

- `#ffffff` Text on the blue primary button and on the shortcut artwork.

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#0a55b0](docs/design/colors/block-0a55b0.svg) | `#0a55b0` | Gaming blue: the primary button, hover borders; the blue of the gaming apps' icon. |
| ![#2a6cc4](docs/design/colors/block-2a6cc4.svg) | `#2a6cc4` | Gaming blue on hover. |
| ![#08448d](docs/design/colors/block-08448d.svg) | `#08448d` | Gaming blue while pressed. |
| ![#0a55b01a](docs/design/colors/block-0a55b01a.svg) | `#0a55b01a` | Blue tint (10 %): hover, every other table row. |
| ![#0a55b059](docs/design/colors/block-0a55b059.svg) | `#0a55b059` | Blue line (35 %): outlines, a pressed button. |
| ![#80808080](docs/design/colors/block-80808080.svg) | `#80808080` | Disabled (50 % grey). |
| ![#5b93da](docs/design/colors/block-5b93da.svg) | `#5b93da` | HD Control: lit parts of the controller, the chosen card. |
| ![#0b1d3a](docs/design/colors/block-0b1d3a.svg) | `#0b1d3a` | shadPS4 shortcut artwork, top of the gradient. |
| ![#030810](docs/design/colors/block-030810.svg) | `#030810` | shadPS4 shortcut artwork, bottom. |
| ![#16123a](docs/design/colors/block-16123a.svg) | `#16123a` | RPCS3 shortcut artwork, top. |
| ![#05040f](docs/design/colors/block-05040f.svg) | `#05040f` | RPCS3 shortcut artwork, bottom. |
| ![#0d2a4a](docs/design/colors/block-0d2a4a.svg) | `#0d2a4a` | PPSSPP shortcut artwork, top. |
| ![#04080f](docs/design/colors/block-04080f.svg) | `#04080f` | PPSSPP shortcut artwork, bottom. |
| ![#3a2c0d](docs/design/colors/block-3a2c0d.svg) | `#3a2c0d` | Vita3K shortcut artwork, top. |
| ![#0f0b03](docs/design/colors/block-0f0b03.svg) | `#0f0b03` | Vita3K shortcut artwork, bottom. |
| ![#000000](docs/design/colors/block-000000.svg) | `#000000` | Console Link's stream view. |

### DatStation

Text colours:

- `#4da3ef` Links on a dark window.

  ![Sample text in #4da3ef](docs/design/colors/text-4da3ef.svg)

- `#0072ce` Links on a light window.

  ![Sample text in #0072ce](docs/design/colors/text-0072ce.svg)

- `#48b67e` Triangle: the Quiz symbol.

  ![Sample text in #48b67e](docs/design/colors/text-48b67e.svg)

- `#e24c4c` Circle: the History symbol.

  ![Sample text in #e24c4c](docs/design/colors/text-e24c4c.svg)

- `#5aa0ff` Cross: the System Version History symbol.

  ![Sample text in #5aa0ff](docs/design/colors/text-5aa0ff.svg)

- `#e07ab8` Square: the Region Codes symbol.

  ![Sample text in #e07ab8](docs/design/colors/text-e07ab8.svg)

- `#ffd166` The PS News symbol.

  ![Sample text in #ffd166](docs/design/colors/text-ffd166.svg)

- `#ffd700` Gold: the Scores & Trophies symbol, a perfect quiz, gold stars.

  ![Sample text in #ffd700](docs/design/colors/text-ffd700.svg)

- `#c0c0c0` Silver stars.

  ![Sample text in #c0c0c0](docs/design/colors/text-c0c0c0.svg)

- `#cd7f32` Bronze stars.

  ![Sample text in #cd7f32](docs/design/colors/text-cd7f32.svg)

- `#2e7d32` Right answers: the count and the feedback.

  ![Sample text in #2e7d32](docs/design/colors/text-2e7d32.svg)

- `#c62828` Wrong answers: the count; little time left.

  ![Sample text in #c62828](docs/design/colors/text-c62828.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#003791](docs/design/colors/block-003791.svg) | `#003791` | PlayStation blue. |
| ![#0072ce](docs/design/colors/block-0072ce.svg) | `#0072ce` | PlayStation light blue: hover borders. |
| ![#1a85e0](docs/design/colors/block-1a85e0.svg) | `#1a85e0` | Blue on hover. |
| ![#00589f](docs/design/colors/block-00589f.svg) | `#00589f` | Blue while pressed. |
| ![#2e7d32](docs/design/colors/block-2e7d32.svg) | `#2e7d32` | A right answer's button. |
| ![#c62828](docs/design/colors/block-c62828.svg) | `#c62828` | A wrong answer's button. |

### Upscaler

Text colours:

- `#3fc8cf` Links on a dark window.

  ![Sample text in #3fc8cf](docs/design/colors/text-3fc8cf.svg)

- `#0e6f75` Links on a light window.

  ![Sample text in #0e6f75](docs/design/colors/text-0e6f75.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#8a5a2e](docs/design/colors/block-8a5a2e.svg) | `#8a5a2e` | Copper: boxes, white text on them. |
| ![#0e6f75](docs/design/colors/block-0e6f75.svg) | `#0e6f75` | Teal: boxes, white text on them. |
| ![#26a9b0](docs/design/colors/block-26a9b0.svg) | `#26a9b0` | Cyan, the icon's: button outlines. |

### BC-250 Bazzite Test (check)

Text colours:

- `#9aa0a6` Muted: versions, hints, notes, baselines, the in-game and overlay labels.

  ![Sample text in #9aa0a6](docs/design/colors/text-9aa0a6.svg)

- `#e6e6e6` Text in the results and history views, on idle buttons, the overlay's values.

  ![Sample text in #e6e6e6](docs/design/colors/text-e6e6e6.svg)

- `#e8e8e8` Code blocks in the README view.

  ![Sample text in #e8e8e8](docs/design/colors/text-e8e8e8.svg)

- `#d0d0d0` The log; a disabled Clean up logs button.

  ![Sample text in #d0d0d0](docs/design/colors/text-d0d0d0.svg)

- `#1a1a1a` Text on the yellow running button.

  ![Sample text in #1a1a1a](docs/design/colors/text-1a1a1a.svg)

- `#222222` Text on the system score boxes.

  ![Sample text in #222222](docs/design/colors/text-222222.svg)

- `#333333` Labels on the graph's bars.

  ![Sample text in #333333](docs/design/colors/text-333333.svg)

- `#e57373` Error findings; a worse result in the history; a low score.

  ![Sample text in #e57373](docs/design/colors/text-e57373.svg)

- `#ffb74d` Warning findings; a middle score.

  ![Sample text in #ffb74d](docs/design/colors/text-ffb74d.svg)

- `#64b5f6` Info and hint findings.

  ![Sample text in #64b5f6](docs/design/colors/text-64b5f6.svg)

- `#b39ddb` The Show in log link.

  ![Sample text in #b39ddb](docs/design/colors/text-b39ddb.svg)

- `#81c784` A better result in the history.

  ![Sample text in #81c784](docs/design/colors/text-81c784.svg)

- `#66bb6a` Log: success; a full score.

  ![Sample text in #66bb6a](docs/design/colors/text-66bb6a.svg)

- `#ffd600` A score's yellow.

  ![Sample text in #ffd600](docs/design/colors/text-ffd600.svg)

- `#ffa726` Log: warning.

  ![Sample text in #ffa726](docs/design/colors/text-ffa726.svg)

- `#ef5350` Log: error; error labels (also in ACPI, CU Unlock and Cores Unlock).

  ![Sample text in #ef5350](docs/design/colors/text-ef5350.svg)

- `#ce93d8` Log: hint.

  ![Sample text in #ce93d8](docs/design/colors/text-ce93d8.svg)

- `#90a4ae` Log: note.

  ![Sample text in #90a4ae](docs/design/colors/text-90a4ae.svg)

- `#8b4fd8` In-game: the accent text.

  ![Sample text in #8b4fd8](docs/design/colors/text-8b4fd8.svg)

- `#6ec46e` In-game: check ok.

  ![Sample text in #6ec46e](docs/design/colors/text-6ec46e.svg)

- `#e0a53a` In-game: check warning.

  ![Sample text in #e0a53a](docs/design/colors/text-e0a53a.svg)

- `#e06c6c` In-game: check error.

  ![Sample text in #e06c6c](docs/design/colors/text-e06c6c.svg)

- `#b388ff` Overlay: the frame rate and the thin border.

  ![Sample text in #b388ff](docs/design/colors/text-b388ff.svg)

- `#ffffff` README table headings.

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#111418](docs/design/colors/block-111418.svg) | `#111418` | The log; the overlay's background (82 %). |
| ![#1e1f24](docs/design/colors/block-1e1f24.svg) | `#1e1f24` | The results and history views; code blocks in the README view. |
| ![#14161c](docs/design/colors/block-14161c.svg) | `#14161c` | The results card and the score dialog. |
| ![#2a2d36](docs/design/colors/block-2a2d36.svg) | `#2a2d36` | The empty part of a score ring. |
| ![#2a2f37](docs/design/colors/block-2a2f37.svg) | `#2a2f37` | The log's border. |
| ![#3a3f4a](docs/design/colors/block-3a3f4a.svg) | `#3a3f4a` | The borders of the preview, setup, checks and stat cards. |
| ![#555555](docs/design/colors/block-555555.svg) | `#555555` | The screenshot's border. |
| ![#888888](docs/design/colors/block-888888.svg) | `#888888` | README table borders. |
| ![#3a3f4b](docs/design/colors/block-3a3f4b.svg) | `#3a3f4b` | Idle buttons; README table headings. |
| ![#f8fafc](docs/design/colors/block-f8fafc.svg) | `#f8fafc` | The system score boxes. |
| ![#2828f6](docs/design/colors/block-2828f6.svg) | `#2828f6` | The GPU score box. |
| ![#ad1457](docs/design/colors/block-ad1457.svg) | `#ad1457` | System overview: cores. |
| ![#00796b](docs/design/colors/block-00796b.svg) | `#00796b` | System overview: threads. |
| ![#3949ab](docs/design/colors/block-3949ab.svg) | `#3949ab` | System overview: upload speed. |
| ![#6d4c41](docs/design/colors/block-6d4c41.svg) | `#6d4c41` | System overview: NVMe. |
| ![#5e35b1](docs/design/colors/block-5e35b1.svg) | `#5e35b1` | System overview: packages. |
| ![#00838f](docs/design/colors/block-00838f.svg) | `#00838f` | System overview: BIOS; the graph's sixth series. |
| ![#5d4037](docs/design/colors/block-5d4037.svg) | `#5d4037` | The graph's seventh series. |
| ![#e53935](docs/design/colors/block-e53935.svg) | `#e53935` | Clean up logs on hover. |
| ![#a31515](docs/design/colors/block-a31515.svg) | `#a31515` | Clean up logs while pressed. |
| ![#7a4a4a](docs/design/colors/block-7a4a4a.svg) | `#7a4a4a` | Clean up logs, disabled. |

### Other apps

Text colours:

- `#888888` Busy and hint labels in italics (ACPI, CU Bisect, CU Unlock, Cores Bisect, Cores Unlock).

  ![Sample text in #888888](docs/design/colors/text-888888.svg)

- `#ef6c00` An incomplete ACPI override; a CU mask that needs checking.

  ![Sample text in #ef6c00](docs/design/colors/text-ef6c00.svg)

- `#b8b8c8` System Overlay: the names of the values.

  ![Sample text in #b8b8c8](docs/design/colors/text-b8b8c8.svg)

- `#dddddd` Console Link's stream view.

  ![Sample text in #dddddd](docs/design/colors/text-dddddd.svg)

- `#e5a400` SFTP: the password warning.

  ![Sample text in #e5a400](docs/design/colors/text-e5a400.svg)

- `#e74c3c` SFTP: password requirements not met.

  ![Sample text in #e74c3c](docs/design/colors/text-e74c3c.svg)

- `#27ae60` SFTP: password requirements met.

  ![Sample text in #27ae60](docs/design/colors/text-27ae60.svg)

- `#2e9e5b` NetcatGUI: success lines in the session.

  ![Sample text in #2e9e5b](docs/design/colors/text-2e9e5b.svg)

- `#d2691e` NetcatGUI: HTTP and status replies.

  ![Sample text in #d2691e](docs/design/colors/text-d2691e.svg)

- `#d04545` NetcatGUI: error lines.

  ![Sample text in #d04545](docs/design/colors/text-d04545.svg)

- `#3c7dd9` NetcatGUI: header names.

  ![Sample text in #3c7dd9](docs/design/colors/text-3c7dd9.svg)

- `#8a8f98` NetcatGUI: byte counts.

  ![Sample text in #8a8f98](docs/design/colors/text-8a8f98.svg)

- `#ffffff` BIOS Reader: tabs, crumbs, the legend and the selection.

  ![Sample text in #ffffff](docs/design/colors/text-ffffff.svg)

- `#0b2a8a` BIOS Reader: the screen's text.

  ![Sample text in #0b2a8a](docs/design/colors/text-0b2a8a.svg)

- `#10205a` BIOS Reader: subtitles.

  ![Sample text in #10205a](docs/design/colors/text-10205a.svg)

- `#6e6e6e` BIOS Reader: hidden items.

  ![Sample text in #6e6e6e](docs/design/colors/text-6e6e6e.svg)

- `#7d7d8c` BIOS Reader: locked items.

  ![Sample text in #7d7d8c](docs/design/colors/text-7d7d8c.svg)

- `#16803c` Installer Tests: passed.

  ![Sample text in #16803c](docs/design/colors/text-16803c.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#1f3e9c](docs/design/colors/block-1f3e9c.svg) | `#1f3e9c` | BIOS Reader: the bar and the selection. |
| ![#c6c6c6](docs/design/colors/block-c6c6c6.svg) | `#c6c6c6` | BIOS Reader: the screen. |
| ![#0d47a1](docs/design/colors/block-0d47a1.svg) | `#0d47a1` | HDMI-CEC: the adapter box. |
| ![#000000](docs/design/colors/block-000000.svg) | `#000000` | HDMI-CEC: the display box; HD Control: the light bar off. |
| ![#e5484d](docs/design/colors/block-e5484d.svg) | `#e5484d` | SFTP: the errors button. |
| ![#5f6368](docs/design/colors/block-5f6368.svg) | `#5f6368` | VRAM: firmware in the memory map. |
| ![#00838f](docs/design/colors/block-00838f.svg) | `#00838f` | VRAM: zswap in the memory map. |
| ![#3dbf9c](docs/design/colors/block-3dbf9c.svg) | `#3dbf9c` | HD Control: the triangle button. |
| ![#e8505b](docs/design/colors/block-e8505b.svg) | `#e8505b` | HD Control: the circle button. |
| ![#6f9fe8](docs/design/colors/block-6f9fe8.svg) | `#6f9fe8` | HD Control: the cross button. |
| ![#e48fc0](docs/design/colors/block-e48fc0.svg) | `#e48fc0` | HD Control: the square button. |
| ![#0050ff](docs/design/colors/block-0050ff.svg) | `#0050ff` | HD Control light bar: blue (the default). |
| ![#ff2020](docs/design/colors/block-ff2020.svg) | `#ff2020` | Light bar: red. |
| ![#10d040](docs/design/colors/block-10d040.svg) | `#10d040` | Light bar: green. |
| ![#a020f0](docs/design/colors/block-a020f0.svg) | `#a020f0` | Light bar: purple. |
| ![#ffffff](docs/design/colors/block-ffffff.svg) | `#ffffff` | Light bar: white. |
| ![#ff0000](docs/design/colors/block-ff0000.svg) | `#ff0000` | The light bar's colour wheel: red. |
| ![#ffff00](docs/design/colors/block-ffff00.svg) | `#ffff00` | Colour wheel: yellow. |
| ![#00ff00](docs/design/colors/block-00ff00.svg) | `#00ff00` | Colour wheel: green. |
| ![#00ffff](docs/design/colors/block-00ffff.svg) | `#00ffff` | Colour wheel: cyan. |
| ![#0000ff](docs/design/colors/block-0000ff.svg) | `#0000ff` | Colour wheel: blue. |
| ![#ff00ff](docs/design/colors/block-ff00ff.svg) | `#ff00ff` | Colour wheel: magenta. |
| ![#d04545](docs/design/colors/block-d04545.svg) | `#d04545` | NetcatGUI tab: red. |
| ![#e08a1e](docs/design/colors/block-e08a1e.svg) | `#e08a1e` | NetcatGUI tab: orange. |
| ![#2e9e5b](docs/design/colors/block-2e9e5b.svg) | `#2e9e5b` | NetcatGUI tab: green. |
| ![#3c7dd9](docs/design/colors/block-3c7dd9.svg) | `#3c7dd9` | NetcatGUI tab: blue. |
| ![#8e5bd0](docs/design/colors/block-8e5bd0.svg) | `#8e5bd0` | NetcatGUI tab: purple. |
| ![#8a8f98](docs/design/colors/block-8a8f98.svg) | `#8a8f98` | NetcatGUI tab: grey. |
| ![#04060c](docs/design/colors/block-04060c.svg) | `#04060c` | Portal Big Picture: the backdrop. |
| ![#1b1b1b](docs/design/colors/block-1b1b1b.svg) | `#1b1b1b` | Portal Big Picture: the outline of the update badge. |
| ![#808080](docs/design/colors/block-808080.svg) | `#808080` | Portal Big Picture: a tab on hover (16 %). |

## Tools

### Portal screenshots

`tools/portal_screenshot.py` paints the portal in a fixed dark palette (Breeze Dark, as Bazzite's desktop shows the portal), so screenshots look the same on every machine.

Text colours:

- `#fcfcfc` Window, field, button and tooltip text.

  ![Sample text in #fcfcfc](docs/design/colors/text-fcfcfc.svg)

- `#a1a9b1` Placeholders.

  ![Sample text in #a1a9b1](docs/design/colors/text-a1a9b1.svg)

- `#1d99f3` Links.

  ![Sample text in #1d99f3](docs/design/colors/text-1d99f3.svg)

Background colours:

| Colour | Hex | Used for |
| --- | --- | --- |
| ![#202326](docs/design/colors/block-202326.svg) | `#202326` | Window. |
| ![#141618](docs/design/colors/block-141618.svg) | `#141618` | Fields and lists. |
| ![#1d1f22](docs/design/colors/block-1d1f22.svg) | `#1d1f22` | Every other row. |
| ![#292c30](docs/design/colors/block-292c30.svg) | `#292c30` | Buttons and tooltips. |
| ![#3daee9](docs/design/colors/block-3daee9.svg) | `#3daee9` | Selection. |
| ![#43474d](docs/design/colors/block-43474d.svg) | `#43474d` | Mid. |
| ![#33373b](docs/design/colors/block-33373b.svg) | `#33373b` | Midlight. |
| ![#101113](docs/design/colors/block-101113.svg) | `#101113` | Dark. |
| ![#3d4146](docs/design/colors/block-3d4146.svg) | `#3d4146` | Light. |
