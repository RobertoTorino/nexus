#
# This file is part of mymc+, based on mymc by Ross Ridge.
#
# mymc+ is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mymc+ is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with mymc+.  If not, see <http://www.gnu.org/licenses/>.
#

"""The PS2 memory card code of mymc++ (github.com/Adubbz/mymcplusplus, GPL-3.0-or-later, by Adubbz, based on mymc+
by Florian Märkl and mymc by Ross Ridge), kept as it is at commit 3247c9c0afac2b88b489f8d65f3e106176e0c859
(28-07-2026, version 3.2.0): the card's file system with its ECC, icon.sys and the 3D icon, and the save formats
with LZARI. Its command line, its wxPython window and its OpenGL icon viewer are not here: the Memory cards tab
(memcard_page.py, on memcards.py) takes their place.

Every line changed from that commit carries a "bc250:" comment:

* names on the card read and written as latin-1 instead of ASCII, so a byte over 127 no longer stops the card
  being read (mymc++ issue #11); ASCII names read the same;
* a save with a folder in it can be deleted (a str and bytes mix-up in _remove_dir);
* a failed import (a full card) takes out what it wrote and raises its own error (the cleanup mixed str and bytes
  and raised a TypeError instead, leaving half a save on the card);
* a 3D icon frame without keys is read as 8 bytes, not 16 (issue #26), so the texture after it is found;
* the ECC code no longer prints a debug line for every page whose ECC it corrects, and packing or unpacking a
  .max save no progress on stderr;
* LZARI never loads a native module named mymcsup from the path, and always uses its Python codec;
* a .max export with a title that has no ASCII form writes ? for those characters instead of failing.
"""
