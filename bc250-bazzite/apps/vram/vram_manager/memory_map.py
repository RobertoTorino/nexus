# SPDX-License-Identifier: GPL-3.0-or-later
"""The memory map: the 16 GB of the board as one bar (the VRAM split, the system RAM and what the firmware keeps),
the GTT the GPU may borrow from that RAM, and the swap that holds pages compressed (zram, zswap) or on disk.

It shows the figures of system.read_memory() (fixed for this boot) and system.read_usage() (live), and, for a split
picked but not booted yet, a preview of the next boot. Hover a part for what it is. It only reads; nothing here
changes the board."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from bc250_core.theme import BLUE, GREEN, GREY, ORANGE, PURPLE
from bc250_core.widgets import hide_tooltip, show_tooltip

from .system import TOTAL_MIB, Memory, Usage, mib_text

FIRMWARE = "#5f6368"
ZSWAP = "#00838f"
BAR_H = 30
ROW_H = 18                              # one line of text
GAP = 8

TIPS = {
    "vram_used": ("VRAM in use: {used} of the {split} split. The split is the part of the 16 GB the GPU keeps for "
                  "itself, set in CMOS and read at boot. The screen's framebuffers must fit in it: when a game "
                  "fills it, the next frame cannot be shown and the session ends (Bazzite Test, test 37)."),
    "vram_free": "Free VRAM: {mib} of the split is not in use now. Linux cannot use it for anything else.",
    "vram": "The VRAM split: {mib}, the part of the 16 GB the GPU keeps for itself, set in CMOS and read at boot.",
    "gtt": ("GTT in use: the GPU borrows {mib} of system RAM now. When the VRAM split is full, the GPU grows into "
            "the RAM like this, up to the GTT limit (the bracket below the bar)."),
    "zram": ("zram: {ram} of RAM holds {stored} of swapped-out pages, compressed. Pages Linux swaps out stay in RAM, "
             "only smaller, so swapping is fast."),
    "zswap": ("zswap: {ram} of RAM holds {stored} of pages, compressed, on their way to the swap device. Pages that "
              "do not fit in its pool go to the swap device itself."),
    "used": ("RAM used by Linux and the apps: {mib}. Together with the GPU's borrowed pages and the compressed swap "
             "next to it, this is MemTotal minus MemAvailable."),
    "available": "Available RAM: {mib} can still be used by apps and games without swapping (MemAvailable).",
    "ram": "System RAM: {mib}, the part of the 16 GB Linux and the games run in.",
    "firmware": ("Kept at boot by the firmware and the kernel: {mib}. It is neither VRAM nor RAM Linux can hand out."),
    "preview_vram": "After the reboot the split would be {mib}.",
    "preview_ram": "After the reboot the system would have about {mib} of RAM.",
}


@dataclass(frozen=True)
class Part:
    key: str
    label: str
    mib: int
    colour: str
    tip: str
    light: bool = False                 # a free or previewed part: drawn pale, with dark text


def ram_layout(memory: Memory, usage: Usage | None = None, split_mib: int | None = None) -> list[Part]:
    """The parts of the 16 GB bar, left to right. With *split_mib*, the next boot's layout (no usage): the split
    moves, the RAM takes or gives the difference and the firmware's share stays."""
    vram, ram = memory.vram_mib or 0, memory.ram_mib or 0
    if not vram or not ram:
        return []
    firmware = max(TOTAL_MIB - vram - ram, 0)
    parts: list[Part] = []
    if split_mib is not None:
        new_ram = max(ram + vram - split_mib, 0)
        parts += [Part("preview_vram", "VRAM split", split_mib, PURPLE, fmt("preview_vram", split_mib), True),
                  Part("preview_ram", "System RAM", new_ram, GREY, fmt("preview_ram", new_ram), True)]
    else:
        used = usage.vram_used_mib if usage else None
        if used is None:
            parts.append(Part("vram", "VRAM split", vram, PURPLE, fmt("vram", vram)))
        else:
            used = min(used, vram)
            parts += [Part("vram_used", "VRAM used", used, PURPLE,
                           TIPS["vram_used"].format(used=mib_text(used), split=mib_text(vram))),
                      Part("vram_free", "free", vram - used, PURPLE, fmt("vram_free", vram - used), True)]
        available = usage.ram_available_mib if usage else None
        if available is None:
            parts.append(Part("ram", "System RAM", ram, GREY, fmt("ram", ram)))
        else:
            left = max(ram - min(available, ram), 0)          # what is in use, handed out below
            pieces = []
            for key, label, mib, colour in (
                    ("gtt", "GPU borrows", usage.gtt_used_mib or 0, BLUE),
                    ("zram", "zram", sum(z.ram_mib for z in usage.zram), ORANGE),
                    ("zswap", "zswap", usage.zswap_pool_mib or 0, ZSWAP)):
                mib = min(mib, left)
                left -= mib
                pieces.append((key, label, mib, colour))
            for key, label, mib, colour in pieces:
                if mib:
                    parts.append(Part(key, label, mib, colour, swap_tip(key, usage) if key != "gtt" else
                                      fmt("gtt", mib)))
            parts.append(Part("used", "Linux and apps", left, GREY, fmt("used", left)))
            parts.append(Part("available", "available", min(available, ram), GREEN,
                              fmt("available", min(available, ram)), True))
    if firmware:
        parts.append(Part("firmware", "firmware", firmware, FIRMWARE, fmt("firmware", firmware)))
    return parts


def fmt(key: str, mib: int) -> str:
    return TIPS[key].format(mib=mib_text(mib))


def swap_tip(key: str, usage: Usage) -> str:
    if key == "zram":
        stored, ram = sum(z.stored_mib for z in usage.zram), sum(z.ram_mib for z in usage.zram)
    else:
        stored, ram = usage.zswap_stored_mib or 0, usage.zswap_pool_mib or 0
    return TIPS[key].format(stored=mib_text(stored), ram=mib_text(ram))


def gtt_ceiling(memory: Memory, split_mib: int | None = None) -> int | None:
    """The most RAM the GPU may borrow: the TTM limit, but never more than the RAM. For the next boot with
    *split_mib*: a TTM limit on the kernel command line stays; the kernel's default is half the RAM."""
    if split_mib is None:
        return memory.gtt_mib
    if not memory.vram_mib or not memory.ram_mib:
        return None
    ram = max(memory.ram_mib + memory.vram_mib - split_mib, 0)
    ttm = memory.ttm_limit_mib if memory.ttm_on_cmdline and memory.ttm_limit_mib else ram // 2
    return min(ttm, ram)


def gtt_text(memory: Memory, usage: Usage | None) -> tuple[str, str]:
    """The bracket's two lines: the GTT limit and what the GPU borrows, and what the TTM limit does."""
    ceiling = memory.gtt_mib
    now = f" (it borrows {mib_text(usage.gtt_used_mib)} now)" if usage and usage.gtt_used_mib is not None else ""
    first = f"GTT: the GPU may borrow up to {mib_text(ceiling)} of the RAM{now}"
    if memory.ttm_limit_mib is None:
        return first, ""
    ttm = mib_text(memory.ttm_limit_mib)
    if memory.gtt_capped:
        second = f"TTM limit {ttm} is above the RAM, so the GTT stops at the RAM"
    elif memory.ttm_on_cmdline:
        second = f"TTM limit {ttm} (ttm.pages_limit on the kernel command line) sets the GTT"
    else:
        second = f"TTM limit {ttm}: the kernel's default, half the RAM"
    return first, second


def swap_rows(memory: Memory, usage: Usage | None) -> list[tuple[str, str, float, float, str]]:
    """One row per swap: (text, color, stored share, RAM share, tooltip); the shares are of the bar's width.
    A row with no bar (shares 0) is a line of text only."""
    rows = []
    for z in (usage.zram if usage else ()):
        ratio = f", {z.ratio:.1f}×" if z.ratio else ""
        text = (f"{z.name}: {mib_text(z.stored_mib)} of pages in {mib_text(z.ram_mib)} of RAM "
                f"({z.algorithm or 'compressed'}{ratio}), swap size {mib_text(z.size_mib)}")
        tip = (f"zram is swap kept in RAM, compressed. The light part is what it holds ({mib_text(z.stored_mib)}), "
               f"the dark part what that costs in RAM ({mib_text(z.ram_mib)}); the whole bar is its swap size "
               f"({mib_text(z.size_mib)}).")
        size = z.size_mib or 1
        rows.append((text, ORANGE, min(z.stored_mib / size, 1), min(z.ram_mib / size, 1), tip))
    if memory.zswap:
        pool = (memory.ram_mib or 0) * (usage.zswap_max_pool_percent or 0) // 100 if usage else 0
        stored = usage.zswap_stored_mib if usage else None
        ram = usage.zswap_pool_mib if usage else None
        text = "zswap: on"
        if stored is not None and ram is not None:
            text = f"zswap: {mib_text(stored)} of pages in {mib_text(ram)} of RAM"
        if usage and usage.zswap_compressor:
            text += f" ({usage.zswap_compressor})"
        if pool:
            text += f", pool up to {mib_text(pool)} ({usage.zswap_max_pool_percent}% of the RAM)"
        tip = ("zswap is a compressed cache in RAM in front of the swap device: pages Linux swaps out are kept "
               "there, compressed, while the pool has room, and go to the swap device when it is full. The bar is "
               "the pool's limit.")
        rows.append((text, ZSWAP, min((stored or 0) / pool, 1) if pool else 0, min((ram or 0) / pool, 1)
                     if pool else 0, tip))
    elif memory.zram:
        rows.append(("zswap: off. That is usual with zram: zswap compresses pages on their way to a swap device, "
                     "and zram already keeps them compressed in RAM.", ZSWAP, 0, 0,
                     "zswap is a compressed cache in RAM in front of a swap device. In front of zram it would only "
                     "compress the pages twice."))
    elif memory.disk_swap:
        rows.append(("zswap: off. It could keep swapped-out pages compressed in RAM in front of the disk swap.",
                     ZSWAP, 0, 0, "zswap is a compressed cache in RAM in front of a swap device."))
    if usage and usage.disk_swap_size_mib:
        size = usage.disk_swap_size_mib
        rows.append((f"disk swap: {mib_text(usage.disk_swap_used_mib)} used of {mib_text(size)}", GREY,
                     min(usage.disk_swap_used_mib / size, 1), 0,
                     "Swap on the disk: slow, but it does not take RAM."))
    if not rows:
        rows.append(("No swap.", GREY, 0, 0, "Without swap, Linux cannot move unused pages out of the RAM."))
    return rows


class MemoryMap(QWidget):
    def __init__(self, memory: Memory, parent: QWidget | None = None):
        super().__init__(parent)
        self.memory = memory
        self.usage: Usage | None = None
        self.preview: int | None = None
        self.zones: list[tuple[QRectF, str]] = []
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._fit()

    def set_usage(self, usage: Usage) -> None:
        self.usage = usage
        self._fit()
        self.update()

    def set_preview(self, split_mib: int | None) -> None:
        """Show the next boot with this split, or nothing (None, or the split the system has now)."""
        self.preview = split_mib if split_mib and split_mib != self.memory.vram_mib else None
        self._fit()
        self.update()

    def content_height(self) -> int:
        h = ROW_H + BAR_H + GAP + 2 * ROW_H + ROW_H             # caption, bar, GTT bracket, legend
        if self.preview is not None:
            h += GAP + ROW_H + BAR_H + GAP + ROW_H
        rows = swap_rows(self.memory, self.usage)
        h += GAP + ROW_H + sum(ROW_H + (10 if stored or ram else 0) + 4 for _, _, stored, ram, _ in rows)
        return h + 4

    def _fit(self) -> None:
        self.setFixedHeight(self.content_height())

    # --- Drawing --------------------------------------------------------------------------------------------------

    def _text(self, p: QPainter, x: float, y: float, text: str, dim: bool = False, bold: bool = False) -> None:
        font = self.font()
        font.setBold(bold)
        p.setFont(font)
        role = QPalette.ColorRole.PlaceholderText if dim else QPalette.ColorRole.WindowText
        p.setPen(self.palette().color(role))
        width = self.width() - x
        p.drawText(QRectF(x, y, width, ROW_H), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideRight, int(width)))

    def _bar(self, p: QPainter, y: float, parts: list[Part], dashed: bool = False) -> list[tuple[Part, QRectF]]:
        """Draws the parts; a part too narrow for its label and size goes into self.unlabelled for the legend."""
        width = self.width()
        x, out = 0.0, []
        self.unlabelled: list[Part] = []
        metrics = QFontMetrics(self.font())
        for part in parts:
            w = width * part.mib / TOTAL_MIB
            rect = QRectF(x, y, w, BAR_H)
            colour = QColor(part.colour)
            if part.light:
                colour.setAlpha(70)
            p.fillRect(rect, colour)
            pen = QPen(self.palette().color(QPalette.ColorRole.Window), 1)
            if dashed:
                pen = QPen(QColor(part.colour), 1.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
            text = f"{part.label} {mib_text(part.mib)}"
            if metrics.horizontalAdvance(text) > w - 8:
                self.unlabelled.append(part)
                text = part.label if metrics.horizontalAdvance(part.label) <= w - 8 else ""
            if text:
                p.setPen(self.palette().color(QPalette.ColorRole.WindowText) if part.light else QColor("white"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            self.zones.append((rect, part.tip))
            out.append((part, rect))
            x += w
        return out

    def _legend(self, p: QPainter, y: float, parts: list[Part]) -> None:
        """A color square, name and size for each part the bar had no room to label."""
        metrics = QFontMetrics(self.font())
        p.setFont(self.font())
        x = 0.0
        for part in parts:
            text = f"{part.label} {mib_text(part.mib)}"
            w = 14 + metrics.horizontalAdvance(text) + 16
            if x + w > self.width():
                break
            colour = QColor(part.colour)
            if part.light:
                colour.setAlpha(70)
            p.fillRect(QRectF(x, y + 4, 10, 10), colour)
            p.setPen(self.palette().color(QPalette.ColorRole.WindowText))
            p.drawText(QRectF(x + 14, y, w, ROW_H), Qt.AlignmentFlag.AlignVCenter, text)
            self.zones.append((QRectF(x, y, w, ROW_H), part.tip))
            x += w

    def _bracket(self, p: QPainter, y: float, x: float, w: float) -> None:
        p.setPen(QPen(QColor(BLUE), 2))
        p.drawLine(QPointF(x + 1, y), QPointF(x + 1, y + 6))
        p.drawLine(QPointF(x + 1, y + 6), QPointF(x + w - 1, y + 6))
        p.drawLine(QPointF(x + w - 1, y), QPointF(x + w - 1, y + 6))

    def paintEvent(self, _event) -> None:
        self.zones = []
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = 0.0
        parts = ram_layout(self.memory, self.usage)
        if not parts:
            self._text(p, 0, y, "The VRAM split and the RAM are not known: no amdgpu device, or no /proc/meminfo.",
                       dim=True)
            return
        self._text(p, 0, y, f"The {TOTAL_MIB // 1024} GB of GDDR6, as the firmware divided it at this boot (live)",
                   dim=True)
        y += ROW_H
        drawn = self._bar(p, y, parts)
        y += BAR_H
        ram_x = next(rect.x() for part, rect in drawn if part.key not in ("vram", "vram_used", "vram_free"))
        ceiling = gtt_ceiling(self.memory) or 0
        bracket_w = self.width() * min(ceiling, self.memory.ram_mib or 0) / TOTAL_MIB
        self._bracket(p, y + 2, ram_x, bracket_w)
        first, second = gtt_text(self.memory, self.usage)
        self.zones.append((QRectF(ram_x, y, bracket_w, GAP + 2 * ROW_H),
                           "The GTT limit: how much of the system RAM the GPU may borrow on top of the split. amdgpu "
                           "takes it from ttm.pages_limit (by default half the RAM) and never makes it larger than "
                           "the RAM."))
        y += GAP
        self._text(p, ram_x, y, first)
        self._text(p, ram_x, y + ROW_H, second, dim=True)
        y += 2 * ROW_H
        self._legend(p, y, self.unlabelled)
        y += ROW_H

        if self.preview is not None:
            y += GAP
            self._text(p, 0, y, f"After a reboot with a {mib_text(self.preview)} split (preview)", bold=True)
            y += ROW_H
            drawn = self._bar(p, y, ram_layout(self.memory, split_mib=self.preview), dashed=True)
            y += BAR_H
            ram_x = drawn[1][1].x()
            new_ceiling = gtt_ceiling(self.memory, self.preview) or 0
            self._bracket(p, y + 2, ram_x, self.width() * new_ceiling / TOTAL_MIB)
            y += GAP
            self._text(p, ram_x, y, f"GTT: up to about {mib_text(new_ceiling)} of the RAM")
            y += ROW_H

        y += GAP
        self._text(p, 0, y, "Swap: where Linux puts pages it moves out of the RAM", dim=True)
        y += ROW_H
        for text, colour, stored, ram, tip in swap_rows(self.memory, self.usage):
            self._text(p, 0, y, text)
            row = QRectF(0, y, self.width(), ROW_H)
            y += ROW_H
            if stored or ram:
                back = QColor(colour)
                back.setAlpha(30)
                p.fillRect(QRectF(0, y, self.width(), 10), back)
                light = QColor(colour)
                light.setAlpha(110)
                p.fillRect(QRectF(0, y, self.width() * stored, 10), light)
                p.fillRect(QRectF(0, y, self.width() * ram, 10), QColor(colour))
                row = row.united(QRectF(0, y, self.width(), 10))
                y += 10
            self.zones.append((row, tip))
            y += 4
        p.end()

    def tip_at(self, pos: QPointF) -> str:
        return next((tip for rect, tip in self.zones if rect.contains(pos)), "")

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.ToolTip:
            tip = self.tip_at(QPointF(event.pos()))
            if tip:
                show_tooltip(event.globalPos(), tip, self)   # the app's rounded tooltip, as every other one
            else:
                hide_tooltip()
                event.ignore()
            return True
        return super().event(event)
