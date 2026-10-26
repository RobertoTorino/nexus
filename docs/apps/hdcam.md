<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![USB HD Cam](../assets/hdcam/bc250-usb-hdcam.webp){ .app-logo }

# USB HD Cam

Makes the **PS5 HD Camera (CFI-ZEY1)** a webcam on **Bazzite**. After that, OBS, a
browser, Discord or any other app can use it like any USB camera. The app changes nothing on the board.

## How the camera works

The camera has no memory of its own. When it is plugged in, it is only a boot loader, an OmniVision OV580 that
waits for its firmware:

```bash
lsusb | grep 05a9           # ... ID 05a9:0580 OmniVision Technologies, Inc. USB Boot
```

A PlayStation sends the firmware each time the camera is plugged in, and this app does the same. Then the camera
leaves the bus and comes back within a few seconds as a USB video camera:

```bash
lsusb | grep 05a9           # ... ID 05a9:058c OmniVision Technologies, Inc. USB Camera-OV580
```

From there on Linux's own `uvcvideo` driver drives it, so it needs **no kernel driver**. It shows up as
`/dev/video<n>`.

The camera needs a **USB 3 port** (5 Gbit/s, usually blue). The boot loader also starts on a USB 2 port, but the
video does not fit through it. The header's **USB** box shows the port's speed and flags a port that is too slow.
The BC-250's two USB 3 ports are on the same controller, so either one will do.

## USB bandwidth

The firmware asks for the largest video stream USB 3 has: about 3 Gbit/s, reserved whatever mode is used. Some USB
controllers cannot give that, the BC-250's among them, and then the camera sends no picture at all (the kernel's
log, `journalctl -k`, says "Not enough bandwidth"). **USB bandwidth** in the Firmware box chooses what the camera
asks for:

| Setting | What it asks for | What streams |
|---|---|---|
| **Reduced** (the default) | two thirds: about 2 Gbit/s | every one-camera mode at its full rate; side by side up to 2560 × 800 at 30 fps, and 3840 × 1080 at 8 fps |
| **Full** | the firmware as it is | every mode at every rate, on a controller that allows it |

The app changes only the copy of the firmware it sends (2 bytes of the camera's USB description), not the file.
A change takes effect the next time the firmware is sent: unplug the camera and plug it in again.

## Access to the camera

The boot loader belongs to root. The first time, the window shows **Access to the camera**: **Allow access…** asks
for your password and adds a udev rule that gives the user at the board the boot loader, for its USB ID only. The
same rule starts the load service when the camera is plugged in (see [Loading by itself](#loading-by-itself)). It
takes effect at once; there is no need to unplug the camera or log out.

The rule is `/etc/udev/rules.d/70-bc250-usb-hdcam.rules`:

```
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="05a9", ATTR{idProduct}=="0580", TAG+="uaccess", TAG+="systemd", ENV{SYSTEMD_USER_WANTS}+="bc250-usb-hdcam-load.service"
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="05a9", ATTR{idProduct}=="058c|058a", TEST=="power/control", ATTR{power/control}="on"
```

The camera itself, once it has its firmware, needs no rule for access: Bazzite already gives the user at the board
its video cameras. The second line keeps it powered while it is plugged in. Otherwise Linux suspends it two seconds
after the last app lets go of it, and a suspended camera forgets its picture settings: the picture is dark again the
next time, although the settings still read Auto Mode. When the app finds a rule from an earlier version, it offers
**Allow access…** again to update it. `install.sh --uninstall` removes the rule again (with sudo).

## The firmware

The firmware is Sony's, so the suite does not include it. The **Firmware** box offers two ways to get it:

- **Download…** gets the firmware of the camera that is plugged in, from a project that publishes it. The app
  downloads one fixed version of each file and checks its SHA-256, so it uses the file it was tested with or nothing:

    | Camera | Firmware | From |
    |---|---|---|
    | PS5 HD Camera | 21.01-03.20.00.04 (67 KB) | [prosperodev/hdcamera](https://github.com/prosperodev/hdcamera) |
    | PS4 Camera | from PS4 system software 1.50 to 3.15 (65 KB), the file PS Move API tested on a CUH-ZEY2 | [psxdev/luke_firmwares](https://github.com/psxdev/luke_firmwares) |

- **Use a file…** takes a firmware file you have.

The app checks the SHA-256 of the file it has and names the files it knows. A known file turns the header's
**Firmware** box green, with the version, and the line under the file's name says "SHA-256 checked: it is the known
file", with the hash; a file of your own turns the box orange. The SHA-1 is the hash the projects that publish the files quote.

| Firmware | SHA-256 | SHA-1 |
|---|---|---|
| PS5 HD Camera 21.01-03.20.00.04: the download | `10af1aee76fe0057a88db7ebf5f3ebf32430633effb93722be4cd0a9ed4fce54` | `0fa4da31a12b662a9a80abc8b84932770df8f7e1` |
| The same with the Discord and gamma fix | `42ce5f7033a1115988cada3ebb8e0a143e8b241661f203a12275354dd2ba0bf6` | `a5d8aadab91d78e33f4c038798c047066e6713d7` |
| PS4 Camera, from PS4 system software 1.00 to 1.05 | `8262c2a785128a04273bbcf360e29e30c10c9f3b1c3e2571a5eea5b929f41e16` | `7390be76a163c2d4a68d939577d46d7c20165881` |
| PS4 Camera, from PS4 system software 1.50 to 3.15: the download | `d550c4abc416385810ca181867f4dd650198e1214d371ba058005a10f420fd9b` | `fe86162309518a0ffe267075a2fcf728c5856b3e` |
| PS4 Camera, from PS4 system software 3.50 to 5.05 | `a6f99b283b707ece098602aea823415e614db3d64b21a22c53d45476e5405b24` | `c556911796202deef1cbb051390b5c3a2e6c0a7a` |
| PS4 Camera, from PS4 system software 6.00 to 7.02 | `09513d1068b9b5e23b09e03bca5640ed4d01830b034b9802395006b14a927b01` | `8b8a6621d358f6782c2e3b31aac2cdfb25102c00` |

Any other file of a sensible size is your choice, and the app calls it an own file. It refuses a file it knows to be
the other camera's firmware. The files are kept in `~/.local/share/bc250-usb-hdcam/firmware/`: `cfi-zey1.bin` for
the PS5 HD Camera, `ps4-camera.bin` for the PS4 Camera.

## Loading by itself

With **Load it by itself when the camera is plugged in** on (the default), you do not need to open the app again
once the camera has its firmware file and access. The installer adds a service for your user,
`~/.config/systemd/user/bc250-usb-hdcam-load.service`. It sends the firmware:

- when the camera is plugged in, started by the udev rule;
- at login, for a camera that was plugged in before.

It runs as your user, not as root. To see what it did:

```bash
journalctl --user -u bc250-usb-hdcam-load.service
```

With the option off, the service does nothing and **Load firmware** in the window's header sends the firmware. While
the window is open it also sends the firmware itself, once per plug-in, when the service could not (for example
because the firmware file or the access came later).

Without the app, the same is a terminal command:

```bash
bc250-usb-hdcam --load      # sends the firmware to every camera that waits for it
```

### After a restart

When the board restarts, the camera may not come back at all: `lsusb` does not list it, and the load service
finds no camera. The USB port keeps its power through a restart, so the camera keeps running its firmware, but it
does not connect to the restarted system. Unplug it and plug it in again: it starts as a boot loader, and the load
service sends the firmware as usual. Switching the port off and on from Linux does not bring it back on the BC-250.
After a shutdown and power on, the camera starts fresh, and the load service sends its firmware at login.
When no camera is found, the window and the load service's journal say the same.

## The picture

Once the camera is ready, the header shows its video node and the **Picture** box offers every mode the camera
reports, each frame size at each of its rates. The camera has two image sensors, and its modes are of two kinds:

| Kind | Frame sizes |
|---|---|
| One camera | 1920 × 1080, 1280 × 800, 960 × 520, 640 × 376, 448 × 256, 320 × 184 |
| Both cameras, side by side | 3840 × 1080, 2560 × 800, 1920 × 520, 1280 × 376, 896 × 256, 640 × 184 |
| Both cameras and smaller copies of them | 5148 × 1088 |

The list shows what your camera reports, with the largest one-camera mode first. Not every mode gives a picture.
With Reduced bandwidth some fast side-by-side modes do not fit, and their frames arrive damaged; and at 15 fps the
1080-line modes send nothing at all. After a few seconds the window says which, and stops the preview. Measured on
the BC-250 with Reduced bandwidth:

| Mode | Picture |
|---|---|
| Every one-camera mode, at every rate, but one | yes |
| 1920 × 1080 at 15 fps | none: the camera sends nothing (at 30 and 8 fps it works) |
| 2560 × 800 at 30, 15 or 8 fps; 1920 × 520 at 60; 1280 × 376 at 120; 896 × 256 at 120; 640 × 184 at 240 | yes |
| 3840 × 1080 and 5148 × 1088 at 8 fps | yes |
| 3840 × 1080 and 5148 × 1088 at 15 fps | none: the camera sends nothing |
| 2560 × 800 at 60; 3840 × 1080 and 5148 × 1088 at 30 | frames damaged: too much for the bandwidth |

For a side-by-side mode, **Show** picks the whole frame or either half. Each half is the lens on that side as you
face the camera: the left half is the lens on your left, which is the camera's right lens seen from behind it.
**Save picture…** saves what the preview shows, at the camera's own size, as a PNG. The preview shows up to 30 frames
a second, fewer in the largest modes; other apps get every frame the camera sends.

While the preview runs, the app holds the camera, and other apps cannot use it. **Stop preview** (or closing the
window) gives it back.

## Picture settings

Beside the preview, **Picture settings** shows the camera's own settings, as it reports them: on the PS5 HD Camera
brightness, contrast, saturation, hue, gain and sharpness (0 to 8, hue 0 to 11), automatic white balance or a color
temperature, the power line frequency (50 or 60 Hz, against flicker under lamps) and the exposure (Auto, or Shutter
Priority, the camera's default). A setting that another one decides is grayed: the color temperature while the white
balance is automatic. **Defaults** puts every setting back.

The app sets **Auto Exposure** to **Auto Mode** unless you choose otherwise: in its own default mode, Shutter
Priority, the camera keeps a short exposure, and the picture stays dark even in a well-lit room. **Defaults** keeps
Auto Mode too. Measured at 1280 × 800 (the average brightness of a
frame, 0 to 255):

| Setting | Brightness | Near black | White clipped |
|---|---|---|---|
| The camera's default (Shutter Priority) | 48 | 24 % | 0 % |
| Auto Mode | 111 | 0 % | 4 % |
| Auto Mode, gain 8 | 136 | 0 % | 6 % |
| Auto Mode, brightness 8 | 166 | 0 % | 9 % |
| Shutter Priority, brightness 8 | 112 | 0 % | 1 % |

Gain changes the picture only in Auto Mode. The camera reports an exposure time, but it cannot be used, so the app
shows it grayed, for completeness. The camera has no manual exposure: it marks the exposure time as set by its
automatic exposure in both of its modes, Linux's driver therefore refuses it, and a value sent to the camera directly
is put back to 1000 when the picture starts. Besides these, the camera has one vendor control of its own (an
extension unit, 3 bytes) that nothing documents; the app leaves it alone.

The camera forgets its settings when it is unplugged. The app keeps the ones you changed and sets them again each
time the camera is ready, also when the load service loaded it, so other apps get the same picture. They work while
another app shows the camera too, so you can open the window to adjust the picture of a call or a stream.

## Using it in other apps

Any app that uses a webcam finds the camera as **USB Camera-OV580**. In OBS, add a **Video Capture Device (V4L2)**
source and choose that device. A one-camera mode such as 1920 × 1080 gives an ordinary webcam picture. Many apps
pick the camera's first mode by themselves; choose the resolution in the app if it offers one.

## PS4 Camera

The PS4 Camera (CUH-ZEY1 or CUH-ZEY2) on Sony's PlayStation Camera Adapter (CFI-ZAA1) starts as the same boot
loader. The app knows it by the adapter between them and shows **PS4 Camera**; the adapter does not say which of the
two models it is. It has its own firmware, which **Download…** gets for it, and the same USB bandwidth setting
applies. Once loaded, it is USB ID `05a9:058a`. A PS4 Camera on a homemade adapter, without Sony's, looks like a PS5
HD Camera to the app and is not supported.

## Install

Install it from the BC250 Bazzite Suite portal, or from a clone or release folder, as your own user:

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
./install.sh --uninstall             # remove the app, its udev rule and its load service; keeps its settings and firmware
./install.sh --uninstall --purge     # also remove its settings and firmware
```

It installs:

- the app in `~/.local/share/bc250-usb-hdcam/app`, with the `bc250_core` it was tested with;
- PyQt6 in the suite's shared venv `~/.local/share/bc250-bazzite-suite/venv`;
- the launcher `~/.local/bin/bc250-usb-hdcam`, an app menu entry and a Desktop icon;
- the load service `~/.config/systemd/user/bc250-usb-hdcam-load.service`, enabled for your login.

Settings are kept in `~/.config/bc250-usb-hdcam/bc250-usb-hdcam.ini`.

## Credits

The upload protocol was found by the PS4EYECam driver (Antonio Jose Ramos Marquez) and is used by
[PS Move API](https://github.com/thp/psmoveapi), whose camera firmware loader this app follows. The firmware file
and the camera's USB description come from [prosperodev/hdcamera](https://github.com/prosperodev/hdcamera).

## License

GPL-3.0-or-later — see [LICENSE](https://github.com/RobertoTorino/nexus/blob/main/apps/hdcam/LICENSE).
The camera's firmware is Sony's and is not part of the app.
