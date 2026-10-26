# SPDX-License-Identifier: GPL-3.0-or-later
# Ported from Greenlight (packages/platform/src/controller/gamepass.ts) and xbox-webapi-node
# (src/provider/smartglass.ts), MIT, Copyright (c) 2019 UnknownSKL (Jim Kroon); the MIT notice is in the README's
# License section.
"""What the account has: its Xbox consoles (Xbox Live's console list, xccs.xboxlive.com), the wake command for one,
and the games of Xbox Cloud Gaming it may play (the streaming service's title list, named by the Game Pass
catalog)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .auth import StreamToken, XboxToken
from .net import Client

XCCS = "https://xccs.xboxlive.com"
CATALOG = "https://catalog.gamepass.com/v3/products"
CATALOG_BATCH = 20                          # product IDs per catalog call, as the reference asks them
CONSOLE_TYPES = {"XboxOne": "Xbox One", "XboxOneS": "Xbox One S", "XboxOneX": "Xbox One X",
                 "XboxSeriesS": "Xbox Series S", "XboxSeriesX": "Xbox Series X", "XboxOneSDigital": "Xbox One S "
                 "All-Digital"}
POWER_STATES = {"On": "On", "ConnectedStandby": "Sleep", "Off": "Off", "SystemUpdate": "Updating",
                "Unknown": "Unknown"}


@dataclass
class Console:
    id: str
    name: str
    console_type: str                       # Xbox Live's name: XboxSeriesX, XboxOne, ...
    power_state: str                        # On, ConnectedStandby (sleep, Instant-on), Off, ...
    streaming_enabled: bool                 # remote play is switched on in the console's settings
    remote_management: bool                 # remote features are on (the wake command needs them)

    @property
    def type_name(self) -> str:
        return CONSOLE_TYPES.get(self.console_type, self.console_type or "Xbox")

    @property
    def power_name(self) -> str:
        return POWER_STATES.get(self.power_state, self.power_state or "Unknown")

    @property
    def can_wake(self) -> bool:
        return self.remote_management and self.power_state != "On"


@dataclass
class CloudTitle:
    title_id: str                           # what a cloud session starts
    product_id: str                         # the Store's ID, for the name
    name: str = ""
    entitled: bool = True                   # the account may play it (Game Pass, or a free-to-play game)


def _xccs_headers(web: XboxToken) -> dict[str, str]:
    return {"Authorization": web.header(), "x-xbl-contract-version": "4", "skillplatform": "RemoteManagement",
            "Accept-Language": "en-US"}


def consoles(client: Client, web: XboxToken) -> list[Console]:
    data = client.get(f"{XCCS}/lists/devices?queryCurrentDevice=false&includeStorageDevices=true",
                      _xccs_headers(web)).data
    found = []
    for item in (data.get("result") or []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        found.append(Console(str(item["id"]), str(item.get("name", "")) or "Xbox", str(item.get("consoleType", "")),
                             str(item.get("powerState", "")), bool(item.get("consoleStreamingEnabled")),
                             bool(item.get("remoteManagementEnabled"))))
    return found


def wake(client: Client, web: XboxToken, console_id: str) -> None:
    """Asks Xbox Live to wake the console. Only works when it sleeps with Instant-on (the console's "Sleep" power
    mode) and has remote features on; a console that is fully off cannot be woken over the network."""
    client.post(f"{XCCS}/commands", _xccs_headers(web),
                json_body={"destination": "Xbox", "type": "Power", "command": "WakeUp",
                           "sessionId": str(uuid.uuid4()), "sourceId": "com.microsoft.smartglass",
                           "parameters": [], "linkedXboxId": console_id})


def cloud_titles(client: Client, cloud: StreamToken) -> list[CloudTitle]:
    data = client.get(f"{cloud.base_uri()}/v2/titles", {"Authorization": f"Bearer {cloud.token}"}).data
    titles = []
    for item in (data.get("results") or []) if isinstance(data, dict) else []:
        if not isinstance(item, dict) or not item.get("titleId"):
            continue
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        titles.append(CloudTitle(str(item["titleId"]), str(details.get("productId", "")),
                                 entitled=bool(details.get("hasEntitlement", True))))
    return titles


def _product_name(product: dict) -> str:
    for key in ("ProductTitle", "Title", "Name"):
        value = product.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def name_titles(client: Client, cloud: StreamToken, titles: list[CloudTitle], language: str = "en-US") -> None:
    """Fills in the titles' names from the Game Pass catalog; a title it does not know keeps its title ID."""
    market = cloud.market or "US"
    ids = sorted({t.product_id for t in titles if t.product_id})
    names: dict[str, str] = {}
    for start in range(0, len(ids), CATALOG_BATCH):
        batch = ids[start:start + CATALOG_BATCH]
        data = client.post(f"{CATALOG}?market={market}&language={language}&hydration=RemoteHighSapphire0",
                           {"Authorization": f"Bearer {cloud.token}", "ms-cv": "0.0",
                            "calling-app-name": "Console LinkB", "calling-app-version": "1.0"},
                           json_body={"Products": batch}).data
        products = data.get("Products") if isinstance(data, dict) else None
        items = products.items() if isinstance(products, dict) else \
            ((p.get("StoreId", ""), p) for p in products or [] if isinstance(p, dict))
        for product_id, product in items:
            if isinstance(product, dict):
                name = _product_name(product)
                if name:
                    names[str(product.get("StoreId") or product_id).upper()] = name
    for title in titles:
        title.name = names.get(title.product_id.upper(), "") or title.name or title.title_id
