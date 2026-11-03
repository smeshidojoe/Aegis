"""
Сама строка: пароль, поиск и список записей, редактор, настройки, вопросы
(перенесено из Spotty).

Режимы:
    setup   — первый запуск: придумать мастер-пароль
    locked  — база заперта: ввести мастер-пароль
    search  — поле поиска и записи
    edit    — новая запись или правка
    settings
    change  — смена мастер-пароля
    verify  — подтвердить мастер-пароль перед экспортом
    confirm — вопрос с двумя кнопками (сопряжение расширения, сохранение пароля)

Показывается мгновенно, без анимации появления: её вызывают с клавиатуры
десятки раз в день. Закрывается, когда теряет фокус, по Esc и после действия.
Кроме одного случая: пока ставится обновление, она заперта карточкой с
прогрессом (ui/update_card.py) — см. locked().

Окно, из которого строку позвали, — self.context (aegis/core/context.py).
Если оно есть, Enter набирает логин и пароль в него; если нет (позвали из
трея) — копирует пароль.
"""

import time

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QCursor, QFont, QGuiApplication, QPainter, QPalette, QPen
from PySide6.QtWidgets import QLineEdit, QWidget

from ..actions import actions_for, confirm_delete, primary_label
from ..core import winapi
from ..core.i18n import tr
from ..vault import search
from . import theme
from .actions_menu import ActionsMenu
from .backdrop import Backdrop
from .confirm import ConfirmPage
from .editor import EntryEditor
from .footer import Footer
from .live_glass import LiveGlass
from .results import ResultsView
from .settings import SettingsPage
from .unlock import UnlockPage
from .update_card import UpdateCard
from .widgets import Button

# Виртуальные коды клавиш Windows — одинаковые при любой раскладке.
VK_B, VK_C, VK_E, VK_K, VK_L, VK_N, VK_O, VK_T = (
    0x42, 0x43, 0x45, 0x4B, 0x4C, 0x4E, 0x4F, 0x54)
VK_COMMA = 0xBC

# Верх строки — на этой доле высоты экрана.
PANEL_TOP = 0.3

# Стекло, включённое в настройках, считается после анимации переключателя (180 мс).
GLASS_AFTER_TOGGLE_MS = 200

PASSWORD_MODES = ("setup", "locked", "change", "verify")
# Режимы с заголовком и стрелкой «назад» вместо поля поиска.
TITLED_MODES = ("edit", "settings")


class SearchField(QLineEdit):
    """Поле ввода без рамки и фона — фон рисует сама строка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrame(False)
        self.setFont(theme.font(20))
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: rgba(255,255,255,240);"
            " selection-background-color: rgba(10,132,255,150); }")
        self.setPlaceholderText(tr("search.placeholder"))
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, theme.TEXT_FAINT)
        self.setPalette(palette)


class Panel(QWidget):
    def __init__(self, app):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Aegis")
        self.mode = "locked"
        self.modal = False            # открыт системный диалог — не закрываться
        self.context = None           # окно, из которого позвали строку
        self._hidden_at = 0.0
        self._last_text = None
        self._delete_entry = None     # о ней сейчас спрашивает меню
        self._on_answer = None        # что делать с ответом на вопрос (confirm)
        self._back_mode = "search"    # куда вернуться из вопроса и пароля

        self.backdrop = Backdrop()
        self.backdrop.glass_enabled = app.config.get("glass")
        self.live = LiveGlass(self, self.backdrop)
        self.live.enabled = bool(app.config.get("live_glass"))
        self.live.set_rate(app.config.get("live_fps"))
        if self.live.enabled:
            self.live.gpu()          # до создания окна — потом только с пересозданием

        self.input = SearchField(self)
        self.input.textChanged.connect(lambda _t: self._refresh())
        self.input.installEventFilter(self)

        self.results = ResultsView(self)
        self.results.activated_item.connect(lambda entry: self.perform(entry, None))
        self.results.current_changed.connect(self._on_current)

        self.unlock = UnlockPage(self)
        self.unlock.submitted.connect(self._on_password)
        self.unlock.cancelled.connect(self._password_cancelled)
        self.editor = EntryEditor(app, self)
        self.editor.saved.connect(self._on_saved)
        self.editor.cancelled.connect(lambda: self.set_mode("search"))
        self.editor.delete_requested.connect(self._ask_delete_from_editor)
        self.confirm = ConfirmPage(self)
        self.confirm.answered.connect(self._on_answered)
        self.settings = SettingsPage(app, self)

        self.footer = Footer(self)
        self.footer.primary_clicked.connect(lambda: self.perform(self.current(), None))
        self.footer.actions_clicked.connect(self.toggle_actions)
        self.footer.settings_clicked.connect(lambda: self.set_mode("settings"))
        self.footer.add_clicked.connect(lambda: self.edit(None))
        self.footer.lock_clicked.connect(self.app.lock)
        self.footer.back_clicked.connect(self.back)

        self.menu = ActionsMenu(self)
        self.menu.triggered.connect(self._on_menu_action)

        # Скачанное в фоне обновление ждёт этой кнопки справа от поля ввода —
        # при каждом открытии строки, пока её не нажмут.
        self.update_ready = ""
        self.update_button = Button(tr("update.restart_button"), self, accent=True)
        self.update_button.clicked.connect(self.app.restart_and_update)
        self.update_button.hide()
        self.update_card = UpdateCard(self)

        self.resize(theme.PANEL_W + theme.SHADOW * 2, theme.PANEL_H + theme.SHADOW * 2)
        self._layout()
        self._show_pages()

    # --- геометрия --------------------------------------------------------- #

    def panel_rect(self):
        s = theme.SHADOW
        return QRect(s, s, theme.PANEL_W, theme.PANEL_H)

    def _layout(self):
        panel = self.panel_rect()
        x, y, w = panel.x(), panel.y(), panel.width()
        right = 20
        if self.update_button.isVisibleTo(self):
            size = self.update_button.sizeHint()
            self.update_button.setGeometry(x + w - 16 - size.width(),
                                           y + (theme.SEARCH_H - size.height()) // 2,
                                           size.width(), size.height())
            right = 16 + size.width() + 12
        self.input.setGeometry(x + 52, y + 8, w - 52 - right, theme.SEARCH_H - 16)
        body = QRect(x + theme.LIST_PAD, y + theme.SEARCH_H + 1,
                     w - theme.LIST_PAD * 2,
                     theme.PANEL_H - theme.SEARCH_H - theme.FOOTER_H - 2)
        self.results.setGeometry(body)
        page = QRect(x + 1, body.y(), w - 2, body.height())
        self.settings.setGeometry(page)
        self.editor.setGeometry(page)
        # Пароль и вопрос — на всю строку над нижней полосой, без поля поиска.
        full = QRect(x + 1, y + 1, w - 2, theme.PANEL_H - theme.FOOTER_H - 2)
        self.unlock.setGeometry(full)
        self.confirm.setGeometry(full)
        self.footer.setGeometry(x + 1, panel.bottom() + 1 - theme.FOOTER_H, w - 2,
                                theme.FOOTER_H)

    # --- показ и скрытие --------------------------------------------------- #

    def warm_up(self):
        """
        Один невидимый прогон отрисовки при старте программы.

        Самый первый показ иначе тратит почти секунду: шейдеры, буферы стекла,
        тень, шрифты и кэш глифов создаются по первому требованию. Пусть это
        случится, пока строку никто не ждёт.
        """
        screen = QGuiApplication.primaryScreen()
        self.backdrop.warm_up(self.size(), self.panel_rect(), screen.devicePixelRatio())
        if self.live.has_gpu():
            # Окно на GPU в первый раз создаётся ~170 мс (Direct3D) — пусть сейчас.
            self.winId()
        self.grab()

    def summon(self, mode=None, context=None):
        """
        Показать строку на экране под курсором. context — окно, откуда позвали
        (None — из трея: набирать некуда).
        """
        if self.isVisible():
            if mode and not self.locked():
                self.set_mode(mode)
            self._activate()
            return
        self.context = context
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(self._place(screen))
        # Стекло снимаем, пока окна ещё нет на экране — поэтому в снимок оно не
        # попадает само.
        self.backdrop.prepare(screen, self.geometry(), self.panel_rect())
        self.input.clear()
        self.set_mode(mode or self.app.default_mode())
        self.results.reset_mouse()
        self.show()
        self._activate()

    def _place(self, screen):
        full, area = screen.geometry(), screen.availableGeometry()
        w, h = self.width(), self.height()
        x = area.x() + (area.width() - w) // 2
        top = full.y() + int(full.height() * PANEL_TOP)
        top = min(top, area.bottom() - theme.PANEL_H - 16)
        top = max(top, area.y() + 16)
        return QRect(x, top - theme.SHADOW, w, h)

    def _activate(self):
        self.raise_()
        self.activateWindow()
        winapi.force_foreground(int(self.winId()))
        self._focus_mode()

    def _focus_mode(self):
        if self.locked():
            self.update_card.setFocus()
        elif self.mode == "search":
            self.input.setFocus()
        elif self.mode in PASSWORD_MODES:
            self.unlock.focus()
        elif self.mode == "edit":
            self.editor.focus()
        elif self.mode == "confirm":
            self.confirm.setFocus()
        else:
            self.setFocus()

    def dismiss(self):
        if not self.isVisible() or self.locked():
            return
        self.menu.close_menu()
        self.settings.hotkey.stop()
        if self.mode == "edit":
            self.editor.close_editor()
        if self.mode == "confirm":
            self._answer(False)
        self.input.clear()
        self.hide()
        self._hidden_at = time.monotonic()

    def showEvent(self, event):
        super().showEvent(event)
        self.live.start()

    def hideEvent(self, event):
        self.live.stop()
        super().hideEvent(event)

    def hidden_recently(self, seconds=0.3):
        """Строку только что закрыла потеря фокуса — клик в трей не должен
        тут же открыть её снова."""
        return time.monotonic() - self._hidden_at < seconds

    def event(self, event):
        if event.type() == QEvent.Type.WindowDeactivate and not self.modal:
            # Даём Qt доиграть смену фокуса: при открытии собственного
            # диалога деактивация приходит раньше, чем выставится modal.
            QTimer.singleShot(0, self._dismiss_if_inactive)
        return super().event(event)

    def _dismiss_if_inactive(self):
        if not self.modal and not self.isActiveWindow():
            self.dismiss()

    def can_type(self):
        return self.context is not None and winapi.is_window(self.context.hwnd)

    def set_context_url(self, hwnd, url):
        """Адрес страницы пришёл позже показа — подходящие сайту записи наверх."""
        if self.context is not None and self.context.hwnd == hwnd and url:
            self.context.url = url
            if self.isVisible() and self.mode == "search":
                self._refresh(force=True)

    # --- обновление -------------------------------------------------------- #

    def locked(self):
        """Идёт установка обновления: строку не закрыть и не потрогать."""
        return self.update_card.blocking()

    def show_update_card(self, version, fraction=0.0, restarting=False):
        if not self.isVisible():
            self.summon()
        self.menu.close_menu()
        self.settings.hotkey.stop()
        self.update_card.start(version, fraction, restarting)
        self._sync_update_button()
        self._activate()

    def hide_update_card(self):
        if not self.locked():
            return
        self.update_card.finish()
        self._sync_update_button()
        if self.isVisible():
            self._activate()

    def set_update_ready(self, version):
        self.update_ready = version
        self._sync_update_button()

    def _sync_update_button(self):
        show = bool(self.update_ready) and self.mode == "search" and not self.locked()
        if show != self.update_button.isVisibleTo(self):
            self.update_button.setVisible(show)
            self._layout()

    # --- режимы ------------------------------------------------------------ #

    def set_mode(self, mode):
        if self.mode == "edit" and mode != "edit":
            self.editor.close_editor()
        if mode in ("search", "edit", "change", "verify") and not self.app.vault.is_unlocked():
            mode = self.app.default_mode()
        if mode in PASSWORD_MODES and self.mode not in PASSWORD_MODES + ("confirm",):
            self._back_mode = self.mode if self.mode in ("search", "settings") else "search"
        self.mode = mode
        self.menu.close_menu()
        self._show_pages()
        if mode in PASSWORD_MODES:
            self.unlock.start(mode)
        elif mode == "search":
            self._refresh(force=True)
        elif mode == "settings":
            self.settings.refresh()
        self._sync_update_button()
        self.footer.set_mode(mode)
        if self.isVisible():
            self._focus_mode()
        self.update()

    def _show_pages(self):
        mode = self.mode
        self.input.setVisible(mode == "search")
        self.results.setVisible(mode == "search")
        self.unlock.setVisible(mode in PASSWORD_MODES)
        self.editor.setVisible(mode == "edit")
        self.settings.setVisible(mode == "settings")
        self.confirm.setVisible(mode == "confirm")

    def back(self):
        if self.mode == "edit":
            self.set_mode("search")
        elif self.mode in ("change", "verify"):
            self.set_mode("settings")
        elif self.mode == "settings":
            self.set_mode(self.app.default_mode())
        else:
            self.dismiss()

    def edit(self, entry, prefill=None):
        if not self.app.vault.is_unlocked():
            return
        self.editor.open(entry, prefill)
        self.set_mode("edit")

    def ask(self, title, text, yes, no, on_answer):
        """Вопрос в строке; on_answer(bool). Прежний вопрос считается отклонённым."""
        self._answer(False)
        if self.mode not in ("confirm",) + PASSWORD_MODES:
            self._back_mode = self.mode if self.mode in ("search", "settings") else "search"
        self._on_answer = on_answer
        self.confirm.ask(title, text, yes, no)
        if self.isVisible():
            self.set_mode("confirm")
        else:
            self.summon("confirm")

    def _answer(self, value):
        callback, self._on_answer = self._on_answer, None
        if callback is not None:
            callback(value)

    def _on_answered(self, value):
        self._answer(value)
        if self.mode == "confirm":
            self.set_mode(self._back_mode)

    def retranslate(self):
        self.input.setPlaceholderText(tr("search.placeholder"))
        self.update_button.setText(tr("update.restart_button"))
        old = self.settings
        self.settings = SettingsPage(self.app, self)
        self._layout()
        self.settings.setVisible(old.isVisible())
        old.hide()
        old.deleteLater()
        if self.settings.isVisible():
            self.settings.refresh()
        if self.mode in PASSWORD_MODES:
            self.unlock.start(self.mode)
        self._refresh(force=True)
        self.footer.update()
        self.update()

    # --- стекло ------------------------------------------------------------ #

    def set_glass(self, on):
        self.backdrop.glass_enabled = on
        if not self.isVisible():
            return
        if on:
            # Включили на открытой строке: стекло считается из снимка, который
            # сделан перед показом, — прятать строку ради нового не нужно.
            # Считаем после того, как доедет ручка переключателя: первый расчёт
            # поднимает OpenGL и собирает шейдеры (до полсекунды).
            QTimer.singleShot(GLASS_AFTER_TOGGLE_MS, self._glass_on)
        else:
            self.live.stop()
            self.backdrop.drop()
            self.update()

    def _glass_on(self):
        if self.backdrop.glass_enabled and self.isVisible():
            self.backdrop.rebuild()
            self.live.start()
            self.update()

    def set_live_glass(self, on):
        self.live.enabled = on
        if not on:
            self.live.release()
            return
        if self.live.gpu() and self.isVisible():
            # Тип окна выбирается при создании хендла: включили на открытой
            # строке — пересоздаём окно. Оно мигнёт один раз; фокус уходит,
            # поэтому на это время строка не закрывается сама.
            QTimer.singleShot(GLASS_AFTER_TOGGLE_MS, self._recreate)
        elif self.isVisible():
            self.live.start()

    def _recreate(self):
        if not self.isVisible() or self.locked():
            return
        self.modal = True
        self.hide()
        self.destroy()
        self.live.window_recreated()
        self.show()
        self._activate()
        # Деактивация от hide() приходит через очередь событий — ждём её.
        QTimer.singleShot(GLASS_AFTER_TOGGLE_MS, self._recreated)

    def _recreated(self):
        self.modal = False
        # Новый хендл окна — уведомления о блокировке Windows подписываем заново.
        self.app.session.watch(self.winId())

    # --- пароль ------------------------------------------------------------ #

    def _on_password(self, data):
        self.unlock.set_busy(True)
        self.app.password_submitted(self.mode, data)

    def password_failed(self, text):
        self.unlock.fail(text)

    def _password_cancelled(self):
        if self.mode in ("change", "verify"):
            self.set_mode("settings")
        else:
            self.dismiss()

    # --- поиск ------------------------------------------------------------- #

    def _refresh(self, force=False):
        if self.mode != "search":
            return
        text = self.input.text()
        if not force and text == self._last_text:
            return
        self._last_text = text
        self.menu.close_menu()
        vault = self.app.vault
        if not vault.entries:
            self.results.empty_text = tr("empty.vault")
        else:
            self.results.empty_text = tr("empty.nothing")
        sections = search.search(vault.entries, text, self.context)
        self.results.set_sections([(self._section_title(key), items) for key, items in sections])
        self._on_current(self.results.current_item())

    def _section_title(self, key):
        if key == "context" and self.context is not None:
            site = self.context.host
            return tr("section.context", where=site or self.context.title[:40])
        return tr("section." + key)

    def refresh_results(self):
        """Записи поменялись — пересобрать выдачу, не сбивая выделение."""
        if not self.isVisible() or self.mode != "search":
            return
        current = self.current()
        row = self.results.currentIndex().row()
        self._refresh(force=True)
        if current is not None and not self.results.select_key(current.id):
            self.results.select_near(row)

    def current(self):
        return self.results.current_item()

    def _on_current(self, entry):
        self.footer.set_primary(primary_label(entry, self.can_type()), entry is not None)

    # --- действия ---------------------------------------------------------- #

    def perform(self, entry, action_id):
        if entry is None:
            return
        self.menu.close_menu()
        if action_id is None:
            action_id = actions_for(entry, self.can_type())[0].id
        if action_id == "delete":
            self._delete_entry = entry
            self._open_menu(confirm_delete(entry))
            return
        self.app.perform(entry, action_id, self.context)

    def toggle_actions(self):
        if self.menu.is_open():
            self.menu.close_menu()
            return
        entry = self.current()
        if entry is not None:
            self._open_menu(actions_for(entry, self.can_type()))

    def _open_menu(self, actions):
        footer = self.footer.geometry()
        self.menu.open(actions, footer.right() - 4, footer.top() + 2)

    def _on_menu_action(self, action_id):
        entry = self.current()
        if action_id == "delete" and entry is not None:
            # Сначала спросить: меню сменяется вопросом на том же месте.
            self._delete_entry = entry
            self._open_menu(confirm_delete(entry))
            return
        self.menu.close_menu()
        if action_id == "delete_confirm":
            entry, self._delete_entry = self._delete_entry, None
            if entry is not None:
                self.app.delete_entry(entry)
            return
        if entry is not None and action_id != "cancel":
            self.app.perform(entry, action_id, self.context)

    def _on_saved(self, entry):
        self.app.save_entry(entry)
        self.set_mode("search")
        self.results.select_key(entry.id)

    def _ask_delete_from_editor(self, entry):
        if entry is None:
            return
        title = entry.title

        def answer(yes):
            if yes:
                self.app.delete_entry(entry)

        self.ask(tr("confirm.delete_title", name=title), tr("confirm.delete_text"),
                 tr("confirm.delete_yes"), tr("action.cancel"), answer)

    # --- клавиатура -------------------------------------------------------- #

    def eventFilter(self, obj, event):
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            return self._key(event)
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        # Сюда попадают нажатия вне поля поиска (настройки и др.).
        if event.key() == Qt.Key.Key_Escape:
            if not self.settings.hotkey.is_recording():
                self.back()
            return
        super().keyPressEvent(event)

    def _key(self, event):
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        # Буквенные сочетания сверяем по физической клавише: на русской
        # раскладке Ctrl+K приходит от Qt как Ctrl+Л.
        vk = event.nativeVirtualKey()

        def combo(letter_vk, qt_key):
            return ctrl and (vk == letter_vk or key == qt_key)

        if self.menu.is_open():
            if key == Qt.Key.Key_Escape or combo(VK_K, Qt.Key.Key_K):
                self.menu.close_menu()
            elif key == Qt.Key.Key_Up:
                self.menu.move_selection(-1)
            elif key == Qt.Key.Key_Down:
                self.menu.move_selection(1)
            elif enter:
                self.menu.activate()
            return True        # пока меню открыто, в поле ввода ничего не идёт

        if key == Qt.Key.Key_Escape:
            if self.input.text():
                self.input.clear()
            else:
                self.dismiss()
            return True
        if key == Qt.Key.Key_Down:
            self.results.move(1)
            return True
        if key == Qt.Key.Key_Up:
            self.results.move(-1)
            return True
        if key == Qt.Key.Key_PageDown:
            self.results.page(1)
            return True
        if key == Qt.Key.Key_PageUp:
            self.results.page(-1)
            return True
        if combo(VK_K, Qt.Key.Key_K):
            self.toggle_actions()
            return True
        if combo(VK_COMMA, Qt.Key.Key_Comma):
            self.set_mode("settings")
            return True
        if combo(VK_N, Qt.Key.Key_N):
            self.edit(None)
            return True
        if combo(VK_L, Qt.Key.Key_L):
            self.app.lock()
            return True
        entry = self.current()
        if enter:
            if entry is not None:
                if ctrl and shift and self.can_type():
                    self.perform(entry, "type_password")
                else:
                    self.perform(entry, None)
            return True
        shortcuts = ((VK_B, Qt.Key.Key_B, "copy_username"), (VK_T, Qt.Key.Key_T, "copy_totp"),
                     (VK_O, Qt.Key.Key_O, "open_url"), (VK_E, Qt.Key.Key_E, "edit"))
        for letter, qt_key, action in shortcuts:
            if combo(letter, qt_key):
                if entry is not None:
                    self.perform(entry, action)
                return True
        # Ctrl+C копирует пароль, если в поле поиска ничего не выделено, —
        # иначе это обычное копирование выделенного текста.
        if combo(VK_C, Qt.Key.Key_C) and not self.input.hasSelectedText():
            if entry is not None:
                self.perform(entry, "copy_password")
            return True
        return False

    # --- отрисовка --------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QRectF(self.panel_rect())
        self.backdrop.paint(p, self.panel_rect())

        p.setPen(QPen(theme.HAIRLINE, 1))
        if self.mode == "search" or self.mode in TITLED_MODES:
            y = panel.top() + theme.SEARCH_H + 0.5
            p.drawLine(QPointF(panel.left() + 1, y), QPointF(panel.right() - 1, y))
        y = panel.bottom() - theme.FOOTER_H + 0.5
        p.drawLine(QPointF(panel.left() + 1, y), QPointF(panel.right() - 1, y))

        center_y = panel.top() + theme.SEARCH_H / 2
        if self.mode == "search":
            theme.magnifier(p, QPointF(panel.left() + 30, center_y), 18, theme.TEXT_DIM)
        elif self.mode in TITLED_MODES:
            # Заголовок со стрелкой «назад».
            p.setPen(QPen(theme.TEXT_DIM, 1.8, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            cx = panel.left() + 28
            p.drawPolyline([QPointF(cx + 4, center_y - 7), QPointF(cx - 3, center_y),
                            QPointF(cx + 4, center_y + 7)])
            if self.mode == "edit":
                title = tr("editor.new" if self.editor.is_new else "editor.edit")
            else:
                title = tr("settings.title")
            p.setFont(theme.font(18, QFont.Weight.DemiBold))
            p.setPen(theme.TEXT)
            p.drawText(QRectF(panel.left() + 52, panel.top(), 500, theme.SEARCH_H),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)

    def mousePressEvent(self, event):
        if self.mode in TITLED_MODES:
            panel = self.panel_rect()
            if QRect(panel.left(), panel.top(), 52, theme.SEARCH_H).contains(
                    event.position().toPoint()):
                self.back()
                return
        if self.menu.is_open() and not self.menu.geometry().contains(
                event.position().toPoint()):
            self.menu.close_menu()
        super().mousePressEvent(event)
