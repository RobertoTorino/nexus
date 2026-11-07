# SPDX-License-Identifier: GPL-3.0-or-later
"""The front page: one tile per feature, in a grid of four by four; the slots no feature fills yet hold a grayed-out
Coming Soon tile, which takes no focus and opens nothing. A tile is a button with the feature's symbol (the shapes of
the controller's buttons for the first four) beside its name, and a few lines on what it opens. The arrow keys move between
the tiles, so a controller through Steam Input (a D-pad as arrow keys, A as Enter) works as well as a mouse.

The symbols are characters every common font has (the geometric shapes, the multiplication sign, the star): the
Dingbats, the mathematical operators and the emoji fall back to another font, which a Qt platform without font
fallback (offscreen on Windows) draws as boxes, and the suite's portal draws its own glyphs for the same reason."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QShowEvent
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .quiz import DATA_CATEGORIES, load_questions
from .style import TEXT, label

COLUMNS, ROWS = 4, 4
TILE_MIN_WIDTH, TILE_HEIGHT = 200, 118          # the tiles share the width of the row
TRIANGLE, CIRCLE, CROSS, SQUARE = "#3dbf9c", "#e8505b", "#6f9fe8", "#e48fc0"   # as USB HD Control draws them


@dataclass(frozen=True)
class Feature:
    key: str
    symbol: str
    colour: str
    name: str
    text: str


FEATURES = (
    Feature("quiz", "△", TRIANGLE, "PlayStation Quiz",            # the count follows the shipped questions file
            f"{len(load_questions()):,} questions in {len(DATA_CATEGORIES)} categories, against the clock. "
            "Perfect rounds earn trophies."),
    Feature("history", "○", CIRCLE, "PlayStation History",
            "Every console since 1994: what it sold, how many titles, and its legacy."),
    Feature("versions", "×", CROSS, "System Version History",
            "Every system software release, from the PS1 to the PS5 and the Portal."),
    Feature("regions", "□", SQUARE, "Region Codes Explained",
            "What the prefix of a title ID and the last digit of a model number say about the region."),
    Feature("guides", "◇", TEXT, "PlayStation User Guides",
            "Sony's online manuals for every PlayStation product, in your browser."),
    Feature("news", "◆", "#FFD166", "PS News",
            "The latest announcements from the PlayStation Blog, upcoming games and new releases."),
    Feature("scores", "★", "#FFD700", "Scores & Trophies",
            "Your best quiz scores and the trophies your perfect rounds earned."),
)
KEYS = tuple(feature.key for feature in FEATURES)


class Tile(QPushButton):
    def __init__(self, feature: Feature, parent: QWidget | None = None):
        super().__init__(parent)
        self.feature = feature
        self.setProperty("tile", True)
        self.setFixedHeight(TILE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(f"Open {feature.name}")
        self.setAccessibleName(feature.name)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(10)
        symbol = QLabel(feature.symbol)
        symbol.setStyleSheet(f"color:{feature.colour}; font-size:24px; font-weight:900;")
        name = QLabel(feature.name)
        name.setStyleSheet(f"color:{TEXT}; font-size:15px; font-weight:800;")
        text = label(feature.text, muted=True, wrap=True)
        text.setStyleSheet("font-size:12px;")
        for widget in (symbol, name, text):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        top.addWidget(symbol)
        top.addWidget(name, 1)
        layout.addLayout(top)
        layout.addWidget(text)
        layout.addStretch(1)

    def minimumSizeHint(self) -> QSize:  # noqa: N802  (Qt's name)
        """A button's own hint knows only its text; the tile's comes from its layout: the name on one line."""
        return self.layout().minimumSize().expandedTo(QSize(TILE_MIN_WIDTH, TILE_HEIGHT))


class ComingSoon(QPushButton):
    """An empty slot of the grid: a tile's frame with "Coming Soon", disabled, so it is grayed out."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__("Coming Soon", parent)
        self.setProperty("tile", True)
        self.setProperty("soon", True)
        self.setMinimumWidth(TILE_MIN_WIDTH)
        self.setFixedHeight(TILE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEnabled(False)


class FrontPage(QWidget):
    opened = pyqtSignal(str)            # a feature's key

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label("What do you want to open?", title=True))
        # The grid scrolls when the window is lower than its four rows (or narrower than its tiles need).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        holder = QWidget()
        self.grid = grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(14)
        self.tiles: list[Tile] = []
        self.coming_soon: list[ComingSoon] = []
        for n in range(COLUMNS * ROWS):
            if n < len(FEATURES):
                tile = Tile(FEATURES[n])
                tile.clicked.connect(lambda _checked=False, key=FEATURES[n].key: self.opened.emit(key))
                self.tiles.append(tile)
            else:
                tile = ComingSoon()
                self.coming_soon.append(tile)
            grid.addWidget(tile, n // COLUMNS, n % COLUMNS)
        for column in range(COLUMNS):
            grid.setColumnStretch(column, 1)
        grid.setRowStretch(ROWS, 1)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802  (Qt's name)
        """Every column as wide as the widest tile needs (known once the fonts are polished), so they stay equal."""
        width = max(tile.minimumSizeHint().width() for tile in self.tiles)
        for column in range(COLUMNS):
            self.grid.setColumnMinimumWidth(column, width)
        super().showEvent(event)

    def tile(self, key: str) -> Tile:
        return next(tile for tile in self.tiles if tile.feature.key == key)

    def focus_tile(self, key: str | None = None) -> None:
        (self.tile(key) if key else self.tiles[0]).setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802  (Qt's name)
        """Arrows move the focus through the grid's features (not onto a Coming Soon slot); Enter and Space open the
        focused tile (a button's own)."""
        focused = self.focusWidget()
        if isinstance(focused, Tile):
            index = self.tiles.index(focused)
            moves = {Qt.Key.Key_Right: 1, Qt.Key.Key_Left: -1, Qt.Key.Key_Down: COLUMNS, Qt.Key.Key_Up: -COLUMNS}
            step = moves.get(event.key())
            if step is not None:
                target = index + step
                if 0 <= target < len(self.tiles):
                    self.tiles[target].setFocus(Qt.FocusReason.OtherFocusReason)
                event.accept()
                return
        super().keyPressEvent(event)
