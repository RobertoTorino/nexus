<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 ACE Queues](../assets/ace/bc250-ace-queues.webp){ .app-logo }

# BC-250 ACE Queues

Lets games on the **AMD BC-250** use its dedicated compute queues (**async compute**). Games split a frame into
graphics work and compute work (lighting, particles, post-processing, upscaling). With a compute queue of its own,
the compute work runs beside the graphics work on shader cores that would otherwise wait.

The BC-250's GPU has these queues (the ACE, Asynchronous Compute Engines), but the stock Mesa driver keeps them
closed: on this chip its compute dispatches came out wrong. The app builds a patched RADV (Mesa's Vulkan driver)
that opens them and runs their dispatches in a mode that works on this chip. That driver is installed **beside**
the system Mesa, which is never changed. Games use it only when you say so, and only after the app's test passed
on the running kernel.

The upstream project measured +21 to +25 % in Cyberpunk 2077 (1440p, Medium, with the 40-CU unlock). The gain
depends on the game: only games that use async compute gain anything.

!!! warning "Changes the board"
    The app installs a GPU driver and can make it the driver of every app. It is software-only and can be
    undone: **Remove** takes the driver out again, and the system Mesa stays as it was. Read this chapter first.

## Before you start

- A BC-250 on **Bazzite** (the app builds for the Fedora version Bazzite is based on).
- About 1 GB free in your home folder during a build, and an internet connection.
- `podman`, which Bazzite ships.

## Using it

Install the app from the BC250 Bazzite Suite portal, where it is under Gaming, or from a clone or release folder,
as your own user (not with sudo):

```bash
./install.sh                         # app menu entry and Desktop icon
./install.sh --no-desktop-shortcut   # app menu entry only
```

Installing the app changes nothing on the board. Open **BC-250 ACE Queues** and go through the four steps.

1. **Build.** Builds the patched RADV for the Mesa version your system has, as your own user, in a Fedora
   container. It downloads the Mesa source and the build tools (several hundred MB) and takes 20 to 40 minutes.
   Nothing on the system changes.
2. **Install.** Copies the driver to `/usr/local/lib/bc250-ace-queues` (asks for your password). Nothing uses it
   yet.
3. **Test.** Runs the ACE queue test with the installed driver, about a minute. Games only get the driver once
   the test has passed on the running kernel.
4. **Use.** Per game, or for every app:
    - **Per game:** **Copy launch options** and paste them into the game's *Properties → Launch options* in Steam:

        ```
        /usr/local/bin/bc250-ace-queues-run %command%
        ```

        When the test has not passed on the running kernel (after a kernel update, or with a new driver), the game
        starts with the system Mesa instead, and `~/.local/state/bc250-ace-queues/run.log` says why.
    - **All apps:** every app uses the patched driver, the desktop included, without launch options. It applies
      after you log out and back in. Flatpak apps keep their own driver.

The status next to the title sums it up: **Not built**, **Not installed**, **Test needed**, **Ready**,
**Test failed** or **On for all apps**.

## The test

The test runs the same work on every compute queue at once: a buffer fill, a buffer copy, a copy into an image and
back (the driver's own copy shaders, where the bug dropped rows), and a compute dispatch whose last workgroup is a
partial one. It compares every result word for word, then closes the queues and opens them again, ten times. It
also checks the kernel log for GPU ring timeouts and resets during the test.

A failed test means: don't use the driver on this kernel. Its output is in
`~/.local/state/bc250-ace-queues/test.log`.

!!! note "Why a test per kernel"
    The upstream fix also patches the kernel, to repair how the compute queues are set up and torn down. Bazzite's
    kernel is not patched. The Bazzite port of the fix runs without the kernel patches on Bazzite's kernels, so
    this app does too, but checks each kernel with its test before games may use the driver.

## When the kernel or Mesa changes

- **A kernel update:** games with the launch options start with the system Mesa until you run the test again.
  With **All apps** on, a check at boot (before anyone logs in) switches it off; the window then says so. Run the
  test, then switch it on again.
- **A Mesa update:** the installed driver keeps working. The Build step says when the system has a newer Mesa;
  build and install again to keep up with it, then run the test.

## If something goes wrong

- **A game does not start, or shows corruption:** take the launch options out of the game. If the test passed,
  please report it with the game and `run.log`.
- **The desktop does not come back after switching on All apps:** press Ctrl+Alt+F3, log in and run:

    ```bash
    sudo rm /etc/environment.d/90-bc250-ace-queues.conf
    sudo reboot
    ```

- **Remove** in the window switches All apps off and removes the driver. Take the launch options out of your games
  first: without the driver they do not start.

## From a terminal

The window runs `bc250-ace-queues.sh` in the app's folder (`/opt/bc250-ace-queues`). The same steps by hand:

```bash
/opt/bc250-ace-queues/bc250-ace-queues.sh --status
/opt/bc250-ace-queues/bc250-ace-queues.sh --build            # as your own user
sudo /opt/bc250-ace-queues/bc250-ace-queues.sh --install-driver
/opt/bc250-ace-queues/bc250-ace-queues.sh --test
sudo /opt/bc250-ace-queues/bc250-ace-queues.sh --all-apps on # or off
sudo /opt/bc250-ace-queues/bc250-ace-queues.sh --remove-driver
```

## What goes where

| Where | What |
|---|---|
| `/opt/bc250-ace-queues` | the app (root-owned) |
| `~/.cache/bc250-ace-queues` | the Mesa source and your build; removed when you uninstall the app |
| `~/.local/state/bc250-ace-queues` | test results, the test log and `run.log` |
| `/usr/local/lib/bc250-ace-queues` | the installed driver and the ACE queue test |
| `/usr/local/bin/bc250-ace-queues-run` | the launch options wrapper |
| `/etc/environment.d/90-bc250-ace-queues.conf`, `/etc/profile.d/90-bc250-ace-queues.sh` | only with All apps on |
| `bc250-ace-queues-guard.service` | only with All apps on: the check at boot |

On Bazzite `/usr/local` is `/var/usrlocal`: writable, and kept across image updates, so the driver needs no
layering and no reboot.

Uninstalling the app (`./install.sh --uninstall`) removes the app and the build, and leaves an installed driver as
it is; remove that first with **Remove**. `--purge` also removes the settings and the test results.

## How it is built

- **Mesa source:** the release from `archive.mesa3d.org` that matches the system's Mesa version, checked against
  its signature with the keys of the Mesa release maintainers (from Mesa's own source, bundled with the app).
- **The patch** (`mesa/gfx1013-ace-queue.patch`, one file, `src/amd/common/ac_gpu_info.c`): opens the compute
  queue on GFX1013 and gives it the async compute workaround RADV already has for the Iceland and Tonga GPUs. That
  workaround runs compute dispatches in thread-dimension mode instead of threadgroup-dimension mode.
- **The build:** RADV alone (no OpenGL, no LLVM), with the prefix `/usr/local/lib/bc250-ace-queues`, in a
  `registry.fedoraproject.org/fedora` container of your Bazzite's Fedora version, so it links against the same
  libraries. The driver's game profiles (`drirc`) point at the system's.

## Credits

- The fix: [DryhoppedIPA/bc250-gfx1013-fix](https://github.com/DryhoppedIPA/bc250-gfx1013-fix) (MIT), with the
  benchmark above.
- The Bazzite port, without the kernel half:
  [tri3gubki-ops/bc250-async-compute-bazzite](https://github.com/tri3gubki-ops/bc250-async-compute-bazzite) (MIT).
- [Mesa](https://mesa3d.org/) (MIT).
