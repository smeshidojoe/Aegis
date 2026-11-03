"""
Вопрос внутри строки: «Подключить расширение?», «Сохранить пароль для …?».

Решение — только кнопкой или Esc («нет»). Enter ничего не делает: вопрос
всплывает сам, и случайно нажатый Enter не должен ничего разрешить.
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from . import appicon, theme
from .widgets import Button


class ConfirmPage(QWidget):
    answered = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = ""
        self.text = ""
        column = QVBoxLayout(self)
        column.setContentsMargins(60, 0, 60, 40)
        column.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.no = Button("")
        self.no.setFixedHeight(34)
        self.no.clicked.connect(lambda: self.answered.emit(False))
        self.yes = Button("", accent=True)
        self.yes.setFixedHeight(34)
        self.yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(self.no)
        row.addSpacing(8)
        row.addWidget(self.yes)
        row.addStretch(1)
        column.addLayout(row)

    def ask(self, title, text, yes, no):
        self.title, self.text = title, text
        self.yes.setText(yes)
        self.no.setText(no)
        self.yes.updateGeometry()
        self.no.updateGeometry()
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.answered.emit(False)
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        appicon.paint(p, QRectF(w / 2 - 28, 60, 56, 56), edge=True)
        p.setFont(theme.font(18, QFont.Weight.DemiBold))
        p.setPen(theme.TEXT)
        p.drawText(QRectF(30, 132, w - 60, 28), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(theme.font(13))
        p.setPen(theme.TEXT_DIM)
        p.drawText(QRectF(70, 166, w - 140, 120),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                   | Qt.TextFlag.TextWordWrap, self.text)
