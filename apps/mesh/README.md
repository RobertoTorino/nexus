<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# BC-250 Mesh Shaders

Gives games on the **AMD BC-250** mesh shaders on **Bazzite**, through RADV with
[DirectMesh](https://github.com/lonewolf0622/bc250meshtaskwork), built on the board and installed beside the
system Mesa. Games use it only after its test passed on the running kernel.

How to install and use it: [BC-250 Mesh Shaders in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/mesh/).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The DirectMesh patch in `mesa/` is the published patch of
[DirectMesh](https://github.com/lonewolf0622/bc250meshtaskwork) by lonewolf0622, unchanged, and MIT, as Mesa. The
suite's patch in `mesa/`, applied on top of it, is GPL-3.0-or-later, as the app.
