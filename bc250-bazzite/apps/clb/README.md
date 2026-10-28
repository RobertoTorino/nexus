<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Console LinkB

Console LinkB streams Xbox games to the **AMD BC-250** on **Bazzite**: sign in with your Microsoft account, wake your
Xbox and play it on the board (Remote Play), or play games from Xbox Cloud Gaming.

How to install and use it: [Console LinkB in the manual](https://robertotorino.github.io/nexus/bc250-bazzite-suite/apps/clb/).

## Disclaimer

Nexus and its suites are independent community projects, not affiliated with or endorsed by AMD, ASRock, the Bazzite
/ Universal Blue project, Sony, Microsoft, Nintendo, Valve, or the makers of the emulators and the other programs the
apps work with. BC-250 is AMD's product name and Bazzite the Universal Blue project's. PlayStation, PS4, PS5, PS3,
PS2, PSP, PS Vita, PSN, DualSense and Remote Play are Sony's; Xbox, Xbox 360, Xbox Cloud Gaming, Game Pass and
Windows are Microsoft's; Steam, Steam Deck and Big Picture are Valve's; the names of Nintendo's consoles, of the
emulators (shadPS4, RPCS3, PPSSPP, PCSX2, Vita3K, Xenia) and of Decky Loader, HelixSR and DirectMesh belong to their
owners. The suites use them only to say what their apps work with.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The protocol code is ported from [Greenlight](https://github.com/unknownskl/greenlight)
and [xal-node](https://github.com/unknownskl/xal-node), both MIT, Copyright (c) 2019 and 2023 UnknownSKL (Jim Kroon);
the files ported from them say so in their header and keep the MIT notice below. The stream uses
[aiortc](https://github.com/aiortc/aiortc) (BSD-3-Clause) and [PyAV](https://github.com/PyAV-Org/PyAV) (BSD-3-Clause,
its wheels bring FFmpeg, LGPL-2.1-or-later), installed from PyPI.

```
The MIT License (MIT)

Copyright (c) 2019 UnknownSKL (Jim Kroon) (Greenlight)
Copyright (c) 2023 UnknownSKL (Jim Kroon) (xal-node)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
