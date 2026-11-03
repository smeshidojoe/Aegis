"""
Иконка Aegis — в одном стиле с остальными программами: плоская чёрная плитка
и толстый белый знак, щит с замочной скважиной. Без градиентов и бликов: знак
должен читаться и на 16 px, и в трее.

Рисуется кодом, а не хранится картинкой: этим же кодом tools/make_assets.py
собирает app.ico, а в рантайме — значок в трее и в плашках.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap

PLATE = QColor("#000000")
GLYPH = QColor("#ffffff")


def _shield_path(rect):
    """Щит, вписанный в rect: прямой верх, бока сходятся к острому низу."""
    s, x0, y0 = rect.width(), rect.x(), rect.y()
    top = y0 + s * 0.08
    left, right = x0 + s * 0.14, x0 + s * 0.86
    mid = x0 + s * 0.5
    path = QPainterPath()
    path.moveTo(mid, top - s * 0.02)
    path.cubicTo(QPointF(mid + s * 0.14, top + s * 0.06), QPointF(right - s * 0.08, top + s * 0.04),
                 QPointF(right, top + s * 0.06))
    path.cubicTo(QPointF(right, y0 + s * 0.55), QPointF(mid + s * 0.2, y0 + s * 0.8),
                 QPointF(mid, y0 + s * 0.94))
    path.cubicTo(QPointF(mid - s * 0.2, y0 + s * 0.8), QPointF(left, y0 + s * 0.55),
                 QPointF(left, top + s * 0.06))
    path.cubicTo(QPointF(left + s * 0.08, top + s * 0.04), QPointF(mid - s * 0.14, top + s * 0.06),
                 QPointF(mid, top - s * 0.02))
    path.closeSubpath()
    return path


def _keyhole_path(rect):
    s, x0, y0 = rect.width(), rect.x(), rect.y()
    cx, cy = x0 + s * 0.5, y0 + s * 0.42
    r = s * 0.1
    path = QPainterPath()
    path.addEllipse(QPointF(cx, cy), r, r)
    stem = QPainterPath()
    stem.moveTo(cx - r * 0.45, cy)
    stem.lineTo(cx + r * 0.45, cy)
    stem.lineTo(cx + r * 0.75, y0 + s * 0.66)
    stem.lineTo(cx - r * 0.75, y0 + s * 0.66)
    stem.closeSubpath()
    return path.united(stem)


def glyph(p, rect, color, hole=None):
    """Щит со скважиной в rect. hole — цвет скважины; None — прорезать насквозь."""
    shield = _shield_path(rect)
    keyhole = _keyhole_path(rect)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    if hole is None:
        p.drawPath(shield.subtracted(keyhole))
    else:
        p.drawPath(shield)
        p.setBrush(hole)
        p.drawPath(keyhole)


def paint(p, rect, edge=False):
    """
    Иконка приложения в rect: плитка и щит.
    edge=True — тонкая светлая кромка, чтобы чёрная плитка не терялась на
    тёмном фоне.
    """
    rect = QRectF(rect)
    s = rect.width()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = rect.adjusted(s * 0.03, s * 0.03, -s * 0.03, -s * 0.03)
    path = QPainterPath()
    path.addRoundedRect(tile, tile.width() * 0.22, tile.width() * 0.22)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(PLATE)
    p.drawPath(path)
    if edge:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        p.drawPath(path)
    inner = tile.width() * (0.66 if s <= 24 else 0.6)
    glyph(p, QRectF(tile.center().x() - inner / 2, tile.center().y() - inner / 2, inner, inner),
          GLYPH, hole=PLATE)
    p.restore()


def pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint(p, QRectF(0, 0, size, size))
    p.end()
    return pm


# --- трей ------------------------------------------------------------------- #

# Размеры, которые Windows спрашивает у значка в трее при разных масштабах.
TRAY_SIZES = (16, 20, 24, 32, 40, 48)
# Доля клетки под знак: соседние значки в трее нарисованы с полями.
TRAY_GLYPH_RATIO = 0.9


def tray_pixmap(size, color, locked=True):
    """Одноцветный щит. Открытая база — щит без скважины: видно с первого взгляда."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    side = size * TRAY_GLYPH_RATIO
    offset = (size - side) / 2
    rect = QRectF(offset, offset, side, side)
    if locked:
        glyph(p, rect, color)
    else:
        p.setPen(QPen(color, max(1.4, size / 12)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_shield_path(rect.adjusted(size * 0.04, size * 0.04, -size * 0.04,
                                              -size * 0.04)))
    p.end()
    return pm
