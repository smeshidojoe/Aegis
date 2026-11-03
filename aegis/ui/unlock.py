"""
Страница пароля внутри строки: создать базу, открыть её, сменить мастер-пароль
или подтвердить его перед опасным действием (экспорт в открытый CSV).

Одна страница на все случаи — разница только в наборе полей и подписях:

    setup   — новый пароль и повтор
    locked  — пароль
    verify  — пароль (подтвердить перед действием)
    change  — текущий, новый и повтор

Проверка пароля идёт не здесь: страница отдаёт введённое сигналом submitted,
а ответ (ошибку или успех) ей сообщает программа. Argon2 считается в фоне,
пока на странице «Проверяю…».
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPalette
from PySide6.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from ..core.i18n import tr
from . import appicon, theme
from .widgets import Button

MIN_LENGTH = 8
FIELD_W = 420


class _Field(QLineEdit):
    def __init__(self, placeholder):
        super().__init__()
        self.setEchoMode(QLineEdit.EchoMode.Password)
        self.setFont(theme.font(15))
        self.setFixedHeight(40)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(theme.FIELD_QSS)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, theme.TEXT_FAINT)
        self.setPalette(palette)
        self.textChanged.connect(lambda _t: self.set_error(False))

    def set_error(self, on):
        if self.property("error") != on:
            self.setProperty("error", on)
            self.style().unpolish(self)
            self.style().polish(self)


class _Header(QWidget):
    """Значок, заголовок и подпись над полями — по центру."""

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setFixedHeight(112)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        appicon.paint(p, QRectF(w / 2 - 26, 0, 52, 52), edge=True)
        p.setFont(theme.font(18, QFont.Weight.DemiBold))
        p.setPen(theme.TEXT)
        p.drawText(QRectF(0, 62, w, 26), Qt.AlignmentFlag.AlignCenter, self.page.title)
        p.setFont(theme.font(12))
        p.setPen(theme.TEXT_DIM)
        p.drawText(QRectF(0, 90, w, 20), Qt.AlignmentFlag.AlignCenter, self.page.subtitle)


class UnlockPage(QWidget):
    """submitted(dict): {"password"} | {"password", "new"} — по режиму."""

    submitted = Signal(dict)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "locked"
        self.busy = False
        self.title = ""
        self.subtitle = ""

        # Всё по центру строки: растяжки сверху и снизу делят свободное место
        # поровну, сколько бы полей ни было (одно у «открыть», три у «сменить»).
        column = QVBoxLayout(self)
        column.setContentsMargins(20, 12, 20, 12)
        column.setSpacing(10)
        column.addStretch(1)
        self.header = _Header(self)
        column.addWidget(self.header)
        column.addSpacing(6)
        self.current = _Field(tr("unlock.current"))
        self.password = _Field(tr("unlock.password"))
        self.repeat = _Field(tr("unlock.repeat"))
        for field in (self.current, self.password, self.repeat):
            field.setFixedWidth(FIELD_W)
            field.returnPressed.connect(self.submit)
            column.addWidget(field, 0, Qt.AlignmentFlag.AlignHCenter)
        self.message = QLabel()
        self.message.setFont(theme.font(12))
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Высота постоянная: появившаяся ошибка не сдвигает кнопку.
        self.message.setFixedHeight(18)
        column.addWidget(self.message)
        self.button = Button("", accent=True)
        self.button.setFixedHeight(34)
        self.button.clicked.connect(self.submit)
        column.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)

    # --- режимы ------------------------------------------------------------ #

    def start(self, mode, title=""):
        self.mode = mode
        self.busy = False
        for field in (self.current, self.password, self.repeat):
            field.clear()
            field.set_error(False)
        self.current.setVisible(mode == "change")
        self.repeat.setVisible(mode in ("setup", "change"))
        self.password.setPlaceholderText(tr("unlock.new" if mode in ("setup", "change")
                                            else "unlock.password"))
        self.title = title or tr("unlock.title." + mode)
        self.subtitle = tr("unlock.sub." + mode)
        self.button.setText(tr("unlock.button." + mode))
        self.button.setEnabled(True)
        self._say("")
        self.header.update()

    def first_field(self):
        return self.current if self.mode == "change" else self.password

    def focus(self):
        self.first_field().setFocus()

    # --- ответ программы ----------------------------------------------------- #

    def set_busy(self, on):
        self.busy = on
        self.button.setEnabled(not on)
        self._say(tr("unlock.checking") if on else "")

    def fail(self, text):
        """Пароль не подошёл: поле красным, текст стирается — набирать заново."""
        self.set_busy(False)
        field = self.current if self.mode == "change" else self.password
        field.set_error(True)
        field.clear()
        field.setFocus()
        self._say(text, error=True)

    def _say(self, text, error=False):
        color = theme.DANGER if error else theme.TEXT_FAINT
        self.message.setStyleSheet("color: %s; background: transparent;" % theme.qss_color(color))
        self.message.setText(text)

    # --- ввод -------------------------------------------------------------- #

    def submit(self):
        if self.busy:
            return
        password = self.password.text()
        if self.mode in ("setup", "change"):
            if self.mode == "change" and not self.current.text():
                self.current.set_error(True)
                self.current.setFocus()
                return
            if len(password) < MIN_LENGTH:
                self.password.set_error(True)
                self.password.setFocus()
                self._say(tr("unlock.too_short", count=MIN_LENGTH), error=True)
                return
            if password != self.repeat.text():
                self.repeat.set_error(True)
                self.repeat.clear()
                self.repeat.setFocus()
                self._say(tr("unlock.mismatch"), error=True)
                return
        elif not password:
            self.password.set_error(True)
            return
        if self.mode == "change":
            self.submitted.emit({"password": self.current.text(), "new": password})
        else:
            self.submitted.emit({"password": password})

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)
