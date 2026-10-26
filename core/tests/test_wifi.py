# SPDX-License-Identifier: GPL-3.0-or-later
"""The Wi-Fi reader: adapters found in a fake /sys and the kernel's module tables, and what the report says about
them. The owner's UGREEN AX900 as the board reported it (storage mode on 19-10-2026, Wi-Fi mode on 17-10-2026), and
setups the owner's board does not have: Realtek and MediaTek sticks, a missing firmware file, rfkill, a stick no
driver claims, an Intel PCIe card."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from bc250_core import wifi

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="sysfs, kernel modules and iw, as on Linux")

KERNEL = "7.2.9-ogc3.1.fc44.x86_64"
SUITE = Path(__file__).resolve().parents[2]
# Lines of the running kernel's modules.dep and modules.alias (7.2.9-ogc3.1), and an Intel and MediaTek one.
MODULES_DEP = ("kernel/drivers/net/wireless/realtek/rtw88/rtw88_8822bu.ko.xz: kernel/net/mac80211/mac80211.ko.xz\n"
               "kernel/drivers/net/wireless/mediatek/mt76/mt7921/mt7921u.ko.xz:\n"
               "kernel/drivers/net/wireless/intel/iwlwifi/iwlwifi.ko.xz: kernel/net/wireless/cfg80211.ko.xz\n"
               "kernel/drivers/usb/storage/usb-storage.ko.xz:\n"
               "kernel/drivers/bluetooth/btusb.ko.xz:\n")
MODULES_ALIAS = ("# Aliases extracted from modules themselves.\n"
                 "alias usb:v0BDApB812d*dc*dsc*dp*icFFiscFFipFFin* rtw88_8822bu\n"
                 "alias usb:v0E8Dp7961d*dc*dsc*dp*icFFiscFFipFFin* mt7921u\n"
                 "alias pci:v00008086d00002723sv*sd*bc*sc*i* iwlwifi\n"
                 "alias usb:v*p*d*dc*dsc*dp*ic08isc06ip50in* usb_storage\n"
                 "alias usb:v*p*d*dc*dsc*dp*icE0isc01ip01in* btusb\n")
IW_LINK = ("Connected to 00:00:00:00:00:00 (on wlan1)\n\tSSID: home\n\tfreq: 5180.0\n\tsignal: -44 dBm\n"
           "\ttx bitrate: 540.4 MBit/s 80MHz HE-MCS 10 HE-NSS 2\n")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")


def link(path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(os.path.relpath(target, path.parent))


def driver(sys_root: Path, bus: str, name: str, module: str | None = None) -> Path:
    folder = sys_root / "bus" / bus / "drivers" / name
    folder.mkdir(parents=True, exist_ok=True)
    if module and not (folder / "module").exists():
        link(folder / "module", sys_root / "module" / module)
    return folder


def usb(sys_root: Path, name: str, vendor: str, product: str, product_name: str,
        interfaces: dict[str, tuple[str, str | None, str | None]]) -> None:
    """A USB device: interfaces map "1.0" to (interface class, driver, its module); the modalias follows."""
    device = sys_root / "bus/usb/devices" / name
    write(device / "idVendor", vendor)
    write(device / "idProduct", product)
    write(device / "product", product_name)
    for suffix, (cls, drv, module) in interfaces.items():
        part = sys_root / "bus/usb/devices" / f"{name}:{suffix}"
        sub = {"08": "06", "e0": "01"}.get(cls, cls)
        proto = {"08": "50", "e0": "01"}.get(cls, cls)
        write(part / "bInterfaceClass", cls)
        write(part / "modalias", f"usb:v{vendor.upper()}p{product.upper()}d0200dc00dsc00dp00"
                                 f"ic{cls.upper()}isc{sub.upper()}ip{proto.upper()}in00")
        if drv:
            link(part / "driver", driver(sys_root, "usb", drv, module))


def wlan(sys_root: Path, name: str, device: Path, carrier: bool = True, soft: bool = False,
         hard: bool = False) -> None:
    iface = sys_root / "class/net" / name
    (iface / "wireless").mkdir(parents=True)
    write(iface / "operstate", "up" if carrier else "dormant")
    write(iface / "carrier", "1" if carrier else "0")
    link(iface / "device", device)
    phy = sys_root / "class/ieee80211" / f"phy-{name}"
    write(phy / "rfkill0/soft", "1" if soft else "0")
    write(phy / "rfkill0/hard", "1" if hard else "0")
    link(iface / "phy80211", phy)


@pytest.fixture
def sys_root(tmp_path) -> Path:
    """The owner's board with no stick: the wired port (r8169), a USB hub and a Logitech receiver."""
    root = tmp_path / "sys"
    write(root / "bus/pci/devices/0000:04:00.0/class", "0x020000")
    write(root / "bus/pci/devices/0000:04:00.0/vendor", "0x10ec")
    write(root / "bus/pci/devices/0000:04:00.0/device", "0x8168")
    write(root / "bus/pci/devices/0000:04:00.0/modalias", "pci:v000010ECd00008168sv*")
    write(root / "class/net/enp4s0/operstate", "up")
    link(root / "class/net/enp4s0/device", root / "bus/pci/devices/0000:04:00.0")
    usb(root, "usb1", "1d6b", "0002", "xHCI Host Controller", {"1.0": ("09", "hub", "usbcore")})
    usb(root, "1-2", "046d", "c52b", "USB Receiver", {"2.0": ("03", "usbhid", "usbhid")})
    return root


@pytest.fixture
def modules(tmp_path) -> wifi.Modules:
    write(tmp_path / "lib/modules" / KERNEL / "modules.dep", MODULES_DEP)
    write(tmp_path / "lib/modules" / KERNEL / "modules.alias", MODULES_ALIAS)
    return wifi.read_modules(KERNEL, tmp_path / "lib/modules")


def levels(lines: list[tuple[str, str]]) -> list[str]:
    return [level for level, _ in lines]


def text(lines: list[tuple[str, str]]) -> str:
    return "\n".join(t for _, t in lines)


def test_module_tables(modules):
    assert modules.wireless == {"rtw88_8822bu", "mt7921u", "iwlwifi"} and modules.found
    assert [m for _, m in modules.aliases] == ["rtw88_8822bu", "mt7921u", "iwlwifi"]      # usb_storage left out
    assert modules.claiming("usb:v0BDApB812d0200dc00dsc00dp00icFFiscFFipFFin00") == ("rtw88_8822bu",)
    assert modules.claiming("usb:v0BDApB812d0200dc00dsc00dp00icE0isc01ip01in00") == ()
    assert modules.claiming("") == ()
    missing = wifi.read_modules("6.0.0", Path("/nowhere"))
    assert not missing.found and missing.aliases == ()


def test_no_adapter_on_the_board(sys_root, modules):
    assert wifi.find_adapters(sys_root, modules) == ()
    lines = wifi.report((), modules)
    assert levels(lines) == ["INFO", "HINT"]
    assert "The BC-250 has none of its own" in text(lines) and "from BC-250 USB Wi-Fi." in text(lines)
    assert "from this app." in text(wifi.report((), modules, in_wifi_app=True))
    assert levels(wifi.report((), wifi.read_modules(KERNEL, Path("/nowhere")))) == ["NOTE", "INFO", "HINT"]


def test_the_owners_stick_in_storage_mode(sys_root, modules):
    # As the board reported it on 19-10-2026: 1-5, a69c:5723 "Aic MSC", its disk on usb-storage.
    usb(sys_root, "1-5", "a69c", "5723", "Aic MSC", {"1.0": ("08", "usb-storage", "usb_storage")})
    (stick,) = wifi.find_adapters(sys_root, modules)
    assert (stick.usb_id, stick.drivers, stick.claiming) == ("a69c:5723", ("usb_storage",), ())
    assert stick.storage_mode and stick.aic_d80 and stick.verdict == "storage"
    lines = wifi.report((stick,), modules)
    assert lines[0] == ("INFO", "Aic MSC (a69c:5723, USB 1-5): driver usb_storage")
    assert lines[1][0] == "NOTE" and "BC-250 USB Wi-Fi (in the portal) builds it" in lines[1][1]
    assert "build and install the driver here" in text(wifi.report((stick,), modules, in_wifi_app=True))


def test_the_owners_stick_in_wifi_mode(sys_root, modules):
    # 17-10-2026: 2-5, a69c:8d81, Bluetooth on btusb, Wi-Fi on the suite's out-of-tree aic8800_fdrv, wlan0.
    usb(sys_root, "2-5", "a69c", "8d81", "AIC 8800D80",
        {"1.0": ("e0", "btusb", "btusb"), "1.1": ("e0", "btusb", "btusb"), "1.2": ("ff", "aic8800_fdrv", None)})
    wlan(sys_root, "wlan0", sys_root / "bus/usb/devices/2-5:1.2")
    runner = lambda argv: IW_LINK.replace("wlan1", argv[2])                               # noqa: E731
    (stick,) = wifi.find_adapters(sys_root, modules, runner=runner)
    assert stick.drivers == ("btusb", "aic8800_fdrv") and stick.wifi_drivers == ("aic8800_fdrv",)
    assert stick.verdict == "connected" and stick.interfaces[0].link == wifi.Link(5180, -44, "540.4 MBit/s")
    lines = wifi.report((stick,), modules)
    assert lines == [("INFO", "AIC 8800D80 (a69c:8d81, USB 2-5): driver btusb, aic8800_fdrv, interface wlan0"),
                     ("SUCCESS", "wlan0 is connected: 5 GHz (5180 MHz), signal -44 dBm, 540.4 Mbit/s.")]
    assert "home" not in text(lines)                                                      # the network's name
    # Without a connection, and without reading it:
    write(sys_root / "class/net/wlan0/carrier", "0")
    (stick,) = wifi.find_adapters(sys_root, modules)
    lines = wifi.report((stick,), modules)
    assert stick.verdict == "ready" and levels(lines) == ["INFO", "SUCCESS", "HINT"] and "WPA2" in lines[2][1]


def test_the_aic_stick_without_a_driver(sys_root, modules):
    usb(sys_root, "2-5", "a69c", "8d81", "AIC 8800D80", {"1.0": ("e0", "btusb", "btusb"), "1.2": ("ff", None, None)})
    (stick,) = wifi.find_adapters(sys_root, modules)
    assert stick.verdict == "aic"
    lines = wifi.report((stick,), modules)
    assert lines[1][0] == "WARNING" and "BC-250 USB Wi-Fi (in the portal) builds it" in lines[1][1]
    # The suite's loader has it, no interface yet:
    usb(sys_root, "2-6", "a69c", "8d80", "AIC Wlan", {"1.0": ("ff", "aic_load_fw", None)})
    loader = wifi.find_adapters(sys_root, modules)[1]
    assert loader.verdict == "aic" and "its window shows what the chip answered" in text(wifi.report((loader,), modules))


def test_a_realtek_stick_on_the_kernels_driver(sys_root, modules):
    usb(sys_root, "1-3", "0bda", "b812", "802.11ac NIC", {"1.0": ("ff", "rtw_8822bu", "rtw88_8822bu")})
    wlan(sys_root, "wlp0s1", sys_root / "bus/usb/devices/1-3:1.0")
    (stick,) = wifi.find_adapters(sys_root, modules, loaded=frozenset({"rtw88_8822bu"}),
                                  runner=lambda argv: "Not connected.\n")
    assert stick.drivers == ("rtw88_8822bu",) and stick.claiming == ("rtw88_8822bu",)
    assert stick.verdict == "connected" and stick.interfaces[0].link is None
    assert wifi.report((stick,), modules)[1] == ("SUCCESS", "wlp0s1 is connected.")


def test_a_driver_that_is_not_loaded(sys_root, modules):
    usb(sys_root, "1-3", "0e8d", "7961", "Wireless_Device", {"3.0": ("ff", None, None)})
    (stick,) = wifi.find_adapters(sys_root, modules)
    assert stick.verdict == "not-loaded" and stick.loaded == ()
    lines = wifi.report((stick,), modules)
    assert lines[1] == ("WARNING", f"Kernel {KERNEL} has a driver for it (mt7921u), but it is not loaded.")
    assert "sudo modprobe mt7921u" in lines[2][1]
    (stick,) = wifi.find_adapters(sys_root, modules, loaded=frozenset({"mt7921u"}))
    assert wifi.report((stick,), modules)[1][1].endswith("(mt7921u), loaded but not bound to it.")


def test_missing_firmware_and_no_interface(sys_root, modules):
    usb(sys_root, "1-3", "0e8d", "7961", "Wireless_Device", {"3.0": ("ff", "mt7921u", "mt7921u")})
    log = ("usb 1-3: new high-speed USB device number 4 using xhci_hcd\n"
           "mt7921u 1-3:3.0: Direct firmware load for mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin failed with "
           "error -2\n"
           "mt7921u 1-4:1.0: Direct firmware load for other.bin failed with error -2\n")
    (stick,) = wifi.find_adapters(sys_root, modules, boot_log=log)
    assert stick.verdict == "firmware" and stick.firmware_missing == ("mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin",)
    lines = wifi.report((stick,), modules)
    assert lines[1] == ("WARNING", "mt7921u has the adapter but not its firmware: "
                                   "mediatek/WIFI_MT7961_patch_mcu_1_2_hdr.bin.")
    (stick,) = wifi.find_adapters(sys_root, modules)
    assert stick.verdict == "no-interface" and "grep -i mt7921u" in text(wifi.report((stick,), modules))


def test_rfkill(sys_root, modules):
    usb(sys_root, "1-3", "0bda", "b812", "802.11ac NIC", {"1.0": ("ff", "rtw_8822bu", "rtw88_8822bu")})
    wlan(sys_root, "wlan0", sys_root / "bus/usb/devices/1-3:1.0", carrier=False, soft=True)
    (stick,) = wifi.find_adapters(sys_root, modules)
    lines = wifi.report((stick,), modules)
    assert stick.verdict == "blocked" and lines[1] == ("WARNING", "wlan0 is switched off (rfkill, in software).")
    assert "rfkill unblock wifi" in lines[2][1]
    write(sys_root / "class/ieee80211/phy-wlan0/rfkill0/hard", "1")
    (stick,) = wifi.find_adapters(sys_root, modules)
    assert "a hardware switch" in text(wifi.report((stick,), modules))


def test_a_stick_no_driver_claims(sys_root, modules):
    usb(sys_root, "1-3", "0bda", "c999", "", {"1.0": ("ff", None, None)})
    (stick,) = wifi.find_adapters(sys_root, modules)
    assert stick.name == "Realtek device" and stick.verdict == "no-driver"
    lines = wifi.report((stick,), modules)
    assert lines[1] == ("WARNING", f"Kernel {KERNEL} has no driver for 0bda:c999: this adapter does not work on "
                                   "Bazzite as it is.")
    # A device of another maker that nothing claims is not taken for a Wi-Fi stick.
    usb(sys_root, "1-4", "1234", "5678", "Gadget", {"1.0": ("ff", None, None)})
    assert [a.path for a in wifi.find_adapters(sys_root, modules)] == ["1-3"]


def test_a_stick_in_its_driver_disk_mode(sys_root, modules):
    usb(sys_root, "1-3", "0bda", "1a2b", "DISK", {"1.0": ("08", "usb-storage", "usb_storage")})
    (stick,) = wifi.find_adapters(sys_root, modules)
    lines = wifi.report((stick,), modules)
    assert stick.verdict == "storage" and not stick.aic_d80 and "sudo eject /dev/sdX" in lines[2][1]


def test_an_intel_pcie_card(sys_root, modules):
    card = sys_root / "bus/pci/devices/0000:05:00.0"
    write(card / "class", "0x028000")
    write(card / "vendor", "0x8086")
    write(card / "device", "0x2723")
    write(card / "modalias", "pci:v00008086d00002723sv00008086sd00000084bc02sc80i00")
    link(card / "driver", driver(sys_root, "pci", "iwlwifi", "iwlwifi"))
    wlan(sys_root, "wlp5s0", card, carrier=False)
    usb(sys_root, "1-3", "0bda", "b812", "802.11ac NIC", {"1.0": ("ff", None, None)})
    stick, intel = wifi.find_adapters(sys_root, modules)
    assert (stick.bus, intel.bus) == ("usb", "pci")
    assert intel.name == "Intel Wi-Fi card" and intel.drivers == ("iwlwifi",) and intel.verdict == "ready"
    assert wifi.report((intel,), modules)[0] == (
        "INFO", "Intel Wi-Fi card (8086:2723, PCIe 0000:05:00.0): driver iwlwifi, interface wlp5s0")


def test_link_and_band():
    assert wifi.read_link("wlan0", lambda argv: "") is None
    assert wifi.read_link("wlan0", lambda argv: "freq: 2437\n").band == "2.4 GHz"
    assert wifi.Link(5955).band == "6 GHz" and wifi.Link().band == ""


def test_runs_with_the_system_python_in_isolated_mode():
    """BC-250 Bazzite Test runs it as root with python3 -I -B and only the standard library: no Qt."""
    done = subprocess.run([sys.executable, "-I", "-B", "-c",
                           "import sys; sys.path.insert(0, sys.argv[1]); from bc250_core import wifi; "
                           "wifi.main(); print('Qt' if any(m.startswith('PyQt6') for m in sys.modules) else 'no Qt')",
                           str(SUITE / "core")], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[-1] == "no Qt"
    assert all(line.split(":", 1)[0] in ("SUCCESS", "INFO", "NOTE", "WARNING", "HINT") for line in lines[:-1])
