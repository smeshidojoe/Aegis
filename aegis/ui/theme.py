"""
Размеры, цвета, шрифты и общие куски отрисовки.

Все размеры — в логических пикселях (Qt сам умножает на масштаб экрана).
Пропорции — как у строки Spotty: ~760x476, ряд 44, скругление 20.
"""

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QGraphicsBlurEffect, QGraphicsPixmapItem,
                               QGraphicsScene)

# --- геометрия -------------------------------------------------------------- #
PANEL_W = 760
PANEL_H = 476
RADIUS = 20
SHADOW = 36            # поле вокруг строки под тень; окно больше строки на него

SEARCH_H = 60
FOOTER_H = 50
ROW_H = 46
HEADER_H = 30
LIST_PAD = 8           # отступ списка от краёв строки
ICON = 28

# --- цвета ------------------------------------------------------------------ #
TEXT = QColor(255, 255, 255, 235)
TEXT_DIM = QColor(255, 255, 255, 140)
TEXT_FAINT = QColor(255, 255, 255, 92)
SELECTION = QColor(255, 255, 255, 24)
HOVER = QColor(255, 255, 255, 14)
HAIRLINE = QColor(255, 255, 255, 18)
BORDER = QColor(255, 255, 255, 34)
KEYCAP = QColor(255, 255, 255, 22)
ACCENT = QColor(10, 132, 255)
DANGER = QColor(255, 105, 97)
BADGE = QColor(10, 132, 255, 64)       # метка «Для этого окна»
BADGE_TEXT = QColor(122, 186, 255)

SUCCESS = QColor(48, 209, 88)
WARNING = QColor(255, 159, 10)
# Поверх стекла: без затемнения белый текст на светлых обоях не читается.
GLASS_OVERLAY = QColor(16, 16, 20, 168)
# Когда стекло выключено или OpenGL недоступен.
SOLID = QColor(26, 26, 31, 248)
FIELD = QColor(255, 255, 255, 14)
FIELD_FOCUS = QColor(255, 255, 255, 22)
MENU_BG = QColor(40, 40, 46, 252)

# Сильный ease-out для интерфейса (cubic-bezier(0.23, 1, 0.32, 1)): встроенные
# кривые Qt слишком вялые — начало движения запаздывает.
def ease_out():
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(0.23, 1.0), QPointF(0.32, 1.0), QPointF(1.0, 1.0))
    return curve


# --- шрифты ----------------------------------------------------------------- #
_family = None


def family():
    """Segoe UI Variable на Windows 11, Segoe UI на Windows 10."""
    global _family
    if _family is None:
        families = set(QFontDatabase.families())
        _family = next((f for f in ("Segoe UI Variable Text", "Segoe UI")
                        if f in families), QFont().family())
    return _family


def font(px, weight=QFont.Weight.Normal):
    f = QFont(family())
    f.setPixelSize(px)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


# --- общие куски отрисовки -------------------------------------------------- #

def rounded(rect, radius):
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    return path


def _cap_font(label, px):
    # Значки вроде ↵ в Segoe UI заметно мельче букв того же кегля.
    return font(px + 3 if len(label) == 1 and not label.isalnum() else px,
                QFont.Weight.Medium)


def keycap(p, x, center_y, label, px=11):
    """Клавиша-подсказка; возвращает её ширину. Рисует от x вправо."""
    p.setFont(_cap_font(label, px))
    width = max(20.0, p.fontMetrics().horizontalAdvance(label) + 10.0)
    rect = QRectF(x, center_y - 10, width, 20)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(KEYCAP)
    p.drawRoundedRect(rect, 5, 5)
    p.setPen(TEXT_DIM)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
    return width


def keycaps_width(p, labels, px=11, gap=4):
    """p=None — мерить без художника: размер окна считают до отрисовки."""
    total = 0.0
    for label in labels:
        cap = _cap_font(label, px)
        if p is None:
            metrics = QFontMetrics(cap)
        else:
            p.setFont(cap)
            metrics = p.fontMetrics()
        total += max(20.0, metrics.horizontalAdvance(label) + 10.0)
    return total + gap * max(0, len(labels) - 1)


def draw_keycaps(p, x, center_y, labels, px=11, gap=4):
    for label in labels:
        x += keycap(p, x, center_y, label, px) + gap
    return x


def magnifier(p, center, size, color):
    """Значок поиска в строке ввода."""
    r = size * 0.36
    c = QPointF(center.x() - size * 0.08, center.y() - size * 0.08)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, max(1.6, size / 11), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(c, r, r)
    p.drawLine(QPointF(c.x() + r * 0.72, c.y() + r * 0.72),
               QPointF(center.x() + size * 0.42, center.y() + size * 0.42))
    p.restore()


def blurred_shadow(width, height, radius, blur, color):
    """
    Тень под скруглённым прямоугольником: настоящий гаусс через сцену.

    QGraphicsDropShadowEffect не годится — обрезается границей виджета и на
    светлом фоне даёт жёсткий край. Считается один раз на размер.
    """
    w, h = int(width + blur * 2), int(height + blur * 2)
    src = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    src.fill(Qt.GlobalColor.transparent)
    p = QPainter(src)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(blur, blur, width, height), radius, radius)
    p.end()

    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(src))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(blur)
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)

    out = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    scene.render(p, QRectF(out.rect()), QRectF(src.rect()))
    p.end()
    return out


SCROLLBAR_QSS = """
QScrollBar:vertical { background: transparent; width: 10px; margin: 6px 2px 6px 0; }
QScrollBar::handle:vertical { background: rgba(255,255,255,38); border-radius: 3px;
                              min-height: 32px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: rgba(255,255,255,70); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def qss_color(color):
    return "rgba(%d,%d,%d,%d)" % (color.red(), color.green(), color.blue(), color.alpha())


# Поле ввода в формах (разблокировка, редактор записи).
FIELD_QSS = """
QLineEdit, QPlainTextEdit {
    background: rgba(255,255,255,14); border: 1px solid rgba(255,255,255,20);
    border-radius: 8px; padding: 6px 10px; color: rgba(255,255,255,235);
    selection-background-color: rgba(10,132,255,150);
}
QLineEdit:focus, QPlainTextEdit:focus {
    background: rgba(255,255,255,22); border: 1px solid rgba(10,132,255,200);
}
QLineEdit[error="true"] { border: 1px solid rgba(255,105,97,220); }
"""


def letter_tile(p, rect, title, seed=""):
    """Значок записи: цветная плитка с первой буквой. Иконки сайтов не качаем —
    иначе каждый сайт из базы узнал бы, что он в ней есть."""
    import zlib
    text = (title or "?").strip()[:1].upper() or "?"
    hue = zlib.crc32((seed or title or "?").lower().encode("utf-8")) % 360
    color = QColor.fromHsl(hue, 150, 92)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(rect, rect.width() * 0.26, rect.width() * 0.26)
    p.setFont(font(int(rect.height() * 0.5), QFont.Weight.DemiBold))
    p.setPen(QColor(255, 255, 255, 240))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    p.restore()
