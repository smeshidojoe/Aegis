"""
Страница настроек — живёт внутри той же строки, вместо списка записей
(перенесено из Spotty). Всё применяется сразу, кнопки «Сохранить» нет.

Пока база заперта, видна только общая часть, расширение и обновления:
безопасность, копии и импорт без открытой базы не нужны и не работают.
"""

import os
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..core import autostart
from ..core.config import DEFAULTS, UPDATE_MODES
from ..core.constants import APP_VERSION
from ..core.i18n import DEFAULT, LANGUAGES, tr
from ..vault import browsers
from . import live_glass, theme
from .widgets import Button, HotkeyField, Segmented, Toggle

LOCK_MINUTES = (5, 15, 30, 60, 0)
CLEAR_SECONDS = (10, 20, 45, 0)
GENERATOR_LENGTHS = (12, 16, 20, 28, 40)
BACKUPS_SHOWN = 5


def _label(text, px=14, color=theme.TEXT, weight=QFont.Weight.Normal):
    label = QLabel(text)
    label.setFont(theme.font(px, weight))
    label.setStyleSheet("color: %s; background: transparent;" % theme.qss_color(color))
    return label


class _ElidedLabel(QWidget):
    """Путь, обрезанный посередине: начало и имя папки важнее середины."""

    def __init__(self, text, px=13, color=theme.TEXT):
        super().__init__()
        self.text = text
        self.color = color
        self.setFont(theme.font(px))
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setToolTip(text)

    def sizeHint(self):
        return QSize(40, self.fontMetrics().height())

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setFont(self.font())
        p.setPen(self.color)
        text = self.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideMiddle,
                                             self.width())
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   text)


class _RemoveButton(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.underMouse() or self.isDown():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 40 if self.isDown() else 24))
            p.drawEllipse(QRectF(self.rect()))
        p.setPen(QPen(theme.TEXT_DIM, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        c = QRectF(self.rect()).center()
        p.drawLine(QPointF(c.x() - 4, c.y() - 4), QPointF(c.x() + 4, c.y() + 4))
        p.drawLine(QPointF(c.x() + 4, c.y() - 4), QPointF(c.x() - 4, c.y() + 4))


class _Card(QWidget):
    """Группа строк на светлой подложке, между строками — тонкие линии."""

    def __init__(self):
        super().__init__()
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(0)

    def add(self, widget):
        self.box.addWidget(widget)
        return widget

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 12))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        p.setPen(QPen(theme.HAIRLINE, 1))
        for i in range(self.box.count() - 1):
            widget = self.box.itemAt(i).widget()
            if widget is not None and widget.isVisible():
                y = widget.geometry().bottom() + 0.5
                p.drawLine(QPointF(14, y), QPointF(self.width() - 14, y))


def _row(title, subtitle="", control=None, height=52):
    row = QWidget()
    row.setFixedHeight(height)
    box = QHBoxLayout(row)
    box.setContentsMargins(14, 0, 12, 0)
    box.setSpacing(12)
    text = QVBoxLayout()
    text.setSpacing(1)
    text.addStretch(1)
    text.addWidget(_label(title, 14))
    if subtitle:
        row.subtitle = _label(subtitle, 12, theme.TEXT_FAINT)
        text.addWidget(row.subtitle)
    text.addStretch(1)
    box.addLayout(text, 1)
    if control is not None:
        box.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


def _item_row(title, subtitle, button):
    row = QWidget()
    row.setFixedHeight(48)
    box = QHBoxLayout(row)
    box.setContentsMargins(14, 0, 12, 0)
    box.setSpacing(12)
    text = QVBoxLayout()
    text.setSpacing(1)
    text.addStretch(1)
    text.addWidget(_ElidedLabel(title, 14))
    if subtitle:
        text.addWidget(_ElidedLabel(subtitle, 12, theme.TEXT_FAINT))
    text.addStretch(1)
    box.addLayout(text, 1)
    box.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)
    return row


class SettingsPage(QScrollArea):
    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWidgetResizable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                           + theme.SCROLLBAR_QSS)
        self.viewport().setAutoFillBackground(False)
        self._build()
        app.updates.state.connect(self._update_state)
        app.updates.progress.connect(self._update_progress)

    # --- построение -------------------------------------------------------- #

    def _build(self):
        content = QWidget()
        content.setAutoFillBackground(False)
        self.column = QVBoxLayout(content)
        self.column.setContentsMargins(16, 10, 16, 16)
        self.column.setSpacing(12)
        config = self.app.config

        general = _Card()
        self.hotkey = HotkeyField(config.get("hotkey"))
        self.hotkey.changed.connect(self._on_hotkey)
        self.hotkey.recording.connect(self.app.suspend_hotkey)
        self.hotkey_row = general.add(_row(tr("settings.hotkey"), tr("settings.hotkey_sub"),
                                           self.hotkey))
        self.autostart = Toggle(self.app.autostart_enabled())
        self.autostart.toggled.connect(self.app.set_autostart)
        # Из исходников в автозапуск прописался бы python.exe — там выключено.
        self.autostart.setEnabled(autostart.supported())
        general.add(_row(tr("settings.autostart"),
                         "" if autostart.supported() else tr("settings.autostart_dev"),
                         self.autostart))
        current = config.get("language")
        self.language = Segmented(list(LANGUAGES.items()),
                                  current if current in LANGUAGES else DEFAULT)
        self.language.changed.connect(self.app.set_language)
        general.add(_row(tr("settings.language"), control=self.language))
        self.column.addWidget(general)

        # --- вид -------------------------------------------------------------- #
        self.column.addWidget(self._header(tr("settings.look")))
        look = _Card()
        self.glass = Toggle(config.get("glass"))
        self.glass.toggled.connect(self.app.set_glass)
        look.add(_row(tr("settings.glass"), tr("settings.glass_sub"), self.glass))
        self.live_glass = Toggle(config.get("live_glass"))
        self.live_glass.toggled.connect(self.app.set_live_glass)
        look.add(_row(tr("settings.live_glass"), tr("settings.live_glass_sub"),
                      self.live_glass))
        self.live_fps = Segmented([(str(fps), str(fps)) for fps in live_glass.RATES],
                                  str(self._live_rate()))
        self.live_fps.changed.connect(self.app.set_live_fps)
        look.add(_row(tr("settings.live_fps"), tr("settings.live_fps_sub"), self.live_fps))
        self.glass.toggled.connect(self._sync_live)
        self.live_glass.toggled.connect(self._sync_live)
        self._sync_live()
        self.column.addWidget(look)

        # --- безопасность ----------------------------------------------------- #
        self.security_header = self._header(tr("settings.security"))
        self.column.addWidget(self.security_header)
        security = _Card()
        self.lock_idle = Segmented(
            [(str(m), tr("settings.minutes", count=m) if m else tr("settings.never"))
             for m in LOCK_MINUTES], str(config.get("lock_idle_minutes")))
        self.lock_idle.changed.connect(lambda v: self.app.set_lock_idle(int(v)))
        security.add(_row(tr("settings.lock_idle"), tr("settings.lock_idle_sub"),
                          self.lock_idle))
        self.lock_session = Toggle(config.get("lock_on_session"))
        self.lock_session.toggled.connect(lambda on: config.set("lock_on_session", on))
        security.add(_row(tr("settings.lock_session"), tr("settings.lock_session_sub"),
                          self.lock_session))
        self.clear_clip = Segmented(
            [(str(s), tr("settings.seconds", count=s) if s else tr("settings.never"))
             for s in CLEAR_SECONDS], str(config.get("clipboard_clear_s")))
        self.clear_clip.changed.connect(lambda v: config.set("clipboard_clear_s", int(v)))
        security.add(_row(tr("settings.clipboard"), tr("settings.clipboard_sub"),
                          self.clear_clip))
        self.read_url = Toggle(config.get("read_browser_url"))
        self.read_url.toggled.connect(lambda on: config.set("read_browser_url", on))
        security.add(_row(tr("settings.read_url"), tr("settings.read_url_sub"), self.read_url))
        self.gen_length = Segmented([(str(n), str(n)) for n in GENERATOR_LENGTHS],
                                    str(config.get("generator_length")))
        self.gen_length.changed.connect(lambda v: config.set("generator_length", int(v)))
        security.add(_row(tr("settings.gen_length"), tr("settings.gen_length_sub"),
                          self.gen_length))
        self.gen_symbols = Toggle(config.get("generator_symbols"))
        self.gen_symbols.toggled.connect(lambda on: config.set("generator_symbols", on))
        security.add(_row(tr("settings.gen_symbols"), tr("settings.gen_symbols_sub"),
                          self.gen_symbols))
        change = Button(tr("settings.change_password"))
        change.clicked.connect(lambda: self.app.panel.set_mode("change"))
        security.add(_row(tr("settings.master"), tr("settings.master_sub"), change))
        self.security = security
        self.column.addWidget(security)

        # --- копии ------------------------------------------------------------ #
        self.backups_header = self._header(tr("settings.backups"))
        make = Button(tr("settings.backup_now"))
        make.clicked.connect(self.app.backup_now)
        self.backups_header.layout().addWidget(make)
        self.column.addWidget(self.backups_header)
        backups = _Card()
        open_folder = Button(tr("settings.open"))
        open_folder.clicked.connect(lambda: self.app.reveal(self.app.backups.folder))
        backups.add(_row(tr("settings.backup_dir"), os.path.normpath(self.app.backups.folder),
                         open_folder))
        extra = QWidget()
        extra_box = QHBoxLayout(extra)
        extra_box.setContentsMargins(0, 0, 0, 0)
        extra_box.setSpacing(6)
        self.extra_clear = _RemoveButton()
        self.extra_clear.clicked.connect(lambda: self.app.set_backup_extra(""))
        choose = Button(tr("settings.choose"))
        choose.clicked.connect(self.app.choose_backup_extra)
        extra_box.addWidget(self.extra_clear)
        extra_box.addWidget(choose)
        self.extra_row = backups.add(_row(tr("settings.backup_extra"), " ", extra))
        self.backups = backups
        self.column.addWidget(backups)
        self.backup_list = _Card()
        self.column.addWidget(self.backup_list)

        # --- импорт и экспорт ------------------------------------------------- #
        self.data_header = self._header(tr("settings.data"))
        self.column.addWidget(self.data_header)
        data = _Card()
        importer = Button(tr("settings.import"))
        importer.clicked.connect(self.app.import_csv)
        data.add(_row(tr("settings.import_title"), tr("settings.import_sub"), importer))
        exporter = Button(tr("settings.export"))
        exporter.clicked.connect(lambda: self.app.panel.set_mode("verify"))
        data.add(_row(tr("settings.export_title"), tr("settings.export_sub"), exporter))
        self.data = data
        self.column.addWidget(data)
        self.browsers = _Card()
        self.column.addWidget(self.browsers)

        # --- расширение ------------------------------------------------------- #
        self.column.addWidget(self._header(tr("settings.extension")))
        ext = _Card()
        self.bridge = Toggle(config.get("bridge_enabled"))
        self.bridge.toggled.connect(self.app.set_bridge_enabled)
        ext.add(_row(tr("settings.bridge"), tr("settings.bridge_sub"), self.bridge))
        folder = Button(tr("settings.open"))
        folder.clicked.connect(self.app.reveal_extension)
        ext.add(_row(tr("settings.ext_install"), tr("settings.ext_install_sub"), folder))
        self.column.addWidget(ext)
        self.pairs = _Card()
        self.column.addWidget(self.pairs)

        # --- обновления ------------------------------------------------------- #
        self.column.addWidget(self._header(tr("settings.updates")))
        updates = _Card()
        self.auto_update = Toggle(config.get("auto_update"))
        self.auto_update.toggled.connect(self.app.set_auto_update)
        updates.add(_row(tr("settings.auto_update"), control=self.auto_update))
        mode = config.get("update_mode")
        self.update_mode = Segmented([(m, tr("settings.update_mode." + m)) for m in UPDATE_MODES],
                                     mode if mode in UPDATE_MODES else DEFAULTS["update_mode"])
        self.update_mode.changed.connect(self._on_update_mode)
        self.mode_row = updates.add(_row(tr("settings.update_mode"),
                                         tr("settings.update_mode_sub." + self.update_mode.current),
                                         self.update_mode))
        self.update_button = Button(tr("settings.check_now"))
        self.update_button.clicked.connect(self._on_update_button)
        self.update_row = updates.add(_row(tr("settings.version", version=APP_VERSION),
                                           " ", self.update_button))
        self.column.addWidget(updates)

        self.column.addStretch(1)
        self.setWidget(content)
        # setWidget сам включает заливку фона у содержимого — страница стала
        # бы белой поверх стекла.
        content.setAutoFillBackground(False)
        self._update_state(*self.app.updates.last_state())

    @staticmethod
    def _header(title):
        header = QWidget()
        box = QHBoxLayout(header)
        box.setContentsMargins(4, 6, 0, 0)
        box.addWidget(_label(title, 12, theme.TEXT_FAINT, QFont.Weight.DemiBold))
        box.addStretch(1)
        return header

    @staticmethod
    def _clear(card):
        while card.box.count():
            widget = card.box.takeAt(0).widget()
            if widget is not None:
                # Удалится только в цикле событий — до тех пор старая строка
                # рисовалась бы поверх новой.
                widget.hide()
                widget.deleteLater()

    def _fill_backups(self):
        self._clear(self.backup_list)
        items = self.app.backups.all()
        if not items:
            self.backup_list.add(_row(tr("settings.no_backups"), height=44))
        for stamp, path in items[:BACKUPS_SHOWN]:
            restore = Button(tr("settings.restore"))
            restore.clicked.connect(lambda _=False, p=path: self.app.ask_restore(p))
            when = time.strftime("%d.%m.%Y  %H:%M", time.localtime(stamp))
            self.backup_list.add(_item_row(when, os.path.dirname(path), restore))
        if len(items) > BACKUPS_SHOWN:
            self.backup_list.add(_row(tr("settings.more_backups",
                                         count=len(items) - BACKUPS_SHOWN), height=40))
        self.backup_list.update()

    def _fill_browsers(self):
        """Браузеры, найденные на компьютере: прочитать напрямую или выгрузить."""
        self._clear(self.browsers)
        found = browsers.installed()
        if not found:
            self.browsers.add(_row(tr("settings.no_browsers"), height=44))
        for browser in found:
            direct = browsers.can_read(browser)
            button = Button(tr("settings.browser_import" if direct else "settings.browser_export"))
            button.clicked.connect(lambda _=False, k=browser.key: self.app.import_browser(k))
            sub = tr("settings.browser_direct" if direct else "settings.browser_via_export")
            self.browsers.add(_item_row(tr("settings.browser_from", name=browser.name), sub,
                                        button))
        self.browsers.update()

    def _fill_pairs(self):
        self._clear(self.pairs)
        pairs = self.app.config.get("bridge_pairs") or {}
        if not pairs:
            self.pairs.add(_row(tr("settings.no_pairs"), height=44))
        for pair_id, pair in pairs.items():
            remove = Button(tr("settings.unpair"), danger=True)
            remove.clicked.connect(lambda _=False, i=pair_id: self.app.unpair(i))
            self.pairs.add(_item_row(pair.get("name") or "—", tr("settings.paired"), remove))
        self.pairs.update()

    # --- обновление по событиям -------------------------------------------- #

    def refresh(self):
        """Перечитать настройки — при каждом открытии страницы."""
        config = self.app.config
        unlocked = self.app.vault.is_unlocked()
        self.hotkey.set_combo(config.get("hotkey"))
        self.autostart.set_silently(self.app.autostart_enabled())
        self.lock_session.set_silently(config.get("lock_on_session"))
        self.read_url.set_silently(config.get("read_browser_url"))
        self.gen_symbols.set_silently(config.get("generator_symbols"))
        self.bridge.set_silently(config.get("bridge_enabled"))
        self.auto_update.set_silently(config.get("auto_update"))
        self.glass.set_silently(config.get("glass"))
        self.live_glass.set_silently(config.get("live_glass"))
        self.live_fps.current = str(self._live_rate())
        self._sync_live()
        for widget in (self.security_header, self.security, self.backups_header, self.backups,
                       self.backup_list, self.data_header, self.data, self.browsers):
            widget.setVisible(unlocked)
        extra = config.get("backup_extra_dir")
        self.extra_row.subtitle.setText(os.path.normpath(extra) if extra
                                        else tr("settings.backup_extra_sub"))
        self.extra_clear.setVisible(bool(extra))
        if unlocked:
            self._fill_backups()
            self._fill_browsers()
        self._fill_pairs()
        self.verticalScrollBar().setValue(0)

    def _live_rate(self):
        fps = self.app.config.get("live_fps")
        return fps if fps in live_glass.RATES else live_glass.DEFAULT_RATE

    def _sync_live(self):
        # Живому фону нечего обновлять без стекла, частоте — без живого фона.
        glass = self.glass.isChecked()
        self.live_glass.setEnabled(glass)
        self.live_fps.setEnabled(glass and self.live_glass.isChecked())
        self.live_fps.update()

    def _on_hotkey(self, combo):
        ok = self.app.set_hotkey(combo)
        self.hotkey.set_combo(self.app.config.get("hotkey"))
        self.hotkey_row.subtitle.setText(
            tr("settings.hotkey_sub") if ok else tr("settings.hotkey_busy"))
        color = theme.TEXT_FAINT if ok else theme.DANGER
        self.hotkey_row.subtitle.setStyleSheet(
            "color: %s; background: transparent;" % theme.qss_color(color))

    def _on_update_mode(self, mode):
        self.mode_row.subtitle.setText(tr("settings.update_mode_sub." + mode))
        self.app.set_update_mode(mode)

    def _on_update_button(self):
        updates = self.app.updates
        if updates.ready_version():
            self.app.restart_and_update()
        elif updates.latest_available():
            self.app.install_update()
        else:
            self.app.check_updates()

    def _update_progress(self, fraction):
        version = self.app.updates.downloading()
        if version:
            self.update_row.subtitle.setText(tr("update.downloading", version=version,
                                                percent=round(fraction * 100)))

    def _update_state(self, state, version):
        updates = self.app.updates
        if not updates.supported():
            text = tr("update.dev")
        elif state == "downloading":
            text = tr("update.downloading", version=version,
                      percent=round(updates.fraction() * 100))
        elif state:
            text = tr("update." + state, version=version)
        else:
            text = " "
        self.update_row.subtitle.setText(text)
        if updates.ready_version():
            label = tr("settings.restart")
        elif updates.latest_available():
            label = tr("settings.install")
        else:
            label = tr("settings.check_now")
        self.update_button.setText(label)
        self.update_button.setEnabled(updates.supported()
                                      and state not in ("checking", "downloading"))
        self.update_button.updateGeometry()
