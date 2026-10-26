# SPDX-License-Identifier: GPL-3.0-or-later
"""The account's consoles, the wake command and the cloud games with their names."""

from __future__ import annotations

from conftest import FakeTransport

from console_linkb import xbox
from console_linkb.auth import Region, StreamToken, XboxToken
from console_linkb.net import Client

WEB = XboxToken("XSTS", "1234567890", 0, "Player One")
CLOUD = StreamToken("xgpuweb", "CLOUD", "NL", [Region("WestEurope", "https://weu.core.gssv-play-prod.xboxlive.com",
                                                     True)], 0)
DEVICES = "https://xccs.xboxlive.com/lists/devices"
CONSOLES = {"status": {"errorCode": "OK"}, "agentUserId": None, "result": [
    {"id": "F4001234ABCD5678", "name": "Living room", "locale": "en-US", "region": "", "consoleType": "XboxSeriesX",
     "powerState": "ConnectedStandby", "digitalAssistantRemoteControlEnabled": False,
     "remoteManagementEnabled": True, "consoleStreamingEnabled": True, "wirelessWarning": False,
     "outOfHomeWarning": False, "storageDevices": []},
    {"id": "FD009876DCBA4321", "name": "", "consoleType": "XboxOne", "powerState": "Off",
     "remoteManagementEnabled": False, "consoleStreamingEnabled": False},
    {"name": "no id, left out"}]}


def test_consoles_are_read_from_xbox_live():
    transport = FakeTransport({("GET", DEVICES): (200, CONSOLES)})
    found = xbox.consoles(Client(transport), WEB)
    assert [(c.id, c.name, c.type_name, c.power_name) for c in found] == [
        ("F4001234ABCD5678", "Living room", "Xbox Series X", "Sleep"), ("FD009876DCBA4321", "Xbox", "Xbox One", "Off")]
    assert found[0].streaming_enabled and found[0].can_wake
    assert not found[1].streaming_enabled and not found[1].can_wake
    headers = transport.headers("GET", DEVICES)[0]
    assert headers["Authorization"] == "XBL3.0 x=1234567890;XSTS"
    assert headers["x-xbl-contract-version"] == "4" and headers["skillplatform"] == "RemoteManagement"


def test_a_console_that_is_on_needs_no_wake():
    on = xbox.Console("F1", "X", "XboxSeriesS", "On", True, True)
    assert not on.can_wake and on.type_name == "Xbox Series S" and on.power_name == "On"


def test_wake_sends_the_power_command():
    transport = FakeTransport({("POST", "https://xccs.xboxlive.com/commands"): (200, {"result": None})})
    xbox.wake(Client(transport), WEB, "F4001234ABCD5678")
    sent = transport.sent("POST", "https://xccs.xboxlive.com/commands")[0]
    assert (sent["type"], sent["command"], sent["linkedXboxId"]) == ("Power", "WakeUp", "F4001234ABCD5678")
    assert sent["destination"] == "Xbox" and sent["sessionId"]


def test_cloud_titles_and_their_names_in_batches():
    results = [{"titleId": f"T{i}", "details": {"productId": f"9P{i:04d}", "hasEntitlement": i != 3}}
               for i in range(25)]
    transport = FakeTransport({("GET", "https://weu.core.gssv-play-prod.xboxlive.com/v2/titles"):
                               (200, {"results": results + [{"details": {}}]})})
    products = {f"9P{i:04d}": {"StoreId": f"9P{i:04d}", "ProductTitle": f"Game {i}"} for i in range(25) if i != 7}
    transport.add("POST", xbox.CATALOG, (200, {"Products": dict(list(products.items())[:20])}),
                  (200, {"Products": dict(list(products.items())[20:])}))
    titles = xbox.cloud_titles(Client(transport), CLOUD)
    assert len(titles) == 25 and not titles[3].entitled
    xbox.name_titles(Client(transport), CLOUD, titles)
    assert titles[0].name == "Game 0" and titles[24].name == "Game 24"
    assert titles[7].name == "T7"                          # not in the catalog: its title ID
    batches = transport.sent("POST", xbox.CATALOG)
    assert [len(b["Products"]) for b in batches] == [20, 5]
    url = [u for m, u, _h, _b in transport.calls if u.startswith(xbox.CATALOG)][0]
    assert "market=NL" in url and "language=en-US" in url
    assert transport.headers("GET", "https://weu.core")[0]["Authorization"] == "Bearer CLOUD"


def test_catalogue_products_as_a_list_too():
    titles = [xbox.CloudTitle("T1", "9NBLGGH4R315")]
    transport = FakeTransport({("POST", xbox.CATALOG): (200, {"Products": [{"StoreId": "9NBLGGH4R315",
                                                                           "ProductTitle": "Fortnite"}]})})
    xbox.name_titles(Client(transport), CLOUD, titles)
    assert titles[0].name == "Fortnite"
