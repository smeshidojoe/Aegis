"""
Редактор записи — внутри строки, вместо списка.

Поля по важности сверху вниз: название, логин, пароль, сайт; ниже то, что
нужно реже, — окно программы, код 2FA, последовательность автонабора, заметки.
Ctrl+S или Enter в однострочном поле сохраняет, Esc возвращает к списку.

Пароль скрыт точками; глаз справа показывает его, кубик — генерирует новый
(длина и символы — из настроек). Полоска под полем — грубая оценка стойкости.
"""

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget)

from ..core.autotype import DEFAULT_SEQUENCE
from ..core.i18n import tr
from ..vault import csvio, generator, totp
from ..vault.store import Entry
from . import theme
from .widgets import Button, Toggle

LABEL_W = 120


def _palette(widget):
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, theme.TEXT_FAINT)
    widget.setPalette(palette)


def _line(placeholder=""):
    edit = QLineEdit()
    edit.setFont(theme.font(14))
    edit.setFixedHeight(34)
    edit.setPlaceholderText(placeholder)
    edit.setStyleSheet(theme.FIELD_QSS)
    _palette(edit)
    return edit


def _label(text):
    label = QLabel(text)
    label.setFont(theme.font(13))
    label.setFixedWidth(LABEL_W)
    label.setStyleSheet("color: %s; background: transparent;" % theme.qss_color(theme.TEXT_DIM))
    return label


class _IconButton(QAbstractButton):
    """Значок внутри поля пароля: глаз или кубик."""

    def __init__(self, kind, tooltip):
        super().__init__()
        self.kind = kind
        self.setToolTip(tooltip)
        self.setCheckable(kind == "eye")
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self.underMouse() or self.isDown() or self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 34 if self.isDown() or self.isChecked() else 20))
            p.drawRoundedRect(rect, 8, 8)
        c = rect.center()
        p.setPen(QPen(theme.TEXT_DIM, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.kind == "eye":
            p.drawEllipse(QRectF(c.x() - 7, c.y() - 4.5, 14, 9))
            p.setBrush(theme.TEXT_DIM)
            p.drawEllipse(c, 2, 2)
            if not self.isChecked():
                p.drawLine(c.x() - 7, c.y() + 6, c.x() + 7, c.y() - 6)
        else:
            p.drawRoundedRect(QRectF(c.x() - 6.5, c.y() - 6.5, 13, 13), 3, 3)
            p.setBrush(theme.TEXT_DIM)
            for dx, dy in ((-3, -3), (3, 3), (0, 0)):
                p.drawEllipse(c.x() + dx - 1, c.y() + dy - 1, 2, 2)


class _Strength(QWidget):
    COLORS = [theme.DANGER, theme.DANGER, theme.WARNING, theme.SUCCESS, theme.SUCCESS]

    def __init__(self):
        super().__init__()
        self.level = 0
        self.setFixedHeight(4)

    def set_level(self, level):
        self.level = level
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        gap = 4
        w = (self.width() - gap * 3) / 4
        for i in range(4):
            on = i < self.level
            p.setBrush(self.COLORS[self.level] if on else QColor(255, 255, 255, 18))
            p.drawRoundedRect(QRectF(i * (w + gap), 0, w, 4), 2, 2)


class EntryEditor(QScrollArea):
    saved = Signal(object)
    cancelled = Signal()
    delete_requested = Signal(object)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.entry = None
        self.is_new = False
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                           + theme.SCROLLBAR_QSS)
        self.viewport().setAutoFillBackground(False)
        self._build()
        self._totp_timer = QTimer(self, interval=1000)
        self._totp_timer.timeout.connect(self._update_totp)

    # --- построение -------------------------------------------------------- #

    def _row(self, label, widget):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(_label(label))
        if isinstance(widget, QWidget):
            row.addWidget(widget, 1)
        else:
            row.addLayout(widget, 1)
        self.column.addLayout(row)

    def _build(self):
        content = QWidget()
        self.column = QVBoxLayout(content)
        self.column.setContentsMargins(22, 14, 22, 14)
        self.column.setSpacing(8)

        self.title = _line(tr("editor.title_hint"))
        self._row(tr("editor.title"), self.title)
        self.username = _line(tr("editor.username_hint"))
        self._row(tr("editor.username"), self.username)

        self.password = _line()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setFont(theme.font(14))
        self.password.textChanged.connect(
            lambda text: self.strength.set_level(generator.strength(text)))
        self.eye = _IconButton("eye", tr("editor.show"))
        self.eye.toggled.connect(lambda on: self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        self.dice = _IconButton("dice", tr("editor.generate"))
        self.dice.clicked.connect(self.generate)
        box = QHBoxLayout()
        box.setSpacing(4)
        box.addWidget(self.password, 1)
        box.addWidget(self.eye)
        box.addWidget(self.dice)
        self._row(tr("editor.password"), box)
        self.strength = _Strength()
        strength_row = QHBoxLayout()
        strength_row.addSpacing(LABEL_W + 10)
        strength_row.addWidget(self.strength, 1)
        strength_row.addSpacing(68)
        self.column.addLayout(strength_row)

        self.url = _line("https://example.com")
        self.url.editingFinished.connect(self._title_from_url)
        self._row(tr("editor.url"), self.url)
        self.window = _line(tr("editor.window_hint"))
        self._row(tr("editor.window"), self.window)

        self.totp = _line(tr("editor.totp_hint"))
        self.totp.textChanged.connect(self._update_totp)
        self.totp_code = QLabel()
        self.totp_code.setFont(theme.font(14, QFont.Weight.DemiBold))
        self.totp_code.setMinimumWidth(96)
        self.totp_code.setStyleSheet("color: %s; background: transparent;"
                                     % theme.qss_color(theme.TEXT))
        box = QHBoxLayout()
        box.addWidget(self.totp, 1)
        box.addWidget(self.totp_code)
        self._row(tr("editor.totp"), box)

        self.sequence = _line(DEFAULT_SEQUENCE)
        self._row(tr("editor.sequence"), self.sequence)

        self.notes = QPlainTextEdit()
        self.notes.setFont(theme.font(13))
        self.notes.setFixedHeight(70)
        self.notes.setStyleSheet(theme.FIELD_QSS)
        self.notes.setPlaceholderText(tr("editor.notes_hint"))
        _palette(self.notes)
        self._row(tr("editor.notes"), self.notes)

        self.favorite = Toggle(False)
        fav = QHBoxLayout()
        fav.addWidget(self.favorite)
        fav.addStretch(1)
        self._row(tr("editor.favorite"), fav)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        self.delete = Button(tr("editor.delete"), danger=True)
        self.delete.clicked.connect(lambda: self.delete_requested.emit(self.entry))
        buttons.addWidget(self.delete)
        buttons.addStretch(1)
        cancel = Button(tr("editor.cancel"))
        cancel.clicked.connect(self.cancelled.emit)
        buttons.addWidget(cancel)
        self.save = Button(tr("editor.save"), accent=True)
        self.save.clicked.connect(self.submit)
        buttons.addWidget(self.save)
        self.column.addLayout(buttons)
        self.column.addStretch(1)

        for edit in (self.title, self.username, self.password, self.url, self.window,
                     self.totp, self.sequence):
            edit.returnPressed.connect(self.submit)
        save = QAction(self)
        save.setShortcut("Ctrl+S")
        save.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        save.triggered.connect(self.submit)
        self.addAction(save)

        self.setWidget(content)
        content.setAutoFillBackground(False)

    # --- данные ------------------------------------------------------------ #

    def open(self, entry=None, prefill=None):
        """entry=None — новая запись; prefill — поля для неё (из браузера)."""
        self.is_new = entry is None
        self.entry = entry or Entry(**(prefill or {}))
        e = self.entry
        self.title.setText(e.title)
        self.username.setText(e.username)
        self.password.setText(e.password)
        self.url.setText(e.url)
        self.window.setText(e.window)
        self.totp.setText(e.totp)
        self.sequence.setText(e.sequence)
        self.notes.setPlainText(e.notes)
        self.favorite.set_silently(e.favorite)
        self.eye.setChecked(False)
        self.title.setProperty("error", False)
        self.delete.setVisible(not self.is_new)
        if self.is_new and not e.password:
            self.generate()
        self.strength.set_level(generator.strength(self.password.text()))
        self._update_totp()
        self._totp_timer.start()
        self.verticalScrollBar().setValue(0)

    def close_editor(self):
        self._totp_timer.stop()
        # Пароль не держим в полях дольше нужного.
        self.password.clear()
        self.entry = None

    def focus(self):
        target = self.title if self.is_new and not self.title.text() else self.password \
            if self.is_new else self.title
        target.setFocus()
        target.selectAll()

    def generate(self):
        config = self.app.config
        self.password.setText(generator.generate(config.get("generator_length"),
                                                 config.get("generator_symbols")))

    def _title_from_url(self):
        if not self.title.text().strip() and self.url.text().strip():
            self.title.setText(csvio.title_from_url(self.url.text().strip()))

    def _update_totp(self):
        value = self.totp.text().strip()
        if not value:
            self.totp_code.setText("")
            return
        try:
            code = totp.code(value)
            left = totp.seconds_left(value)
            self.totp_code.setText("%s %s  %ds" % (code[:3], code[3:], left))
        except ValueError:
            self.totp_code.setText(tr("editor.totp_bad"))

    def submit(self):
        self._title_from_url()
        title = self.title.text().strip()
        if not title:
            self.title.setProperty("error", True)
            self.title.style().unpolish(self.title)
            self.title.style().polish(self.title)
            self.title.setFocus()
            return
        e = self.entry
        e.title = title
        e.username = self.username.text().strip()
        e.password = self.password.text()
        e.url = self.url.text().strip()
        e.window = self.window.text().strip()
        e.totp = self.totp.text().strip()
        e.sequence = self.sequence.text().strip()
        e.notes = self.notes.toPlainText()
        e.favorite = self.favorite.isChecked()
        self.saved.emit(e)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)
