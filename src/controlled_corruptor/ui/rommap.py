"""ROM map widget -- a horizontal band showing regions and changed bytes.

Renders the whole file as a bar. Target regions are tinted by category,
protected regions are hatched grey, and after a generation pass the bytes that
actually changed are overlaid. Clicking reports the offset under the cursor.
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core.regions import Region

# Category -> colour. Unknown categories fall back to a neutral tone.
_CATEGORY_COLORS = {
    "models": "#4f9dde",
    "animations": "#8e6fd8",
    "textures": "#e0913a",
    "maps": "#43b581",
    "collision": "#2f8f66",
    "audio": "#d85f9c",
    "text": "#c9c04a",
    "executable": "#c0392b",
    "header": "#7f8c8d",
    "filesystem": "#95a5a6",
    "gameplay": "#16a085",
    "unknown": "#5a6472",
}


def category_color(category: str) -> QColor:
    return QColor(_CATEGORY_COLORS.get(category, _CATEGORY_COLORS["unknown"]))


class RomMapWidget(QWidget):
    offset_hovered = Signal(int)
    offset_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(64)
        self.setMouseTracking(True)
        self._size = 0
        self._targets: List[Region] = []
        self._protected: List[Region] = []
        self._changed: List[Tuple[int, int]] = []

    def set_file(self, size: int, targets: Sequence[Region], protected: Sequence[Region]):
        self._size = max(0, size)
        self._targets = list(targets)
        self._protected = list(protected)
        self._changed = []
        self.update()

    def set_changed(self, intervals: Sequence[Tuple[int, int]]):
        self._changed = list(intervals)
        self.update()

    # -- geometry helpers ---------------------------------------------------
    def _x_for(self, offset: int, width: int) -> float:
        if self._size <= 0:
            return 0.0
        return width * (offset / self._size)

    def _offset_for(self, x: float, width: int) -> int:
        if self._size <= 0 or width <= 0:
            return 0
        return int(max(0, min(self._size - 1, self._size * (x / width))))

    # -- events -------------------------------------------------------------
    def mouseMoveEvent(self, event):
        self.offset_hovered.emit(self._offset_for(event.position().x(), self.width()))

    def mousePressEvent(self, event):
        self.offset_clicked.emit(self._offset_for(event.position().x(), self.width()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()

        # Background = whole file (unknown/unmapped).
        painter.fillRect(0, 0, w, h, QColor("#2b2f3a"))
        if self._size <= 0:
            painter.setPen(QPen(QColor("#888")))
            painter.drawText(self.rect(), Qt.AlignCenter, "no file loaded")
            return

        # Target regions.
        for r in self._targets:
            x0 = self._x_for(r.start, w)
            x1 = self._x_for(r.end, w)
            color = category_color(r.category)
            painter.fillRect(QRectF(x0, 4, max(1.0, x1 - x0), h - 8), QBrush(color))

        # Protected regions (hatched grey on top).
        for r in self._protected:
            x0 = self._x_for(r.start, w)
            x1 = self._x_for(r.end, w)
            painter.fillRect(QRectF(x0, 4, max(1.0, x1 - x0), h - 8),
                             QBrush(QColor("#7f8c8d"), Qt.BDiagPattern))

        # Changed bytes overlay (bright).
        if self._changed:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#ffffff"))
            for s, e in self._changed:
                x0 = self._x_for(s, w)
                x1 = self._x_for(e, w)
                painter.drawRect(QRectF(x0, h - 10, max(1.0, x1 - x0), 6))

        painter.setPen(QPen(QColor("#1b1e26")))
        painter.drawRect(0, 0, w - 1, h - 1)
