# SPDX-License-Identifier: GPL-3.0-or-later
"""The picture on the screen: the chosen values as tiles under a header (the user's text, the time and, if wanted,
the time zone and the date), drawn with QPainter at the screen's size in the chosen theme and colors, on an optional
picture of the user's own, and turned to the chosen orientation, then converted to the screen's RGB565. Tiles fill
one column standing up and two lying down, and everything scales with the screen, so the 5" and 7" models get the
same layout, larger."""

from __future__ import annotations

import sys
import time
from array import array
from dataclasses import dataclass, replace

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform

from bc250_core.sensors import Reading

from .weather import Weather

DASH = "—"
WARM, HOT = 80, 90                       # °C: a temperature turns orange, then red, as in System Overlay
TITLE = "BC-250"

# key, caption; the order on the screen
TILES = (("cpu", "CPU"), ("gpu", "GPU"), ("cpu_temp", "CPU temp"), ("gpu_temp", "GPU temp"), ("vram", "VRAM"),
         ("ram", "RAM"), ("fan", "Fan"), ("vrm", "VRM temp"), ("nvme", "NVMe temp"), ("net", "Network"),
         ("disk", "Disk"), ("weather", "Weather"))
DEFAULT_TILES = ("cpu", "gpu", "vram", "ram", "fan", "net")
# What each tile shows, for the Values tab's tooltips.
TILE_HINTS = {
    "cpu": "The CPU's load, with its clock and temperature.",
    "gpu": "The GPU's load, with its clock, power and temperature.",
    "cpu_temp": "The CPU's temperature in large.",
    "gpu_temp": "The GPU's temperature in large.",
    "vram": "The GPU's share of the memory: used and total.",
    "ram": "The memory: used and total.",
    "fan": "The fastest spinning fan.",
    "vrm": "The temperature of the VRM, the voltage regulators beside the chip that feed it its power.",
    "nvme": "The SSD's temperature.",
    "net": "Download and upload, of the interface chosen below.",
    "disk": "Reads and writes of the disks.",
    "weather": "The temperature and the sky at the place chosen on the Weather tab.",
}
# Turned clockwise by this many degrees from the screen's portrait picture, with the USB cable at the top.
ORIENTATIONS = {"Portrait": 0, "Landscape": 90, "Portrait, upside down": 180, "Landscape, upside down": 270}
ORANGE = QColor(240, 150, 40)
RED = QColor(230, 70, 70)


@dataclass(frozen=True)
class Theme:
    background: QColor
    surface: QColor                      # the tiles
    text: QColor
    muted: QColor                        # captions, details, the time
    bar: QColor                          # the empty part of a bar
    accent: QColor | None = None         # the tiles' edge and bars; None: the suite's theme accent


THEMES = {
    "Dark": Theme(QColor(14, 15, 22), QColor(30, 32, 44), QColor(236, 236, 244), QColor(150, 152, 172),
                  QColor(52, 55, 72)),
    "Light": Theme(QColor(232, 234, 240), QColor(255, 255, 255), QColor(24, 26, 34), QColor(96, 100, 118),
                   QColor(214, 217, 226), QColor(60, 110, 200)),
    "Midnight": Theme(QColor(6, 12, 32), QColor(16, 28, 64), QColor(226, 234, 255), QColor(130, 150, 200),
                      QColor(34, 52, 102), QColor(80, 160, 255)),
    "Ember": Theme(QColor(16, 8, 8), QColor(40, 18, 18), QColor(250, 236, 232), QColor(190, 140, 130),
                   QColor(70, 34, 32), QColor(232, 64, 48)),
    "Forest": Theme(QColor(8, 16, 12), QColor(18, 38, 28), QColor(230, 246, 236), QColor(130, 176, 150),
                    QColor(34, 64, 48), QColor(70, 200, 120)),
    "Mono": Theme(QColor(0, 0, 0), QColor(24, 24, 24), QColor(255, 255, 255), QColor(150, 150, 150),
                  QColor(56, 56, 56), QColor(220, 220, 220)),
}
DEFAULT_THEME = "Dark"
TILE_ALPHA = 215                         # the tiles over a picture: the picture shows through a little
# The theme's colors the user may change: the Theme field for each.
COLOURS = {"text": "text", "tiles": "surface", "accent": "accent", "background": "background"}
SUN, DROP, BOLT = QColor(250, 196, 60), QColor(80, 160, 240), QColor(250, 210, 70)


def with_colours(theme: Theme, colours: dict[str, str]) -> Theme:
    """*theme* with the user's own colors (COLORS' keys, as #rrggbb); an empty or unreadable one keeps the theme's."""
    own = {COLOURS[key]: QColor(value) for key, value in colours.items()
           if key in COLOURS and value and QColor(value).isValid()}
    return replace(theme, **own)


# 24 or 12 hours (with AM/PM); the time zone as its name (CEST) or as the offset (UTC+2); the date in one of DATES.
HOURS = {24: "%H:%M", 12: "%I:%M %p"}
ZONES = ("", "name", "offset")
DATES = {"": "", "weekday": "%a %d %b", "dmy": "%d-%m-%Y", "mdy": "%m/%d/%Y", "ymd": "%Y-%m-%d"}


@dataclass(frozen=True)
class Clock:
    hours: int = 24
    zone: str = ""
    date: str = ""


def offset(local: time.struct_time) -> str:
    """UTC+2, UTC-3:30, UTC+0."""
    minutes = (local.tm_gmtoff or 0) // 60
    sign = "-" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{sign}{hours}" + (f":{rest:02d}" if rest else "")


def zone_text(local: time.struct_time, zone: str) -> str:
    """The zone as the system names it for that moment, so CEST in summer and CET in winter."""
    if zone == "name":
        return local.tm_zone or offset(local)
    return offset(local) if zone == "offset" else ""


def clock_text(when: float | None, clock: Clock = Clock()) -> str:
    """The time, in the system's time zone at that moment (summer and winter time follow by themselves)."""
    local = time.localtime(when)
    text = time.strftime(HOURS.get(clock.hours, HOURS[24]), local)
    if clock.hours == 12:
        text = text.lstrip("0")
    zone = zone_text(local, clock.zone)
    return f"{text} {zone}" if zone else text


def date_text(when: float | None, clock: Clock = Clock()) -> str:
    form = DATES.get(clock.date, "")
    return time.strftime(form, time.localtime(when)) if form else ""


@dataclass(frozen=True)
class Tile:
    caption: str
    value: str
    detail: str = ""
    fraction: float | None = None        # 0..1: a bar under the value
    alert: QColor | None = None          # a temperature that is warm or hot
    icon: str | None = None              # the weather's: weather.Weather.icon
    night: bool = False                  # the icon with a moon instead of a sun


def _temp_alert(*temps: float | None) -> QColor | None:
    hottest = max((t for t in temps if t is not None), default=None)
    if hottest is None or hottest < WARM:
        return None
    return RED if hottest >= HOT else ORANGE


def _temp(value: float | None) -> str | None:
    return f"{value:.0f} °C" if value is not None else None


def _temp_tile(caption: str, value: float | None) -> Tile:
    """A temperature on its own: the bar runs from 0 to 100 °C."""
    return Tile(caption, _temp(value) or DASH, fraction=max(0.0, min(1.0, value / 100)) if value is not None else None,
                alert=_temp_alert(value))


def _join(*parts: str | None) -> str:
    return " · ".join(p for p in parts if p)


def _gb(pair: tuple[int, int] | None) -> str:
    return f"{pair[0] / 1e9:.1f} / {pair[1] / 1e9:.1f} GB" if pair else DASH


def _share(pair: tuple[int, int] | None) -> float | None:
    return pair[0] / pair[1] if pair and pair[1] else None


def _rate(value: float) -> str:
    for unit, size in (("MB/s", 1e6), ("KB/s", 1e3)):
        if value >= size:
            return f"{value / size:.1f} {unit}"
    return f"{value:.0f} B/s"


def _weather(weather: Weather | None, place: str) -> Tile:
    if weather is None:
        return Tile(place or "Weather", DASH, "" if place else "choose a place")
    return Tile(place or "Weather", f"{weather.temperature:.0f} °C", weather.description, icon=weather.icon,
                night=not weather.is_day)


def tiles(r: Reading, keys: tuple[str, ...] | list[str], weather: Weather | None = None,
          place: str = "") -> list[Tile]:
    """The tiles for *keys*, in the screen's order; *place* is the weather's place, as the tile's caption."""
    made = {
        "cpu": lambda: Tile("CPU", f"{r.cpu_load:.0f} %" if r.cpu_load is not None else DASH,
                            _join(f"{r.cpu_mhz} MHz" if r.cpu_mhz else None, _temp(r.cpu_temp)),
                            r.cpu_load / 100 if r.cpu_load is not None else None, _temp_alert(r.cpu_temp)),
        # The BC-250 reports a GPU load only with the GPU governor's fix-metrics; without it the clock is the value.
        "gpu": lambda: Tile("GPU", f"{r.gpu_load:.0f} %" if r.gpu_load is not None
                            else f"{r.gpu_mhz} MHz" if r.gpu_mhz else DASH,
                            _join(f"{r.gpu_mhz} MHz" if r.gpu_mhz and r.gpu_load is not None else None,
                                  f"{r.gpu_watts:.0f} W" if r.gpu_watts is not None else None, _temp(r.gpu_temp)),
                            r.gpu_load / 100 if r.gpu_load is not None else None, _temp_alert(r.gpu_temp)),
        "cpu_temp": lambda: _temp_tile("CPU temp", r.cpu_temp),
        "gpu_temp": lambda: _temp_tile("GPU temp", r.gpu_temp),
        "vram": lambda: Tile("VRAM", _gb(r.vram), fraction=_share(r.vram)),
        "ram": lambda: Tile("RAM", _gb(r.ram), fraction=_share(r.ram)),
        "fan": lambda: Tile("Fan", f"{r.fan.rpm} RPM" if r.fan else DASH, r.fan.label if r.fan else ""),
        "vrm": lambda: Tile("VRM temp", _temp(r.vrm_temp) or DASH, alert=_temp_alert(r.vrm_temp)),
        "nvme": lambda: Tile("NVMe temp", _temp(r.nvme_temp) or DASH, alert=_temp_alert(r.nvme_temp)),
        "net": lambda: Tile("Network", f"↓ {_rate(r.net[0])}" if r.net else DASH,
                            f"↑ {_rate(r.net[1])}" if r.net else ""),
        "disk": lambda: Tile("Disk", f"R {_rate(r.disk[0])}" if r.disk else DASH,
                             f"W {_rate(r.disk[1])}" if r.disk else ""),
        "weather": lambda: _weather(weather, place),
    }
    return [made[key]() for key, _ in TILES if key in keys]


def report(r: Reading, when: float | None = None, weather: Weather | None = None, place: str = "",
           network: str = "", title: str = TITLE) -> str:
    """Every value at *when*, as text: the date and time with its zone, then a line per tile. *network* says which
    interface the Network line measures."""
    local = time.localtime(when)
    lines = [title or "BC-250", time.strftime("%d-%m-%Y %H:%M:%S", local) + f" {local.tm_zone} ({offset(local)})", ""]
    for tile in tiles(r, [k for k, _ in TILES], weather, place):
        caption = f"{tile.caption} ({network})" if tile.caption == "Network" and network else tile.caption
        lines.append(f"{caption:<22} {_join(tile.value, tile.detail)}")
    return "\n".join(lines) + "\n"


def _font(px: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont("Inter")
    font.setPixelSize(max(8, round(px)))
    font.setWeight(weight)
    return font


def _cloud(x: float, y: float, s: float) -> QPainterPath:
    """A cloud *s* wide, its top left at (x, y); about s * 0.62 high."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    path.addEllipse(QRectF(x, y + s * 0.2, s * 0.44, s * 0.42))
    path.addEllipse(QRectF(x + s * 0.22, y, s * 0.5, s * 0.5))
    path.addEllipse(QRectF(x + s * 0.5, y + s * 0.16, s * 0.46, s * 0.46))
    path.addRoundedRect(QRectF(x + s * 0.12, y + s * 0.3, s * 0.76, s * 0.32), s * 0.1, s * 0.1)
    return path.simplified()


def _sun(p: QPainter, cx: float, cy: float, r: float, night: bool) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(SUN)
    if night:
        moon = QPainterPath()
        moon.addEllipse(QPointF(cx, cy), r * 1.25, r * 1.25)
        bite = QPainterPath()
        bite.addEllipse(QPointF(cx + r * 0.7, cy - r * 0.45), r * 1.05, r * 1.05)
        p.drawPath(moon.subtracted(bite))
        return
    p.drawEllipse(QPointF(cx, cy), r, r)
    p.setPen(QPen(SUN, max(1.5, r * 0.22), cap=Qt.PenCapStyle.RoundCap))
    for n in range(8):
        ray = QTransform().translate(cx, cy).rotate(n * 45)
        p.drawLine(ray.map(QPointF(r * 1.35, 0)), ray.map(QPointF(r * 1.75, 0)))


def _draw_icon(p: QPainter, box: QRectF, kind: str, night: bool, theme: Theme) -> None:
    """The weather's icon in the square *box*, drawn rather than taken from a font, so it looks the same everywhere."""
    s, x, y = box.width(), box.left(), box.top()
    if kind == "clear":
        _sun(p, x + s / 2, y + s / 2, s * 0.24, night)
        return
    if kind == "partly":
        _sun(p, x + s * 0.36, y + s * 0.34, s * 0.17, night)
    cloud_top = y + (s * 0.3 if kind == "partly" else s * 0.08)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.muted)
    p.drawPath(_cloud(x + s * 0.04, cloud_top, s * 0.92))
    below = cloud_top + s * 0.6
    if kind == "rain":
        p.setPen(QPen(DROP, max(1.5, s * 0.07), cap=Qt.PenCapStyle.RoundCap))
        for dx in (0.3, 0.5, 0.7):
            p.drawLine(QPointF(x + s * dx, below + s * 0.06), QPointF(x + s * (dx - 0.06), below + s * 0.26))
    elif kind == "snow":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.text)
        for dx, dy in ((0.3, 0.1), (0.5, 0.22), (0.7, 0.1)):
            p.drawEllipse(QPointF(x + s * dx, below + s * dy), s * 0.05, s * 0.05)
    elif kind == "fog":
        p.setPen(QPen(theme.muted, max(1.5, s * 0.06), cap=Qt.PenCapStyle.RoundCap))
        for dy, left, right in ((0.08, 0.14, 0.86), (0.22, 0.24, 0.76)):
            p.drawLine(QPointF(x + s * left, below + s * dy), QPointF(x + s * right, below + s * dy))
    elif kind == "thunder":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BOLT)
        p.drawPolygon(QPolygonF([QPointF(x + s * px, below + s * py) for px, py in
                                 ((0.52, -0.06), (0.36, 0.2), (0.5, 0.2), (0.42, 0.38), (0.66, 0.1), (0.52, 0.1),
                                  (0.6, -0.06))]))


def _draw_tile(p: QPainter, box: QRectF, tile: Tile, theme: Theme, accent: QColor, see_through: bool) -> None:
    unit = min(box.height(), box.width() / 2)
    pad = max(6.0, unit * 0.1)
    surface = QColor(theme.surface)
    if see_through:
        surface.setAlpha(TILE_ALPHA)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(surface)
    p.drawRoundedRect(box, pad, pad)
    edge = tile.alert or accent
    p.setBrush(edge)
    p.drawRoundedRect(QRectF(box.left(), box.top(), max(3.0, pad / 2), box.height()), 2, 2)

    inner = box.adjusted(pad * 1.6, pad * 0.8, -pad, -pad * 0.8)
    caption_px, value_px = unit * 0.17, unit * 0.34
    p.setPen(theme.muted)
    p.setFont(_font(caption_px, QFont.Weight.DemiBold))
    p.drawText(QRectF(inner.left(), inner.top(), inner.width(), caption_px * 1.4),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tile.caption)
    if tile.detail:
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), caption_px * 1.4),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tile.detail)
    p.setPen(tile.alert or theme.text)
    p.setFont(_font(value_px, QFont.Weight.ExtraBold))
    value_top = inner.top() + caption_px * 1.4
    p.drawText(QRectF(inner.left(), value_top, inner.width(), value_px * 1.35),
               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, tile.value)
    if tile.icon:
        size = value_px * 1.5
        _draw_icon(p, QRectF(inner.right() - size, value_top + value_px * 0.675 - size / 2, size, size), tile.icon,
                   tile.night, theme)
    if tile.fraction is not None:
        bar_h = max(4.0, unit * 0.07)
        bar = QRectF(inner.left(), inner.bottom() - bar_h, inner.width(), bar_h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.bar)
        p.drawRoundedRect(bar, bar_h / 2, bar_h / 2)
        fill = max(0.0, min(1.0, tile.fraction))
        if fill > 0:
            p.setBrush(edge)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * fill, bar_h), bar_h / 2, bar_h / 2)


def draw(reading: Reading, keys: tuple[str, ...] | list[str], width: int, height: int, accent: QColor,
         title: str = TITLE, clock: float | None = None, theme: Theme = THEMES[DEFAULT_THEME],
         picture: QImage | None = None, weather: Weather | None = None, place: str = "",
         style: Clock = Clock()) -> QImage:
    """The picture upright, *width* x *height* as it is seen (landscape: wider than high). *accent* is used when the
    theme has none of its own; *picture* fills the background, cut to the screen's shape; *clock* is the moment
    shown (None: now), in *style*."""
    accent = theme.accent or accent
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(theme.background)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    see_through = picture is not None and not picture.isNull()
    if see_through:
        scaled = picture.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
        p.drawImage(0, 0, scaled, (scaled.width() - width) // 2, (scaled.height() - height) // 2, width, height)
    margin = round(min(width, height) * 0.03)
    header_h = round(min(width, height) * 0.1)
    header = QRectF(margin, margin, width - 2 * margin, header_h)
    now, date = clock_text(clock, style), date_text(clock, style)
    p.setPen(theme.muted)
    if date:                                    # the time above the date, both smaller
        p.setFont(_font(header_h * 0.42, QFont.Weight.DemiBold))
        clock_w = p.fontMetrics().horizontalAdvance(now)
        p.drawText(header.adjusted(0, 0, 0, -header_h / 2), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   now)
        p.setFont(_font(header_h * 0.36))
        clock_w = max(clock_w, p.fontMetrics().horizontalAdvance(date)) + margin
        p.drawText(header.adjusted(0, header_h / 2, 0, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   date)
    else:
        p.setFont(_font(header_h * 0.5, QFont.Weight.DemiBold))
        clock_w = p.fontMetrics().horizontalAdvance(now) + margin
        p.drawText(header, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, now)
    p.setPen(theme.text)
    p.setFont(_font(header_h * 0.6, QFont.Weight.ExtraBold))
    title_box = header.adjusted(0, 0, -clock_w, 0)
    p.drawText(title_box, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
               p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, round(title_box.width())))

    shown = tiles(reading, keys, weather, place)
    if shown:
        columns = 2 if width > height else 1
        rows = -(-len(shown) // columns)
        gap = margin
        top = margin + header_h + gap
        cell_w = (width - 2 * margin - gap * (columns - 1)) / columns
        cell_h = (height - top - margin - gap * (rows - 1)) / rows
        for n, tile in enumerate(shown):
            row, column = (n // columns, n % columns)
            box = QRectF(margin + column * (cell_w + gap), top + row * (cell_h + gap), cell_w, cell_h)
            _draw_tile(p, box, tile, theme, accent, see_through)
    p.end()
    return image


def for_screen(image: QImage, degrees: int) -> QImage:
    """The upright picture turned into the screen's own portrait orientation."""
    if degrees % 360 == 0:
        return image
    return image.transformed(QTransform().rotate(-degrees))


def rgb565(image: QImage) -> bytes:
    """The screen's pixels: RGB565, little-endian, rows without padding."""
    image = image.convertToFormat(QImage.Format.Format_RGB16)
    width, height, line = image.width(), image.height(), image.bytesPerLine()
    raw = image.constBits().asstring(image.sizeInBytes())
    if line != width * 2:
        raw = b"".join(raw[y * line:y * line + width * 2] for y in range(height))
    if sys.byteorder == "big":                  # RGB16 is in the machine's byte order
        pixels = array("H", raw)
        pixels.byteswap()
        raw = pixels.tobytes()
    return raw
