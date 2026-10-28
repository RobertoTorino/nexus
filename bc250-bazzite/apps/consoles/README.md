<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Console Link

Console Link connects the **AMD BC-250** on **Bazzite** to your PS4 or PS5: find the consoles on your network, wake
them from rest mode, register the board with them, and start a session and its stream.

How to install and use it: [Console Link in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/consoles/).

## Disclaimer

Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the Bazzite
/ Universal Blue project, Sony, Microsoft, Nintendo, Valve, or the makers of the emulators and the other programs the
apps work with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. PlayStation, PS4, PS5, PS3,
PS2, PSP, PS Vita, PSN, DualSense and Remote Play are Sony's; Xbox, Xbox 360, Xbox Cloud Gaming, Game Pass and
Windows are Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of Nintendo's consoles, of the
emulators (shadPS4, RPCS3, PPSSPP, PCSX2, Vita3K, Xenia) and of Decky Loader, HelixSR and DirectMesh belong to their
owners. The suites use them only to say what their apps work with.

## License

AGPL-3.0, see [LICENSE](LICENSE). The protocol code is ported from [chiaki-ng](https://github.com/streetpea/chiaki-ng)
(AGPL-3.0-only with an OpenSSL exception); those files keep that license. They are the files marked
`SPDX-License-Identifier: AGPL-3.0-only`, modified from chiaki-ng's code (ported to Python and Rust, from
12-10-2026 on); the code and tests call chiaki-ng "the reference". The app's own files are AGPL-3.0-or-later. The native core links [FFmpeg](https://ffmpeg.org), LGPL-2.1-or-later (see
[native/ffmpeg/COPYING.LGPLv2.1](native/ffmpeg/COPYING.LGPLv2.1)), built from its own sources by
`native/ffmpeg/build.sh`.
