# SPDX-License-Identifier: GPL-3.0-or-later
"""A type specimen of the suite's text styles, to pick the weight and letter-spacing that read best on a screen
(owner, 26-10-2026: the bold text is hard to read). It draws the roles the apps use, the window title, a pill's
value and caption, a page title, a state beside a title, a status pill and running text, first as the apps have
them now, then in every combination of weight (600 semibold, 700 bold, 800 extra bold) and letter-spacing (0,
0.5 and 1 px), on the theme, with Inter for the title and the pill's value as the apps have it. Nothing in the apps
changes; the picture is for looking at.

    python tools/type_specimen.py                      # type-specimen.png in the folder you are in
    python tools/type_specimen.py --out FILE --theme silver
    python tools/type_specimen.py --show               # a window instead, on the screen the choice is for
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SUITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SUITE / "core"))

WEIGHTS = (600, 700, 800)
SPACINGS = (0.0, 0.5, 1.0)
# (role, sample text, pixel size, the weight the apps use now, Inter as the apps have it)
ROLES = (
    ("Title", "BC-250 Fan Control", 24, 800, True),
    ("Pill value", "12/27", 22, 800, True),
    ("Page title", "Thermal guard", 20, 700, False),
    ("State", "Running", 14, 700, False),
    ("Status pill", "Installed", 13, 600, False),
    ("Caption", "Install all updates", 12, 600, False),
    ("Text", "The fans follow the curve below.", 13, 400, False),
)


def style(size: int, weight: int, spacing: float, inter: bool) -> str:
    from bc250_core.theme import header_font
    return (header_font() if inter else "") + f"font-size:{size}px; font-weight:{weight}; letter-spacing:{spacing}px;"


def build(theme_key: str | None):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QWidget
    from bc250_core.theme import THEME, THEMES, apply_theme, muted, surface_style
    theme = THEMES[theme_key] if theme_key else THEME
    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app, theme=theme)
    root = QWidget()
    root.setWindowTitle(f"Type specimen: {theme.label}")
    grid = QGridLayout(root)
    grid.setContentsMargins(24, 20, 24, 20)
    grid.setHorizontalSpacing(28)
    grid.setVerticalSpacing(10)
    head = QLabel(f"Weight / letter-spacing  ({theme.label})")
    head.setStyleSheet(f"color:{muted(theme)}; font-size:12px; font-weight:600;")
    grid.addWidget(head, 0, 0)
    for column, (role, _, size, weight, _) in enumerate(ROLES, 1):
        label = QLabel(f"{role}  {size}px, now {weight}")
        label.setStyleSheet(f"color:{muted(theme)}; font-size:12px; font-weight:600;")
        grid.addWidget(label, 0, column)
    rows: list[tuple[str, int | None, float]] = [("As the apps are now", None, 0.0)]
    rows += [(f"{weight} / {spacing:g} px", weight, spacing) for weight in WEIGHTS for spacing in SPACINGS]
    line = QFrame()                                 # under the first row: now above, the variants below
    line.setFrameShape(QFrame.Shape.HLine)
    grid.addWidget(line, 2, 0, 1, len(ROLES) + 1)
    for index, (name, weight, spacing) in enumerate(rows, 1):
        row = index if index == 1 else index + 1
        label = QLabel(name)
        label.setStyleSheet(f"color:{muted(theme)}; font-size:13px; font-weight:600;")
        grid.addWidget(label, row, 0)
        for column, (role, text, size, now, inter) in enumerate(ROLES, 1):
            sample = QLabel(text)
            sample.setStyleSheet(style(size, now if weight is None else weight, spacing, inter))
            if role == "Status pill":                   # as StatusPill draws it: on the surface, in a box
                frame = QFrame()
                frame.setStyleSheet(surface_style(theme.accent, "QFrame", 6, theme))
                inner = QGridLayout(frame)
                inner.setContentsMargins(9, 3, 9, 3)
                inner.addWidget(sample)
                grid.addWidget(frame, row, column, Qt.AlignmentFlag.AlignLeft)
            else:
                grid.addWidget(sample, row, column)
    return app, root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default="type-specimen.png", help="the picture to write (default: type-specimen.png)")
    parser.add_argument("--theme", choices=("gunmetal", "silver", "warm"), help="a theme instead of the chosen one")
    parser.add_argument("--show", action="store_true", help="show a window instead of writing the picture")
    args = parser.parse_args(argv)
    if not args.show:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app, root = build(args.theme)
    if args.show:
        root.show()
        return app.exec()
    root.adjustSize()
    root.grab().save(args.out)
    print(f"wrote {args.out} ({root.width()} x {root.height()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
