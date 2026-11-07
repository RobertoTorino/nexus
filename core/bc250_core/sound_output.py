# SPDX-License-Identifier: GPL-3.0-or-later
"""Where Windows plays the sound: the kind of its default sound output (owner, 07-11-2026, measured on the ROG XBOX
Ally X: a TV switched to another input keeps the sound, and it moves to the handheld's speakers only when the
handheld's screen turns off). The kind is the output's form factor as Windows' Core Audio reports it (speakers, a
screen's HDMI or DisplayPort, headphones), never its name (owner, 07-11-2026: hardware changes). Read through
Core Audio's own interface (IMMDeviceEnumerator) with ctypes: no administrator, nothing written."""

from __future__ import annotations

import sys

SPEAKERS, SCREEN, HEADPHONES, OTHER = "speakers", "screen", "headphones", "other"
FORM_FACTORS = {1: SPEAKERS, 9: SCREEN, 3: HEADPHONES, 5: HEADPHONES}   # Speakers, DigitalAudioDisplayDevice,
                                                                        # Headphones, Headset
LABELS = {SPEAKERS: "PC speakers", SCREEN: "Other screen", HEADPHONES: "headphones", OTHER: "another output",
          None: "no output"}
ENUMERATOR = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"           # MMDeviceEnumerator
DEVICE_ENUMERATOR = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"    # IMMDeviceEnumerator
FORM_FACTOR = "{1DA5D803-D492-4EDD-8C23-E0C0FFEE7F0E}"          # PKEY_AudioEndpoint_FormFactor, its pid 0
RENDER, MULTIMEDIA, READ = 0, 1, 0                              # eRender, eMultimedia, STGM_READ
VT_UI4 = 19
NOT_FOUND = 0x80070490                                          # E_NOTFOUND: no sound output at all


def label(kind: str | None) -> str:
    """How the suite names an output's kind: PC speakers, Other screen (a TV's or a monitor's HDMI or DisplayPort)."""
    return LABELS.get(kind, LABELS[OTHER])


def _method(ctypes, pointer, index: int, *argtypes):
    """Method *index* of a COM object's table (IUnknown's three first), callable with the object as its first
    argument."""
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(table[index])


def default_kind() -> str | None:
    """The kind of Windows' default sound output (SPEAKERS, SCREEN, HEADPHONES or OTHER), None when Windows has no
    sound output. OSError off Windows or when Core Audio does not answer."""
    if sys.platform != "win32":
        raise OSError("Windows' sound outputs are Windows'.")
    import ctypes

    class Guid(ctypes.Structure):
        _fields_ = [("data1", ctypes.c_ulong), ("data2", ctypes.c_ushort), ("data3", ctypes.c_ushort),
                    ("data4", ctypes.c_ubyte * 8)]

    class PropertyKey(ctypes.Structure):
        _fields_ = [("fmtid", Guid), ("pid", ctypes.c_ulong)]

    def check(result: int, what: str) -> None:
        if result != 0:
            raise OSError(f"Windows' sound outputs: {what} (0x{result & 0xFFFFFFFF:08x}).")

    def release(pointer) -> None:
        _method(ctypes, pointer, 2)(pointer)

    ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
    clsid, iid, key = Guid(), Guid(), PropertyKey()
    ole32.CLSIDFromString(ENUMERATOR, ctypes.byref(clsid))
    ole32.CLSIDFromString(DEVICE_ENUMERATOR, ctypes.byref(iid))
    ole32.CLSIDFromString(FORM_FACTOR, ctypes.byref(key.fmtid))
    started = ole32.CoInitialize(None) in (0, 1)              # S_OK, S_FALSE; Qt's thread has COM already
    try:
        enumerator = ctypes.c_void_p()
        check(ole32.CoCreateInstance(ctypes.byref(clsid), None, 0x1, ctypes.byref(iid), ctypes.byref(enumerator)),
              "Core Audio does not answer")
        try:
            device = ctypes.c_void_p()
            result = _method(ctypes, enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
                enumerator, RENDER, MULTIMEDIA, ctypes.byref(device))          # GetDefaultAudioEndpoint
            if result & 0xFFFFFFFF == NOT_FOUND:
                return None
            check(result, "no default output")
            try:
                store = ctypes.c_void_p()
                check(_method(ctypes, device, 4, ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p))(
                    device, READ, ctypes.byref(store)), "its properties")     # OpenPropertyStore
                try:
                    value = (ctypes.c_ubyte * 24)()                           # a PROPVARIANT, 24 bytes at most
                    result = _method(ctypes, store, 5, ctypes.POINTER(PropertyKey), ctypes.c_void_p)(
                        store, ctypes.byref(key), value)                      # GetValue
                    vt, number = int.from_bytes(bytes(value[0:2]), "little"), int.from_bytes(bytes(value[8:12]),
                                                                                             "little")
                    ole32.PropVariantClear(value)
                    check(result, "its form factor")
                    return FORM_FACTORS.get(number, OTHER) if vt == VT_UI4 else OTHER
                finally:
                    release(store)
            finally:
                release(device)
        finally:
            release(enumerator)
    finally:
        if started:
            ole32.CoUninitialize()
