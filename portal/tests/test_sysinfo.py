# SPDX-License-Identifier: GPL-3.0-or-later
"""The Sys info window's reader: recorded from the owner's board, and other setups (two GPUs, a SATA drive, DMI
placeholders, Secure Boot, a USB Wi-Fi adapter, nothing reported at all); never a serial number or MAC address."""

from __future__ import annotations

from pathlib import Path

from bc250_portal import sysinfo

PCI_IDS = """\
# a comment
1002  Advanced Micro Devices, Inc. [AMD/ATI]
\t13fe  Cyan Skillfish [BC-250]
\t\t1022 0000  a subsystem
\t73bf  Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]
10de  NVIDIA Corporation
\t2684  AD102 [GeForce RTX 4090]
10ec  Realtek Semiconductor Co., Ltd.
\t8168  RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller
"""
USB_IDS = """\
0bda  Realtek Semiconductor Corp.
\tb812  RTL88x2bu [AC1200 Techkey]
"""
SERIAL = "SN0123456789"
MAC_ADDRESS = "58:10:31:3f:5c:85"


def edid(name: str) -> bytes:
    """A 128-byte EDID with the monitor's serial (0xFF) and name (0xFC) descriptors."""
    def descriptor(tag: int, text: str) -> bytes:
        return bytes([0, 0, 0, tag, 0]) + (text.encode() + b"\n").ljust(13, b" ")
    return bytes(54) + descriptor(0xFF, SERIAL) + descriptor(0xFC, name) + bytes(36) + bytes(2)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def link(path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(target)


def usb_device(sys: Path, port: str, ids: str, product: str = "", manufacturer: str = "", cls: str = "00",
               speed: str = "480") -> Path:
    device = sys / "devices" / "pci0000:00" / "usb" / port
    vendor, _, model = ids.partition(":")
    for name, value in (("idVendor", vendor), ("idProduct", model), ("product", product),
                        ("manufacturer", manufacturer), ("bDeviceClass", cls), ("speed", speed),
                        ("serial", SERIAL)):
        if value:
            write(device / name, value + "\n")
    link(sys / "bus" / "usb" / "devices" / port, device)
    return device


def bc250(root: Path) -> tuple[Path, Path, Path, tuple[Path, ...], Path]:
    """sys, proc and etc as on the owner's board (no serial numbers: the reader never reads them)."""
    sys, proc, etc = root / "sys", root / "proc", root / "etc"
    dmi = sys / "class" / "dmi" / "id"
    for name, value in (("sys_vendor", "Default string"), ("product_name", "AMD BC-250"),
                        ("product_version", "Default string"), ("board_vendor", "ASRock"),
                        ("board_name", "AMD BC-250"), ("board_version", ""), ("bios_vendor", "American Megatrends Inc."),
                        ("bios_version", "P5.00"), ("bios_date", "05/03/2022")):
        write(dmi / name, value + "\n")
    (sys / "firmware" / "efi").mkdir(parents=True)                            # UEFI, no SecureBoot variable
    write(proc / "cpuinfo", "processor\t: 0\nmodel name\t: AMD BC-250\nmicrocode\t: 0x8407007\n\n"
                            "processor\t: 1\nmodel name\t: AMD BC-250\nmicrocode\t: 0x8407007\n")
    cpu = sys / "devices" / "system" / "cpu"
    write(cpu / "online", "0-11\n")
    for n in range(12):
        write(cpu / f"cpu{n}" / "topology" / "physical_package_id", "0\n")
        write(cpu / f"cpu{n}" / "topology" / "core_id", f"{n // 2}\n")
    write(cpu / "cpu0" / "cpufreq" / "cpuinfo_max_freq", "3200000\n")
    card = sys / "class" / "drm" / "card1" / "device"
    write(card / "uevent", "DRIVER=amdgpu\nPCI_CLASS=30000\nPCI_ID=1002:13FE\nPCI_SLOT_NAME=0000:01:00.0\n")
    write(card / "mem_info_vram_total", "6442450944\n")
    write(card / "mem_info_gtt_total", "10119245824\n")
    write(card / "pp_dpm_sclk", "0: 1000Mhz *\n1: 1500Mhz \n2: 2000Mhz \n")
    write(card / "vbios_version", "113-AMDRBN-003\n")
    write(card / "current_link_speed", "16.0 GT/s PCIe\n")
    write(card / "current_link_width", "16\n")
    dp1, dp2 = sys / "class" / "drm" / "card1-DP-1", sys / "class" / "drm" / "card1-DP-2"   # connectors, not cards
    write(dp1 / "status", "connected\n")
    write(dp1 / "modes", "3840x2160\n4096x2160\n")
    (dp1 / "edid").write_bytes(edid("Mi TV"))
    write(dp2 / "status", "disconnected\n")
    write(dp2 / "modes", "")
    write(proc / "asound" / "cards", " 0 [Generic        ]: HDA-Intel - HD-Audio Generic\n"
                                     "                      HD-Audio Generic at 0xfe880000 irq 50\n"
                                     " 1 [Controller     ]: USB-Audio - Wireless Controller\n"
                                     "                      Sony Interactive Entertainment Wireless Controller at "
                                     "usb-0000:00:10.0-2, full speed\n")
    write(proc / "asound" / "card0" / "codec#0", "Codec: ATI R6xx HDMI\nAddress: 0\n")
    nic = sys / "devices" / "pci0000:00" / "0000:04:00.0"
    write(nic / "uevent", "DRIVER=r8169\nPCI_CLASS=20000\nPCI_ID=10EC:8168\n")
    link(sys / "class" / "net" / "enp4s0" / "device", nic)
    write(sys / "class" / "net" / "enp4s0" / "speed", "1000\n")
    write(sys / "class" / "net" / "enp4s0" / "operstate", "up\n")
    write(sys / "class" / "net" / "enp4s0" / "address", MAC_ADDRESS + "\n")
    write(sys / "class" / "net" / "lo" / "operstate", "unknown\n")             # no device: not hardware
    usb_device(sys, "3-5", "a69c:8d80", "AIC Wlan", "aicsemi")
    bt = usb_device(sys, "4-1", "33fa:0012", "UGREEN BT6.0 Adapter", cls="e0", speed="12")
    write(bt / "4-1:1.0" / "uevent", "DRIVER=btusb\n")
    link(sys / "class" / "bluetooth" / "hci0" / "device", bt / "4-1:1.0")
    write(sys / "class" / "bluetooth" / "hci0:65" / "uevent", "")              # a connection
    usb_device(sys, "6-2", "054c:09cc", "Wireless Controller", "Sony Interactive Entertainment", speed="12")
    usb_device(sys, "usb7", "1d6b:0003", "xHCI Host Controller", cls="09", speed="5000")     # a hub
    hwmon = sys / "class" / "hwmon"
    for chip, name, files in (
            ("hwmon0", "nvme", {"temp1_input": "39850", "temp1_label": "Composite"}),
            ("hwmon1", f"ps_controller_battery_{MAC_ADDRESS}", {"temp1_input": "30000"}),
            ("hwmon2", "nct6686", {"temp1_input": "42000", "temp1_label": "CPU", "temp4_input": "0",
                                   "temp4_label": "PCH", "fan1_input": "0", "fan2_input": "1151",
                                   "fan2_label": "Pump Fan"}),
            ("hwmon3", "amdgpu", {"temp1_input": "44000", "temp1_label": "edge", "power1_average": "43914000",
                                  "power1_label": "PPT"}),
            ("hwmon10", "k10temp", {"temp1_input": "43356", "temp1_label": "Tctl"})):
        write(hwmon / chip / "name", name + "\n")
        for file, value in files.items():
            write(hwmon / chip / file, value + "\n")
    write(proc / "meminfo", "MemTotal:        9882076 kB\nMemFree:  1 kB\nSwapTotal:       4941036 kB\n")
    nvme = sys / "block" / "nvme0n1"
    write(nvme / "size", "1000215216\n")
    write(nvme / "removable", "0\n")
    write(nvme / "queue" / "rotational", "0\n")
    write(nvme / "device" / "model", "KXG50ZNV512G NVMe TOSHIBA 512GB          \n")
    write(sys / "block" / "zram0" / "size", "9764864\n")
    write(sys / "block" / "loop0" / "size", "100\n")
    write(etc / "os-release", 'NAME="Bazzite"\nVERSION="44.20261012.0 (Kinoite)"\nPRETTY_NAME="Bazzite"\n')
    image = root / "image-info.json"
    write(image, '{"image-name": "bazzite", "image-tag": "stable", "version-pretty": "Stable (F44.20261012)"}')
    ids = root / "pci.ids"
    write(ids, PCI_IDS)
    write(root / "usb.ids", USB_IDS)
    return sys, proc, etc, (ids,), image


def collect(root: Path, sys: Path, proc: Path, etc: Path, ids: tuple[Path, ...], image: Path):
    return sysinfo.collect(sys, proc, etc, root, ids, image, (root / "usb.ids",))


def test_the_owners_board(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    sys, proc, etc, ids, image = bc250(tmp_path)
    for number, name, bus in ((0, "Power Button", "0019"), (6, "HD-Audio Generic HDMI/DP,pcm=3", "0001"),
                              (12, "Sony Interactive Entertainment Wireless Controller", "0003"),
                              (13, "Dell Keybd KB740 Keyboard", "0005"), (14, "Dell Keybd KB740 Keyboard", "0005"),
                              (15, "Microsoft X-Box 360 pad 0", "0006")):    # Steam Input's virtual pad
        write(sys / "class" / "input" / f"input{number}" / "name", name + "\n")
        write(sys / "class" / "input" / f"input{number}" / "id" / "bustype", bus + "\n")
    found = collect(tmp_path, sys, proc, etc, ids, image)
    sections = dict(found)
    assert list(sections) == ["Board", "BIOS", "CPU", "GPU", "Memory", "Drives", "Display", "Audio", "Network", "USB",
                              "Input", "Sensors", "OS"]
    assert sections["Board"] == [("Board", "ASRock AMD BC-250"), ("Product", "AMD BC-250")]   # no "Default string"
    assert sections["BIOS"] == [("Version", "P5.00"), ("Vendor", "American Megatrends Inc."), ("Date", "05/03/2022"),
                                ("Boot", "UEFI")]
    assert sections["CPU"] == [("Model", "AMD BC-250"), ("Online", "6 cores, 12 threads"), ("Max clock", "3.20 GHz"),
                               ("Microcode", "0x8407007")]
    assert sections["GPU"] == [
        ("Name", "Advanced Micro Devices, Inc. [AMD/ATI] Cyan Skillfish [BC-250]"), ("PCI id", "1002:13FE"),
        ("Driver", "amdgpu"), ("VRAM", "6 GiB"), ("Shared memory (GTT)", "9.4 GiB"),
        ("Clock levels", "1000Mhz, 1500Mhz, 2000Mhz"), ("VBIOS", "113-AMDRBN-003"), ("PCIe link", "16.0 GT/s PCIe x16")]
    assert sections["Memory"] == [("RAM", "9.4 GiB"), ("Swap", "4.7 GiB")]
    drives = dict(sections["Drives"])
    assert drives.pop("nvme0n1") == "KXG50ZNV512G NVMe TOSHIBA 512GB, 512.1 GB NVMe"
    assert list(drives) == ["Home free"]                                                  # no zram, no loop
    os_rows = dict(sections["OS"])
    assert os_rows["System"] == "Bazzite 44.20261012.0 (Kinoite)"
    assert os_rows["Image"] == "bazzite:stable, Stable (F44.20261012)"
    assert os_rows["Desktop"] == "KDE (wayland)" and os_rows["Kernel"]
    assert sections["Display"] == [("DP-1", "Mi TV, 3840x2160 preferred"), ("DP-2", "not connected")]
    assert sections["Audio"] == [("Card 0", "HD-Audio Generic, ATI R6xx HDMI"), ("Card 1", "Wireless Controller")]
    assert sections["Network"] == [
        ("enp4s0", "Realtek Semiconductor Co., Ltd. RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller, "
                   "wired, r8169, 1 Gbit/s"),
        ("hci0", "UGREEN BT6.0 Adapter, Bluetooth, btusb")]
    assert sections["USB"] == [("a69c:8d80", "aicsemi AIC Wlan, USB 2.0"), ("33fa:0012", "UGREEN BT6.0 Adapter, USB 1.1"),
                               ("054c:09cc", "Sony Interactive Entertainment Wireless Controller, USB 1.1")]  # bus order
    assert sections["Input"] == [("Sony Interactive Entertainment Wireless Controller", "USB"),
                                 ("Dell Keybd KB740 Keyboard", "Bluetooth"), ("Microsoft X-Box 360 pad 0", "virtual")]
    assert sections["Sensors"] == [
        ("nvme Composite", "39.9 °C"), ("nct6686 CPU", "42.0 °C"), ("nct6686 Pump Fan", "1151 RPM"),
        ("amdgpu edge", "44.0 °C"), ("amdgpu PPT", "43.9 W"), ("k10temp Tctl", "43.4 °C")]    # hwmon10 after hwmon3
    text = sysinfo.as_text(found)
    assert SERIAL not in text and MAC_ADDRESS not in text                         # nothing personal


def test_two_gpus_a_sata_drive_and_a_usb_stick(tmp_path):
    sys, proc, etc, ids, image = bc250(tmp_path)
    second = sys / "class" / "drm" / "card0" / "device"
    write(second / "uevent", "DRIVER=nvidia\nPCI_CLASS=30000\nPCI_ID=10DE:2684\n")
    write(sys / "class" / "drm" / "card2" / "device" / "uevent", "DRIVER=amdgpu\nPCI_CLASS=30000\nPCI_ID=1002:FFFF\n")
    write(sys / "class" / "drm" / "card3" / "device" / "uevent", "DRIVER=x\nPCI_CLASS=20000\nPCI_ID=1:2\n")  # no GPU
    for name, rotational, removable, model in (("sda", "1", "0", "WDC WD40EFRX"), ("sdb", "0", "1", "Flash Disk")):
        write(sys / "block" / name / "size", "7814037168\n")
        write(sys / "block" / name / "queue" / "rotational", rotational + "\n")
        write(sys / "block" / name / "removable", removable + "\n")
        write(sys / "block" / name / "device" / "model", model + "\n")
    write(sys / "firmware" / "efi" / "efivars" / sysinfo.SECURE_BOOT, "")
    (sys / "firmware" / "efi" / "efivars" / sysinfo.SECURE_BOOT).write_bytes(b"\x06\x00\x00\x00\x01")
    wifi = usb_device(sys, "1-2", "0bda:b812", speed="480")                      # no strings: from usb.ids
    write(wifi / "1-2:1.0" / "uevent", "DRIVER=rtw88_8822bu\n")
    link(sys / "class" / "net" / "wlp0s1" / "device", wifi / "1-2:1.0")
    (sys / "class" / "net" / "wlp0s1" / "wireless").mkdir()
    write(sys / "class" / "net" / "wlp0s1" / "operstate", "down\n")
    hdmi = sys / "class" / "drm" / "card0-HDMI-A-1"
    write(hdmi / "status", "connected\n")                                     # no EDID, no modes
    sections = collect(tmp_path, sys, proc, etc, ids, image)
    assert dict(dict(sections)["BIOS"])["Secure Boot"] == "on"
    assert dict(dict(sections)["Network"])["wlp0s1"] == \
        "Realtek Semiconductor Corp. RTL88x2bu [AC1200 Techkey], Wi-Fi, rtw88_8822bu, not connected"
    assert dict(dict(sections)["Display"])["HDMI-A-1"] == "connected"
    gpus = [(title, dict(rows)) for title, rows in sections if title.startswith("GPU")]
    assert [(t, r["Name"], r["Driver"]) for t, r in gpus] == [
        ("GPU", "NVIDIA Corporation AD102 [GeForce RTX 4090]", "nvidia"),
        ("GPU 2", "Advanced Micro Devices, Inc. [AMD/ATI] Cyan Skillfish [BC-250]", "amdgpu"),
        ("GPU 3", "Advanced Micro Devices, Inc. [AMD/ATI]", "amdgpu")]                  # a device pci.ids lacks
    drives = dict(dict(sections)["Drives"])
    assert drives["sda"] == "WDC WD40EFRX, 4 TB HDD" and drives["sdb"] == "Flash Disk, 4 TB USB"


def test_a_system_that_reports_nothing(tmp_path, monkeypatch):
    """No sysfs, /proc or /etc (another OS, a container): only what Python itself knows."""
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    missing = tmp_path / "missing"
    sections = sysinfo.collect(missing, missing, missing, tmp_path, (missing,), missing, (missing,))
    assert [title for title, _ in sections] == ["Drives", "OS"]
    assert [key for key, _ in dict(sections)["OS"]] == ["Kernel"]


def test_as_text():
    assert sysinfo.as_text([("BIOS", [("Version", "P5.00"), ("Date", "05/03/2022")]), ("OS", [("Kernel", "7")])]) \
        == "BIOS\n  Version: P5.00\n  Date: 05/03/2022\nOS\n  Kernel: 7"
