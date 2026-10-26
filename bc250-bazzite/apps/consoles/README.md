<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Console Link

Console Link connects the **AMD BC-250** on **Bazzite** to your PS4 or PS5: find the consoles on your network, wake
them from rest mode, register the board with them, and start a session and its stream.

How to install and use it: [Console Link in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/consoles/).

## Disclaimer

Console Link is an independent project, not affiliated with or endorsed by the makers of PlayStation.
PlayStation, PS4, PS5 and PSN are trademarks of their owner.

## License

AGPL-3.0, see [LICENSE](LICENSE). The protocol code is ported from [chiaki-ng](https://github.com/streetpea/chiaki-ng)
(AGPL-3.0-only with an OpenSSL exception); those files keep that license. They are the files marked
`SPDX-License-Identifier: AGPL-3.0-only`, modified from chiaki-ng's code (ported to Python and Rust, from
12-10-2026 on); the code and tests call chiaki-ng "the reference". The app's own files are AGPL-3.0-or-later. The native core links [FFmpeg](https://ffmpeg.org), LGPL-2.1-or-later (see
[native/ffmpeg/COPYING.LGPLv2.1](native/ffmpeg/COPYING.LGPLv2.1)), built from its own sources by
`native/ffmpeg/build.sh`.
