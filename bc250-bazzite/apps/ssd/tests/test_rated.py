# SPDX-License-Identifier: GPL-3.0-or-later
"""The makers' rated speeds: by model as udisks gives it, the capacity where it changes them."""

from __future__ import annotations

import re

import pytest

from ssd_check import rated


@pytest.mark.parametrize("model, speeds", [
    ("Samsung SSD 970 EVO Plus 2TB", (3500, 3300)),            # the owner's board
    ("Samsung SSD 970 EVO Plus 500GB", (3500, 3200)),
    ("Samsung SSD 980 PRO 250GB", (6400, 2700)),
    ("Samsung SSD 990 PRO 4TB", (7450, 6900)),
    ("Samsung  SSD 870 EVO 1TB", (560, 530)),                  # spaces as udisks may join them
    ("CT500MX500SSD1", (560, 510)),
    ("WD_BLACK SN850X 2000GB", (7300, 6600)),
    ("Samsung SSD 980 1TB", (3500, 3000)),                      # not the 980 PRO
    ("Samsung SSD 980 PRO with Heatsink 2TB", (7000, 5100)),
    ("Samsung 980 PRO with Heatsink 1TB", (7000, 5000)),         # its other reported form, without "SSD"
    ("Samsung SSD 990 EVO Plus 1TB", (7150, 6300)),
    ("Samsung SSD 9100 PRO 1TB", (14700, 13300)),
    ("Samsung SSD 9100 PRO with Heatsink 8TB", (14800, 13400)),
    ("SHGP31-1000GM-2", (3500, 3200)),
    ("SHPP41-500GM", (7000, 4700)),
    ("WD_BLACK SN850X HS 8000GB", (7200, 6600)),
    ("WDC WDS100T3X0C-00SJG0", (3430, 3000)),                   # the SN750, by its part number
    ("WDS100T3X0C-00SJG0", (3430, 3000)),
    ("WD_BLACK SN850 Heatsink 1TB", (7000, 5300)),
    ("WD_BLACK SN770M 2TB", (5150, 4850)),
    ("WD_BLACK SN8100 2000GB", (14900, 14000)),
    ("CT2000T700SSD3", (12400, 11800)),
    ("CT2000T500SSD8", (7400, 7000)),
    ("CT1000P310SSD2", (7100, 6000)),
    ("CT4000T705SSD5", (14100, 12600)),
    ("CT480E100SSD8", None),                                   # its speeds are only the shops'
    ("CT2000P510SSD8", None),                                  # two different specs are around
    ("Generic SSD", None),
    ("Samsung SSD 970 EVO 1TB", None),                         # not the Plus: not in the list
    ("Samsung 980 PRO 1TB", None),                             # a counterfeit's string: no "SSD", no Heatsink
    ("Samsung SSD 990 PRO 2TBX", None),                         # the whole model must match
    ("Netac NVMe SSD 1TB", None),                              # Netac reports no product name
    ("CUSU CV3500Q 1TB", None),                                # CUSU publishes no specifications
])
def test_rated_speeds(model, speeds):
    assert rated.speeds(model) == speeds


def test_every_entry_is_a_pattern_with_sane_speeds():
    for pattern, read, write in rated.RATED:
        re.compile(pattern)
        assert 100 <= write <= read <= 16000
