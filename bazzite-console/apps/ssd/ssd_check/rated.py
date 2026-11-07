# SPDX-License-Identifier: GPL-3.0-or-later
"""The makers' rated read and write speeds of known drives (owner, 05-11-2026: the official speed is what the drive
can do; the measurement shows what the board lets it do). No drive reports them, so SSD Check keeps this list, from
the makers' spec sheets; a drive not in it shows its fastest link instead. NVMe drives of PCIe 3.0 and later, and a
few SATA SSDs; the weekly backlog review (MIGRATION.md) looks for new models.

Each entry is a pattern that the whole model as udisks gives it (vendor and model, as the drive reports it) must
match, and the sequential read and write in MB/s, the maker's "up to". The speeds often differ by capacity, so the
capacity is part of the pattern where it does. A drive whose reported model does not name the product (Netac's
"Netac NVMe SSD 1TB") cannot be in the list, nor a maker that publishes no specifications (CUSU)."""

from __future__ import annotations

import re

RATED: tuple[tuple[str, int, int], ...] = (
    # Samsung NVMe, from Samsung's data sheets (download.semiconductor.samsung.com/resources/data-sheet/). The 980 PRO
    # with Heatsink reports its model with and without "SSD".
    (r"Samsung SSD 970 EVO Plus 250GB", 3500, 2300),
    (r"Samsung SSD 970 EVO Plus 500GB", 3500, 3200),
    (r"Samsung SSD 970 EVO Plus (1|2)TB", 3500, 3300),
    (r"Samsung SSD 980 250GB", 2900, 1300),
    (r"Samsung SSD 980 500GB", 3100, 2600),
    (r"Samsung SSD 980 1TB", 3500, 3000),
    (r"Samsung SSD 980 PRO 250GB", 6400, 2700),
    (r"Samsung SSD 980 PRO 500GB", 6900, 5000),
    (r"Samsung (SSD 980 PRO( with Heatsink)?|980 PRO with Heatsink) 1TB", 7000, 5000),
    (r"Samsung (SSD 980 PRO( with Heatsink)?|980 PRO with Heatsink) 2TB", 7000, 5100),
    (r"Samsung SSD 990 EVO (1|2)TB", 5000, 4200),
    (r"Samsung SSD 990 EVO Plus 1TB", 7150, 6300),
    (r"Samsung SSD 990 EVO Plus (2|4)TB", 7250, 6300),
    (r"Samsung SSD 990 PRO( with Heatsink)? (1|2|4)TB", 7450, 6900),
    (r"Samsung SSD 9100 PRO( with Heatsink)? 1TB", 14700, 13300),
    (r"Samsung SSD 9100 PRO( with Heatsink)? 2TB", 14700, 13400),
    (r"Samsung SSD 9100 PRO( with Heatsink)? (4|8)TB", 14800, 13400),
    # SK hynix NVMe, from ssd.skhynix.com (Gold P31, Platinum P41); the P31's "-2" is a second variant of the drive
    (r"SHGP31-500GM(-2)?", 3500, 3100),
    (r"SHGP31-(1000|2000)GM(-2)?", 3500, 3200),
    (r"SHPP41-500GM", 7000, 4700),
    (r"SHPP41-(1000|2000)GM", 7000, 6500),
    # WD_BLACK NVMe, from the WD and SanDisk data sheets (documents.sandisk.com). The older drives report a part
    # number, with "WDC " before it; the SN850 reports either form, by its firmware.
    (r"(WDC )?WDS250G3X0C-00SJG0", 3100, 1600),                                  # SN750
    (r"(WDC )?WDS500G3X(0|H)C-00SJG0", 3430, 2600),
    (r"(WDC )?WDS100T3X(0|H)C-00SJG0", 3430, 3000),
    (r"(WDC )?WDS200T3X(0|H)C-00SJG0|WD_BLACK SN750 2TB", 3400, 2900),
    (r"(WDC )?WDS400T3X0C-00SJG0|WD_BLACK SN750 4TB", 3400, 3100),
    (r"WD_BLACK SN750 SE 250GB", 3200, 1000),
    (r"WD_BLACK SN750 SE (NVMe )?500GB", 3600, 2000),
    (r"WD_BLACK SN750 SE (NVMe )?1TB", 3600, 2830),
    (r"WD_BLACK SN770M? 250GB", 4000, 2000),                                       # SN770M: 500GB and up
    (r"WD_BLACK SN770M? 500GB", 5000, 4000),
    (r"WD_BLACK SN770M? 1TB", 5150, 4900),
    (r"WD_BLACK SN770M? 2TB", 5150, 4850),
    (r"(WDC )?WDS500G1X(0|H)E-00AFY0|WD_BLACK SN850 (NVMe |Heatsink |PS5 )?500GB", 7000, 4100),
    (r"(WDC )?WDS100T1X(0|H)E-00AFY0|WD_BLACK SN850 (NVMe |Heatsink |PS5 )?1TB", 7000, 5300),
    (r"(WDC )?WDS200T1X(0|H)E-00AFY0|WD_BLACK SN850 (NVMe |Heatsink |PS5 )?2TB", 7000, 5100),
    (r"WD_BLACK SN850X (HS )?1000GB|WD_BLACK SN850P for PS5 1000GB", 7300, 6300),
    (r"WD_BLACK SN850X (HS )?(2000|4000)GB|WD_BLACK SN850P for PS5 (2000|4000)GB", 7300, 6600),
    (r"WD_BLACK SN850X (HS )?8000GB|WD_BLACK SN850P for PS5 8000GB", 7200, 6600),
    (r"WD_BLACK SN7100 500GB", 6800, 5800),
    (r"WD_BLACK SN7100 (1|2)TB", 7250, 6900),
    (r"WD_BLACK SN7100 4TB", 7000, 6700),
    (r"WD_BLACK SN8100 1000GB", 14900, 11000),
    (r"WD_BLACK SN8100 (2000|4000)GB", 14900, 14000),
    (r"WD_BLACK SN8100 8000GB", 14900, 13200),
    # Crucial NVMe, from Crucial's product flyers and the spec tables reviews give of them. The model is CT, the
    # capacity in GB, the drive and SSD with a form code: 8 a bare 2280, 5 with a heatsink, 3 the T700, T705 and 4TB
    # T500, 2 a 2230.
    (r"CT500P3SSD8", 3500, 1900),
    (r"CT(1000|2000|4000)P3SSD8", 3500, 3000),
    (r"CT500P3PSSD8", 4700, 1900),
    (r"CT1000P3PSSD8", 5000, 3600),
    (r"CT2000P3PSSD8", 5000, 4200),
    (r"CT4000P3PSSD8", 4800, 4100),
    (r"CT500P5PSSD(8|5)", 6600, 4000),
    (r"CT(1000|2000)P5PSSD(8|5)", 6600, 5000),
    (r"CT500T500SSD8", 7200, 5700),
    (r"CT1000T500SSD(8|5)", 7300, 6800),
    (r"CT2000T500SSD(8|5)", 7400, 7000),
    (r"CT4000T500SSD3", 7000, 6900),
    (r"CT500P310SSD8", 6600, 3500),
    (r"CT(1000|2000)P310SSD(8|5|2)", 7100, 6000),
    (r"CT1000T700SSD(3|5)", 11700, 9500),
    (r"CT(2000|4000)T700SSD(3|5)", 12400, 11800),
    (r"CT1000T705SSD(3|5)", 13600, 10200),
    (r"CT2000T705SSD(3|5)", 14500, 12700),
    (r"CT4000T705SSD(3|5)", 14100, 12600),
    (r"CT1000T710SSD(8|5)", 14900, 13700),
    (r"CT(2000|4000)T710SSD(8|5)", 14500, 13800),
    (r"CT1000P510SSD(8|5)", 11000, 9500),
    # Samsung SATA
    (r"Samsung SSD 860 EVO \S+", 550, 520),
    (r"Samsung SSD 870 EVO \S+", 560, 530),
    # Crucial SATA (CT500MX500SSD1, CT1000MX500SSD1, ...)
    (r"CT\d+MX500SSD\d", 560, 510),
)


def speeds(model: str) -> tuple[int, int] | None:
    """The rated (read, write) in MB/s of *model*, or None when it is not in the list."""
    model = " ".join(model.split())
    for pattern, read, write in RATED:
        if re.fullmatch(pattern, model, re.IGNORECASE):
            return read, write
    return None
