# SPDX-License-Identifier: GPL-3.0-or-later
"""The network (network.py): the link, the power plan's Wi-Fi setting, what else is downloading and the timed
download as the Network card shows them, a failed download, the query, and Windows' own APIs answering."""

from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error

import pytest

from portable_test import network

# The owner's Ally on 28-10-2026: the link as netsh showed it, the Turbo plan, and the slow download of that evening
ALLY_LINK = network.Link(frequency=5280, channel=56, standard=10, signal=85, rssi=-54, receive=2402, transmit=2402)
TRAFFIC = {"received": 2_000_000, "seconds": 2.0, "delivery": 2, "running": ["XboxPcApp", "steam"]}


def measure(**changes) -> network.Network:
    fakes = dict(link=lambda: ("MediaTek Wi-Fi 6E MT7922 (RZ616) 160MHz Wireless LAN Card", ALLY_LINK),
                 plan=lambda: ("Turbo", (0, 2)), run=lambda argv: json.dumps(TRAFFIC),
                 url=lambda: "https://example.invalid/wp-test-v1.3.0.zip",
                 download=lambda url: (4_521_984, 10.05))
    fakes.update(changes)
    return network.measure("battery, 82%", **fakes)


def test_the_ally_as_measured():
    assert measure().rows() == [
        ("Wi-Fi", "5 GHz, channel 56"), ("Standard", "Wi-Fi 6 (802.11ax)"), ("Signal", "85%, -54 dBm"),
        ("Rate", "2402 Mbps down, 2402 up"), ("Power", "battery, 82%, Turbo plan"),
        ("Wi-Fi on mains", "Maximum Performance"), ("Wi-Fi on battery", "Medium Power Saving"),
        ("Other traffic", "1.00 MB/s before the download"),
        ("Also running", "Delivery Optimization (2 downloads), Xbox app, Steam"),
        ("Download", "0.4 MB/s (4.5 MB in 10.1 s)")]


@pytest.mark.parametrize("frequency, band", [(2437, "2.4 GHz"), (5280, "5 GHz"), (5955, "6 GHz"), (0, "")])
def test_the_band(frequency, band):
    assert network.Link(frequency=frequency).band == band


def test_without_wifi_and_without_a_plan_setting():
    rows = dict(measure(link=lambda: ("", None), plan=lambda: ("", None)).rows())
    assert rows["Wi-Fi"] == "no Wi-Fi adapter" and "Signal" not in rows and "Wi-Fi on mains" not in rows
    assert rows["Power"] == "battery, 82%"
    assert dict(measure(link=lambda: ("MediaTek", None)).rows())["Wi-Fi"] == "not connected"


def test_nothing_else_downloading_and_an_unknown_frequency():
    found = measure(run=lambda argv: json.dumps({"received": 0, "seconds": 2.0, "delivery": 0, "running": "steam"}),
                    link=lambda: ("MediaTek", network.Link(channel=56, standard=7, signal=40, receive=144,
                                                           transmit=72)))
    rows = dict(found.rows())
    assert rows["Wi-Fi"] == "channel 56" and rows["Signal"] == "40%" and rows["Standard"] == "Wi-Fi 4 (802.11n)"
    assert rows["Other traffic"] == "0.00 MB/s before the download" and rows["Also running"] == "Steam"
    found = measure(run=lambda argv: json.dumps({"received": 0, "seconds": 2.0, "delivery": 0, "running": None}))
    assert dict(found.rows())["Also running"] == "nothing that downloads"


def test_a_query_that_failed_leaves_its_rows_out():
    def fail(argv):
        raise RuntimeError("PowerShell ended with 1")
    rows = dict(measure(run=fail).rows())
    assert "Other traffic" not in rows and rows["Also running"] == "nothing that downloads" and "Download" in rows


def test_a_failed_download():
    def offline():
        raise OSError("no connection (getaddrinfo failed)")

    def refused(url):
        raise urllib.error.URLError("timed out")
    assert measure(url=offline).error == "no connection (getaddrinfo failed)"
    found = measure(download=refused)
    assert found.error == "timed out" and dict(found.rows())["Download"] == "failed: timed out"


def test_it_says_what_it_does():
    said = []
    measure(say=said.append)
    assert [text.split()[0] for text in said] == ["Reading", "Measuring", "Downloading"]


def test_the_query():
    seen = []
    measure(run=lambda argv: seen.append(argv) or json.dumps(TRAFFIC))
    script = base64.b64decode(seen[0][-1]).decode("utf-16-le")
    assert "Start-Sleep -Milliseconds 2000" in script and "Get-DeliveryOptimizationStatus" in script
    assert "Get-Process -Name steam, XboxPcApp," in script and "SAMPLE_MS" not in script
    assert "MacAddress" not in script and "SSID" not in script                 # nothing personal is asked for


def test_the_timed_download_stops_after_its_seconds(monkeypatch):
    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()
    monkeypatch.setattr(network.urllib.request, "urlopen", lambda request, timeout: Response(b"x" * (1 << 20)))
    ticks = iter(range(100))
    got, seconds = network.timed_download("https://example.invalid/a.zip", seconds=3, clock=lambda: next(ticks))
    assert got == 3 * (1 << 16) and seconds == 4
    got, _ = network.timed_download("https://example.invalid/a.zip", seconds=1000, clock=lambda: 0.0)
    assert got == 1 << 20                                                       # the whole file, when it is faster


@pytest.mark.parametrize("state, text", [((82, False), "battery, 82%"), ((100, True), "mains, 100%"), (None, "")])
def test_the_power_row(state, text):
    assert network.power_text(state) == text


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' wlanapi and powrprof")
def test_windows_answers():
    adapter, link = network.wifi()                  # a CI runner has no Wi-Fi adapter: ("", None)
    assert isinstance(adapter, str) and (link is None or 0 <= link.signal <= 100)
    plan, values = network.wifi_power()
    assert isinstance(plan, str) and (values is None or all(value in network.POWER_SAVING for value in values))
