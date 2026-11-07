# SPDX-License-Identifier: GPL-3.0-or-later
"""The region codes explained: per PlayStation, what the prefixes of the title IDs and the model numbers say about
the region. The text and tables of the Android app (Dialogs.kt, RegionCodesInfoDialog, and strings.xml)."""

from __future__ import annotations

from dataclasses import dataclass

TITLE = "Region Codes Explained"


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class Section:
    console: str
    intro: str = ""                     # lines, separated by \n
    table: Table | None = None
    footer: str = ""
    coming_soon: bool = False


PS5_INTRO = """\
• PPSA: Title ID used for Western releases and digital content
• ELJM: Japan physical retail
• ECAS / ELAS: Asia physical retail
The full code matters more than just the prefix because one PPSA family can still map to different regional builds.

PPSA is broader than a simple single-region label. PPSA is the common PS5 title family for North/South American or \
European disc games and digital media, while Japanese physical games use ELJM and Asian physical games use ECAS or \
ELAS.

A good example is the PS5 region guide for Cyberpunk 2077: it shows multiple different regional box codes all still \
beginning with PPSA, such as PPSA-03974 for the Americas, PPSA-04027 for Europe/Africa/Middle East, PPSA-04028 for \
Asia, PPSA-04029 for Europe/Oceania and Korea, and PPSA-04026 for Japan."""

PS4_FOOTER = "A: Avatar | T: Theme | S: Social"

PS3_INTRO = """\
• B: Physical Blu-ray (C: Sony, L: Licensed)
• N: Digital download from PSN
• P: Vita Physical | U: PSP Physical
• MRTC: Internal ID (Capcom/Asian)
• NPIA: Internal ID (PlayStation Home)"""

PS2_INTRO = """\
PS2 keeps the same serial-style family as PS1
• S: Sony
• C: Sony / first-party | L: Licensed / third-party
• P: Japan | U: America | E: Europe | K: Korea
• Most retail PS2 games follow the same SCxx / SLxx pattern"""

PS1_INTRO = """\
• S: Sony
• C: Sony / first-party | L: Licensed / third-party
• P: Japan | U: America | E: Europe | K: Korea
• SCxx: first-party, SLxx: third-party"""

PS1_FOOTER = """\
The PS1/PS2 mapping above follows Sony’s long–running product–code pattern.
Hardware region codes are recognized by the last digit of the PlayStation model number:
0: Japan (Japanese boot ROM, NTSC:J region, NTSC Video, 100 V PSU).
1: USA/Canada (English boot ROM, NTSC:U/C region, NTSC Video, 120 V PSU).
2: Europe/Australia/PAL region (English boot ROM, PAL region, PAL Video, 220-240 V PSU).
2A: Australia (bundled specifically with an Australian mains cord and composite RCA cable).
2B: United Kingdom and Ireland (bundled with a BS 1363 mains cord and RF modulator hook-ups).
2C: All other standard PAL European nations.
3: Asia (English boot ROM, NTSC:J region, NTSC video, Wide range 110-240 V PSU)."""

PS1_PS2_ROWS = (("SCPS", "Japan", "First-Party"), ("SLPS", "Japan", "Third-Party"),
                ("SCUS", "USA", "First-Party"), ("SLUS", "USA", "Third-Party"),
                ("SCES", "Europe", "First-Party"), ("SLES", "Europe", "Third-Party"),
                ("SCKA", "Korea", "First-Party"), ("SLKA", "Korea", "Third-Party"),
                ("SCED", "Europe", "Demo"))

SECTIONS = (
    Section("PlayStation 6", coming_soon=True),
    Section("PlayStation 5", PS5_INTRO, Table(("Prefix", "Market", "Description"), (
        ("PPSA", "US / EU", "Retail + digital"), ("ELJM", "Japan", "Physical Retail"),
        ("ECAS", "Asia", "Physical Retail"), ("ELAS", "Asia", "Physical Retail"),
        ("NPXS", "NoRegion", "System Reserved")))),
    Section("PlayStation 4", "", Table(("Prefix", "Reg_S", "Region", "Sony Entity"), (
        ("EP", "EU", "Europe", "SIEE"), ("HP", "HK", "Asia", "SIE Asia"), ("IP", "IP", "Proto", "Internal"),
        ("JP", "JP", "Japan", "SIEI"), ("KP", "KO", "Korea", "SIEK"), ("UP", "US", "N. Am", "SIEA"))),
            PS4_FOOTER),
    Section("PlayStation 3", PS3_INTRO, Table(("Prefix", "Reg", "Description"), (
        ("BCAS", "Asia", "First-Party"), ("BCES", "Europe", "First-Party"), ("BCJS", "Japan", "First-Party"),
        ("BCUS", "USA", "First-Party"), ("BLES", "Europe", "Third-Party"), ("BLUS", "USA", "Third-Party"),
        ("NPEB", "Europe", "Digital 3rd"), ("NPUB", "USA", "Digital 3rd"), ("NYMPH", "HK", "Digital Classics"),
        ("NPIA", "NoRegion", "HOME")))),
    Section("PlayStation 2", PS2_INTRO, Table(("Prefix", "Region", "Description"),
                                              PS1_PS2_ROWS + (("PAPX / PBX", "NoRegion", "Promo / Utility"),))),
    Section("PlayStation 1", PS1_INTRO, Table(("Prefix", "Region", "Description"),
                                              PS1_PS2_ROWS + (("PBPX", "NoRegion", "Promo / Utility"),)),
            PS1_FOOTER),
)
