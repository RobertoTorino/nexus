<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

![BC-250 Mesh Shaders](../assets/mesh/bc250-mesh-shaders.webp){ .app-logo }

# BC-250 Mesh Shaders

Gives games on the **AMD BC-250** **mesh shaders**. Newer DirectX 12 games (DirectX 12 Ultimate) draw their scenes
with mesh shaders. Some need them to start; others fall back to an older path without them.

The BC-250's GPU has an older design than the one mesh shaders were made for, so the stock Mesa driver does not offer
them. [DirectMesh](https://github.com/lonewolf0622/bc250meshtaskwork) adds them to RADV (Mesa's Vulkan driver) for
the BC-250, drawing every mesh shader on a route that avoids the patterns that hang this chip. The app builds RADV
with DirectMesh and installs it **beside** the system Mesa, which is never changed. Games use it only when you say
so, and only after the app's test passed on the running kernel.

The DirectMesh project reports Final Fantasy VII Rebirth, Control, Hellblade 2, Alan Wake 2 and Crimson Desert
running with it on a BC-250. Only games that use mesh shaders gain anything.

!!! warning "Changes the board"
    The app installs a GPU driver that games use instead of the system's. It is software-only and can be undone:
    **Remove** takes the driver out again, and the system Mesa stays as it was. Read this chapter first.

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

Installing the app changes nothing on the board. Open **BC-250 Mesh Shaders** and go through the four steps.

1. **Build.** Builds RADV with DirectMesh, as your own user, in a Fedora container. It downloads the Mesa source
   and the build tools (several hundred MB) and takes 20 to 40 minutes. Nothing on the system changes.
2. **Install.** Copies the driver to `/usr/local/lib/bc250-mesh-shaders` (asks for your password). Nothing uses it
   yet.
3. **Test.** Runs the mesh test with the installed driver, a few minutes. Games only get the driver once the test
   has passed on the running kernel.
4. **Use.** **Copy launch options** and paste them into the game's *Properties → Launch options* in Steam:

    ```
    /usr/local/bin/bc250-mesh-shaders-run %command%
    ```

    When the test has not passed on the running kernel (after a kernel update, or with a new driver), the game
    starts with the system Mesa instead, and `~/.local/state/bc250-mesh-shaders/run.log` says why.

The status next to the title sums it up: **Not built**, **Not installed**, **Test needed**, **Ready** or
**Test failed**.

The driver is for the games you give the launch options; there is no switch to make it every app's driver.

## The test

The test draws a grid of 256 colored tiles four ways: with a task shader and a mesh shader, with a mesh shader alone
at the largest size a mesh shader may have (the driver has to split it on this chip), and both again from an
indirect draw. It compares every pixel with the color its tile must have.

Meanwhile the BC-250's compute queues (the ACE), which DirectMesh opens, work beside the draws: each copies an image
through the driver's own copy shaders and runs dispatches whose last workgroup is a partial one, and the results are
compared word for word. Task shaders run on the GPU's compute side too, so the test has both at work at once. When a
DirectMesh release keeps these queues closed, the test says so and checks the draws alone.

It does this ten times, each time with a new Vulkan device, and checks the kernel log for GPU ring timeouts and
resets.

A failed test means: don't use the driver on this kernel. Its output is in
`~/.local/state/bc250-mesh-shaders/test.log`.

!!! note "Why a test per kernel"
    The compute queues need fixes in the kernel to be set up and torn down properly, and Bazzite's kernel does not
    have them. The driver runs without them, as BC-250 ACE Queues does, but each kernel is tested before games may
    use it.

## Switches

**Switches…** puts the driver's switches in front of the launch options, for comparisons and for finding the cause of
a problem in one game. Leave them all off to play, unless the game needs one: off is the driver as DirectMesh ships
it. After a change, copy the launch options to the game again.

| Switch | What it does |
|---|---|
| No indexed mesh draws (`RADV_BC250_MESH_IDXPASS=0`) | Keeps DirectMesh's protected mesh routes, without its indexed mesh draws. |
| No renumbered vertices (`RADV_BC250_MESH_SAFE_COMPACT=0`) | A workgroup whose culling left unused vertices exports private triangle corners instead of only the vertices it uses. |
| Private corners only (`RADV_BC250_MESH_SAFE_ADAPTIVE=0`) | No shared vertices at all: every triangle exports its own corners. Slower; the most cautious route. |
| DirectMesh off (`RADV_DIRECTMESH=0`) | The driver falls back to its base BC-250 settings, for a comparison on the same driver. |
| Hide mesh shaders (`RADV_DEBUG=nomeshshader`) | The game does not see mesh shaders and takes its own path without them, for a comparison. |
| Split mesh shaders that write memory (`RADV_BC250_MESH_SPLIT_WRITES=1`) | For a game whose large mesh shaders write to buffers (PS5 emulators): the driver splits them anyway and runs those writes once. It cannot check that the game never reads them back in the same draw, so only for the game that needs it. |

`run.log` notes the switches each game was started with.

## When the kernel or the app changes

- **A kernel update:** games with the launch options start with the system Mesa until you run the test again.
- **A Mesa update of the system:** changes nothing for the driver: it is built from the Mesa release its DirectMesh
  release is made for.
- **An update of the app** can bring a newer DirectMesh release (see [New DirectMesh releases](#new-directmesh-releases)).
  The Build step then says so: build and install again, then run the test.

## New DirectMesh releases

Each version of the app builds one DirectMesh release, whose patch it brings along; the Build step names it. When the
app starts, it asks GitHub whether DirectMesh has a newer release (one small request), and the Build step says what
it found: **DirectMesh v1.x is out**, with a link to its release notes, or that the one it builds is the newest.

The app does not build a newer release by itself. A new version of the app brings it, from the portal, once its
patch has been checked; then build, install and test again. Clear **Look for a newer DirectMesh release at start**
to stop the request; the link in the Build step looks once.

## If something goes wrong

- **A game does not start, hangs or shows corruption:** take the launch options out of the game, or try it with
  **Switches…** to narrow the cause down. If the test passed, please report it with the game, the switches and
  `run.log`.
- **The board locks up during a game:** a GPU hang. DirectMesh asks for hang reports with the kernel parameter
  `amdgpu.gpu_recovery=0` (the board then stays reachable over SSH), `dmesg`, the game and its launch options.
- **Remove** in the window removes the driver. Take the launch options out of your games first: without the driver
  they do not start.

## Together with BC-250 ACE Queues

Both apps install a driver of their own, and a game uses one of them. DirectMesh opens the compute queues as BC-250
ACE Queues does, so a game that needs mesh shaders gets async compute from this driver too. Give a game the launch
options of one app only.

## From a terminal

The window runs `bc250-mesh-shaders.sh` in the app's folder (`/opt/bc250-mesh-shaders`). The same steps by hand:

```bash
/opt/bc250-mesh-shaders/bc250-mesh-shaders.sh --status
/opt/bc250-mesh-shaders/bc250-mesh-shaders.sh --build            # as your own user
sudo /opt/bc250-mesh-shaders/bc250-mesh-shaders.sh --install-driver
/opt/bc250-mesh-shaders/bc250-mesh-shaders.sh --test
sudo /opt/bc250-mesh-shaders/bc250-mesh-shaders.sh --remove-driver
```

## What goes where

| Where | What |
|---|---|
| `/opt/bc250-mesh-shaders` | the app (root-owned) |
| `~/.cache/bc250-mesh-shaders` | the Mesa source and your build; removed when you uninstall the app |
| `~/.local/state/bc250-mesh-shaders` | test results, the test log and `run.log` |
| `/usr/local/lib/bc250-mesh-shaders` | the installed driver and the mesh test |
| `/usr/local/bin/bc250-mesh-shaders-run` | the launch options wrapper |

On Bazzite `/usr/local` is `/var/usrlocal`: writable, and kept across image updates, so the driver needs no
layering and no reboot.

Uninstalling the app (`./install.sh --uninstall`) removes the app and the build, and leaves an installed driver as
it is; remove that first with **Remove**. `--purge` also removes the settings and the test results.

## How it is built

- **Mesa source:** the release from `archive.mesa3d.org` that the DirectMesh release is made for, checked against
  its signature with the keys of the Mesa release maintainers (from Mesa's own source, bundled with the app).
- **The patch** (`mesa/bc250-directmesh-mesa-<version>.patch`): the patch DirectMesh publishes with its release
  for stock Mesa, bundled with the app and checked against the SHA-256 the release publishes.
- **The suite's patch** (`mesa/bc250-suite-mesa-<version>.patch`): applied on top of DirectMesh's, with what the
  suite adds to it: mesh shaders that write memory can be split (the switch above). The Build step names it by the
  start of its SHA-256 (`suite patch 1a2b3c4d`); when an app update changes it, build again.
- **The build:** RADV alone (no OpenGL, no LLVM), with the prefix `/usr/local/lib/bc250-mesh-shaders`, in a
  `registry.fedoraproject.org/fedora` container of your Bazzite's Fedora version, so it links against the same
  libraries. The driver's game profiles (`drirc`) point at the system's.

`bc250-mesh-shaders.sh --version` names the DirectMesh release and the Mesa version an app version builds.

## Credits

- [DirectMesh](https://github.com/lonewolf0622/bc250meshtaskwork) by LoneWolf (MIT): the mesh shader support, and
  the game results above.
- [Mesa](https://mesa3d.org/) (MIT).
