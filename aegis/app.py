"""
Сборка программы: база, строка, трей, хоткей, автонабор, расширение,
обновления (каркас — из Spotty).
"""

import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QFileDialog, QSystemTrayIcon

from . import bridge as bridge_mod
from .bridge import Bridge
from .core import autostart, context, hotkey, i18n, logbook, systheme, winapi
from .core.autotype import AutoTyper
from .core.clipboard import SecureClipboard
from .core.config import Config
from .core.constants import (APP_ICO, APP_ID, APP_NAME, BACKUP_DIR, EXTENSION_DIR, IPC_NAME,
                             IS_FIRST_RUN, VAULT_PATH)
from .core.i18n import tr
from .core.session import SessionWatcher
from .ui import appicon
from .ui.hud import Hud
from .ui.panel import Panel
from .ui.toast import Toast
from .ui.tray_menu import MenuItem, TrayMenu
from .updates import UpdateService
from .vault import browsers, crypto, csvio, watch
from .vault.backup import Backups
from .vault.search import Context, site_of
from .vault.store import Vault

UPDATE_FIRST_CHECK_MS = 20_000
UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1000
# «Перезапускаю…» на карточке успевает прочитаться до того, как строка исчезнет.
RESTART_DELAY_MS = 450
TOAST_LONG_MS = 8000
SAVE_TOAST_MS = 20_000
# Сколько ждать CSV от браузера после открытия страницы выгрузки.
EXPORT_WAIT_S = 10 * 60


class Aegis(QObject):
    _done = Signal(object, object)       # (callback, результат) из фонового потока

    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        self.config = Config()
        i18n.set_language(self.config.get("language"))

        self.backups = Backups(BACKUP_DIR, self.config.get("backup_extra_dir"))
        self.vault = Vault(VAULT_PATH, on_saved=self._after_save)
        self.clipboard = SecureClipboard(self)
        self.typer = AutoTyper(self)
        self.typer.finished.connect(self._typed)
        self.address = context.AddressReader(self)
        self.address.ready.connect(lambda hwnd, url: self.panel.set_context_url(hwnd, url))
        self.bridge = Bridge(self)
        self.updates = UpdateService(self)
        self.hud = Hud()
        self.toast = Toast()
        self.panel = Panel(self)
        self._after_unlock = None       # что сделать, когда базу откроют
        self._done.connect(lambda callback, result: callback(result),
                           Qt.ConnectionType.QueuedConnection)

        self.updates.state.connect(self._on_update_state)
        self.updates.progress.connect(self._on_update_progress)
        self._install_now = False     # человек ждёт установки — карточка в строке
        self._tray_check = False      # проверку начали из трея — отвечаем плашкой
        self._notified_version = ""   # о ней уже показали плашку в этом сеансе
        if self.updates.ready_version():
            self._on_update_state("ready", self.updates.ready_version())

        self.hotkeys = hotkey.HotkeyManager(self)
        self.hotkeys.install(qapp)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self._recording = False       # в настройках записывают новое сочетание

        self.session = SessionWatcher(self)
        self.session.idle_minutes = int(self.config.get("lock_idle_minutes") or 0)
        self.session.lock_requested.connect(self._on_lock_requested)

        self._build_tray()
        self._server = QLocalServer(self)
        # Канал — только своему пользователю Windows: через него ходит расширение.
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(IPC_NAME)
        self._server.newConnection.connect(self._on_ipc)
        self._server.listen(IPC_NAME)

        self._export = None             # (браузер, Waiter, начало) — ждём выгрузку
        self._export_timer = QTimer(self, interval=1000)
        self._export_timer.timeout.connect(self._poll_export)

        self._update_timer = QTimer(self, interval=UPDATE_INTERVAL_MS)
        self._update_timer.timeout.connect(self._auto_check)

    # --- запуск ------------------------------------------------------------ #

    def start(self):
        self._sync_autostart()
        self.tray.show()
        combo = self.config.get("hotkey")
        if not self.hotkeys.register("toggle", combo):
            logbook.log("хоткей занят:", combo)
            self.toast.show_message(tr("toast.hotkey_busy", hotkey=hotkey.display(combo)),
                                    tr("toast.hotkey_busy_sub"), TOAST_LONG_MS,
                                    on_click=lambda: self.panel.summon("settings"))
        elif IS_FIRST_RUN:
            self.toast.show_message(tr("toast.welcome"),
                                    tr("toast.welcome_sub", hotkey=hotkey.display(combo)),
                                    TOAST_LONG_MS, on_click=self.panel.summon)
        bridge_mod.sync_extension()
        if self.config.get("bridge_enabled"):
            bridge_mod.register()
        self.session.install(self.qapp, self.panel.winId())
        QTimer.singleShot(300, self.panel.warm_up)
        QTimer.singleShot(UPDATE_FIRST_CHECK_MS, self._auto_check)
        self._update_timer.start()

    def _build_tray(self):
        icon = QIcon(APP_ICO) if os.path.isfile(APP_ICO) else QIcon(appicon.pixmap(64))
        self.qapp.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip(APP_NAME)
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _scheme: self._sync_tray())
        self.tray.activated.connect(self._on_tray)
        # Меню рисуем сами (ui/tray_menu.py) и показываем по правому клику.
        self.menu = TrayMenu()
        self.menu.triggered.connect(self._on_tray_menu)

    def _tray_icon(self):
        """Заперта — сплошной щит со скважиной, открыта — контур щита."""
        ink = QColor(systheme.tray_ink())
        icon = QIcon()
        locked = not self.vault.is_unlocked()
        for size in appicon.TRAY_SIZES:
            icon.addPixmap(appicon.tray_pixmap(size, ink, locked))
        return icon

    def _sync_tray(self):
        self.tray.setIcon(self._tray_icon())

    def _tray_items(self):
        unlocked = self.vault.is_unlocked()
        items = [MenuItem("open", tr("tray.open"), hotkey.keycaps(self.config.get("hotkey")))]
        if unlocked:
            items += [MenuItem("new", tr("tray.new")), MenuItem("lock", tr("tray.lock"))]
        elif self.vault.exists():
            items.append(MenuItem("unlock", tr("tray.unlock")))
        items += [MenuItem("settings", tr("tray.settings")), None]
        if autostart.supported():
            items.append(MenuItem("autostart", tr("settings.autostart"),
                                  checked=self.autostart_enabled()))
        if self.updates.ready_version():
            items.append(MenuItem("restart", tr("update.restart_button")))
        else:
            items.append(MenuItem("update", tr("tray.update")))
        items += [None, MenuItem("quit", tr("tray.quit"))]
        return items

    def _on_tray_menu(self, item_id):
        if item_id in ("open", "unlock"):
            self.panel.summon()
        elif item_id == "new":
            self.panel.summon()
            self.panel.edit(None)
        elif item_id == "lock":
            self.lock()
        elif item_id == "settings":
            self.panel.summon("settings")
        elif item_id == "autostart":
            self.set_autostart(not self.autostart_enabled())
        elif item_id == "update":
            self._check_from_tray()
        elif item_id == "restart":
            self.restart_and_update()
        elif item_id == "quit":
            self.quit()

    def _on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Клик в трей сначала снимает фокус со строки, и она закрывается;
            # не открываем её тут же обратно — клик означал «закрой».
            if not self.panel.hidden_recently():
                self.toggle(None)
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self.panel.dismiss()
            self.menu.popup(self._tray_items(), QCursor.pos())

    def _on_ipc(self):
        """Второй запуск пишет «show», посредник расширения — «bridge» и дальше JSON."""
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        buf = bytearray()

        def on_ready():
            buf.extend(bytes(socket.readAll()))
            if buf.startswith(b"bridge\n"):
                socket.readyRead.disconnect(on_ready)
                self.bridge.adopt(socket, bytes(buf[len(b"bridge\n"):]))
            elif buf.startswith(b"show"):
                socket.readyRead.disconnect(on_ready)
                socket.disconnected.connect(socket.deleteLater)
                socket.close()
                self.panel.summon()
            elif len(buf) > 16:
                socket.abort()

        socket.readyRead.connect(on_ready)

    def quit(self):
        self.clipboard.clear()
        self.vault.lock()
        self.hotkeys.unregister_all()
        self.toast.hide()
        self.tray.hide()
        self.qapp.quit()

    # --- строка ------------------------------------------------------------ #

    def default_mode(self):
        if not self.vault.exists():
            return "setup"
        return "search" if self.vault.is_unlocked() else "locked"

    def _on_hotkey(self, _name):
        ours = int(self.panel.winId())
        if winapi.root_window(winapi.foreground_window()) == ours:
            self.toggle(None)
            return
        # Окно снимаем сейчас, пока передний план ещё не наш.
        self.toggle(context.capture())

    def toggle(self, ctx):
        if self.panel.locked():
            self.panel.summon()         # идёт установка — только вернуть на передний план
        elif self.panel.isVisible() and self.panel.isActiveWindow():
            self.panel.dismiss()
        else:
            if ctx is not None and context.is_browser(ctx):
                self._fill_url(ctx)
            self.panel.summon(context=ctx)

    def _fill_url(self, ctx):
        """Адрес страницы: от расширения, если оно его сообщало, иначе из окна."""
        reported = self.bridge.tab_url.get(ctx.process)
        if reported:
            ctx.url = reported
        elif self.config.get("read_browser_url"):
            self.address.request(ctx.hwnd)

    def summon_unlock(self):
        self.panel.summon()

    def summon_for_url(self, url):
        self.panel.summon(context=Context(url=url))

    # --- пароль ------------------------------------------------------------ #

    def _background(self, work, done):
        """work() в потоке (Argon2 — полсекунды), done(результат) — на главном."""
        def run():
            try:
                result = work()
            except Exception as error:      # исключение — тоже результат
                result = error
            self._done.emit(done, result)
        threading.Thread(target=run, name="aegis-kdf", daemon=True).start()

    def password_submitted(self, mode, data):
        password = data["password"]
        if mode == "setup":
            self._background(lambda: self.vault.create(password), self._created)
        elif mode == "locked":
            self._background(lambda: self.vault.unlock(password), self._unlocked)
        elif mode == "change":
            new = data["new"]

            def change():
                if not self.vault.check_password(password):
                    raise crypto.InvalidPassword()
                self.vault.change_password(new)
            self._background(change, self._changed)
        elif mode == "verify":
            self._background(lambda: self.vault.check_password(password), self._verified)

    def _created(self, result):
        if isinstance(result, Exception):
            logbook.log("не создал базу:", repr(result))
            self.panel.password_failed(tr("hud.save_failed"))
            return
        self._opened()

    def _unlocked(self, result):
        if isinstance(result, crypto.InvalidPassword):
            self.panel.password_failed(tr("unlock.wrong"))
        elif isinstance(result, Exception):
            logbook.log("не открыл базу:", repr(result))
            self.panel.password_failed(tr("unlock.broken"))
        else:
            self._opened()

    def _opened(self):
        self._sync_tray()
        action, self._after_unlock = self._after_unlock, None
        self.panel.set_mode("search")
        if action is not None:
            action()

    def _changed(self, result):
        if isinstance(result, crypto.InvalidPassword):
            self.panel.password_failed(tr("unlock.wrong"))
        elif isinstance(result, Exception):
            logbook.log("не сменил пароль:", repr(result))
            self.panel.password_failed(tr("hud.save_failed"))
        else:
            self.panel.set_mode("settings")
            self.hud.show_text(tr("hud.password_changed"))

    def _verified(self, result):
        if result is True:
            self.panel.set_mode("settings")
            self._export_csv()
        else:
            self.panel.password_failed(tr("unlock.wrong"))

    def lock(self):
        self.typer.cancel()
        self.clipboard.clear()
        # Заперли — выгрузку не ждём: импортировать её некуда, а стирать
        # непрочитанный файл нельзя. Он останется там, куда его сохранили.
        self._stop_export()
        self._after_unlock = None
        was_open = self.vault.is_unlocked()
        self.vault.lock()
        self._sync_tray()
        if self.panel.isVisible():
            self.panel.set_mode(self.default_mode())
        if was_open:
            self.hud.show_text(tr("hud.locked"))

    def _on_lock_requested(self, reason):
        if reason in ("session", "suspend") and not self.config.get("lock_on_session"):
            return
        if self.vault.is_unlocked():
            logbook.log("запираю:", reason)
            self.panel.dismiss()
            self.lock()

    def set_lock_idle(self, minutes):
        self.config.set("lock_idle_minutes", minutes)
        self.session.idle_minutes = minutes

    # --- действия с записями ----------------------------------------------- #

    def perform(self, entry, action_id, ctx):
        handler = getattr(self, "_do_" + action_id, None)
        if handler is None:
            logbook.log("неизвестное действие:", action_id)
            return
        try:
            handler(entry, ctx)
        except Exception:
            logbook.exc("действие " + action_id)

    def _touch(self, entry):
        try:
            self.vault.touch(entry)
        except Exception:
            logbook.exc("отметка использования")

    def _do_type(self, entry, ctx, sequence=None):
        if ctx is None or not winapi.is_window(ctx.hwnd):
            self._do_copy_password(entry, ctx)
            return
        self.panel.dismiss()
        self.typer.run(entry, ctx.hwnd, sequence)
        self._touch(entry)

    def _do_type_password(self, entry, ctx):
        self._do_type(entry, ctx, "{PASSWORD}")

    def _typed(self, ok):
        if not ok:
            self.hud.show_text(tr("hud.type_failed"))

    def _copy_secret(self, text, message):
        seconds = int(self.config.get("clipboard_clear_s") or 0)
        self.clipboard.copy(text, seconds)
        self.panel.dismiss()
        self.hud.show_text(message)

    def _do_copy_password(self, entry, _ctx):
        seconds = int(self.config.get("clipboard_clear_s") or 0)
        self._copy_secret(entry.password, tr("hud.copied_password", seconds=seconds)
                          if seconds else tr("hud.copied_password_keep"))
        self._touch(entry)

    def _do_copy_username(self, entry, _ctx):
        self.clipboard.copy(entry.username, secret=False)
        self.panel.dismiss()
        self.hud.show_text(tr("hud.copied_username"))

    def _do_copy_totp(self, entry, _ctx):
        from .vault import totp
        try:
            code = totp.code(entry.totp)
        except ValueError:
            self.hud.show_text(tr("hud.no_totp"))
            return
        self._copy_secret(code, tr("hud.copied_totp"))

    def _do_open_url(self, entry, _ctx):
        url = entry.url if "://" in entry.url else "https://" + entry.url
        winapi.allow_foreground_for_launched()
        self.panel.dismiss()
        winapi.shell_open(url)

    def _do_edit(self, entry, _ctx):
        self.panel.edit(entry)

    def _do_favorite(self, entry, _ctx):
        entry.favorite = not entry.favorite
        self.save_entry(entry, quiet=True)
        self.panel.refresh_results()

    def save_entry(self, entry, quiet=False):
        try:
            self.vault.put(entry)
        except Exception:
            logbook.exc("запись в базу")
            self.hud.show_text(tr("hud.save_failed"))
            return
        if not quiet:
            self.hud.show_text(tr("hud.saved"))

    def delete_entry(self, entry):
        try:
            self.vault.delete(entry.id)
        except Exception:
            logbook.exc("удаление записи")
            self.hud.show_text(tr("hud.save_failed"))
            return
        if self.panel.mode != "search":
            self.panel.set_mode("search")
        self.panel.refresh_results()
        self.hud.show_text(tr("hud.deleted"))

    # --- копии ------------------------------------------------------------- #

    def _after_save(self, path):
        self.backups.after_save(path)
        if self.backups.last_error:
            logbook.log("копия не записалась:", self.backups.last_error)
            self.toast.show_message(tr("toast.backup_failed"),
                                    tr("toast.backup_failed_sub",
                                       folder=self.backups.last_error), TOAST_LONG_MS,
                                    tag="backup")

    def backup_now(self):
        if not self.vault.exists():
            return
        ok = self.backups.make_now(VAULT_PATH)
        self.hud.show_text(tr("hud.backup_done" if ok else "hud.backup_failed"))
        if self.panel.mode == "settings":
            self.panel.settings.refresh()

    def reveal(self, folder):
        os.makedirs(folder, exist_ok=True)
        self.panel.dismiss()
        winapi.shell_open(folder)

    def reveal_extension(self):
        self.reveal(EXTENSION_DIR)

    def _pick(self, dialog):
        """Системный диалог поверх строки: на это время она не закрывается сама."""
        self.panel.modal = True
        try:
            return dialog()
        finally:
            self.panel.modal = False
            self.panel.summon()

    def choose_backup_extra(self):
        folder = self._pick(lambda: QFileDialog.getExistingDirectory(
            self.panel, tr("dialog.backup_dir")))
        if folder:
            self.set_backup_extra(os.path.normpath(folder))

    def set_backup_extra(self, folder):
        self.config.set("backup_extra_dir", folder)
        self.backups.extra = folder
        if folder and self.vault.exists():
            self.backups.make_now(VAULT_PATH)
        self.panel.settings.refresh()

    def ask_restore(self, path):
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(os.path.getmtime(path)))

        def answer(yes):
            if not yes:
                return
            try:
                self.backups.restore(path, VAULT_PATH)
            except OSError:
                logbook.exc("восстановление копии")
                self.hud.show_text(tr("hud.save_failed"))
                return
            self.lock()
            self.panel.summon("locked")
            self.hud.show_text(tr("hud.restored"))

        self.panel.ask(tr("confirm.restore_title"), tr("confirm.restore_text", when=when),
                       tr("confirm.restore_yes"), tr("confirm.no"), answer)

    # --- импорт и экспорт -------------------------------------------------- #

    def import_csv(self):
        path, _ = self._pick(lambda: QFileDialog.getOpenFileName(
            self.panel, tr("dialog.import"), "", "CSV (*.csv);;* (*.*)"))
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                entries = csvio.parse(f.read())
        except (OSError, ValueError):
            logbook.exc("импорт")
            self.hud.show_text(tr("hud.import_failed"))
            return
        count = self._add_entries(entries)
        if count:
            self.panel.set_mode("search")
        self.hud.show_text(tr("hud.imported", count=count) if count else tr("hud.import_none"))

    def _add_entries(self, entries):
        """Новые записи без повторов (тот же сайт, логин и пароль). Сколько добавлено."""
        fresh = []
        for entry in entries:
            if not csvio.is_duplicate(entry, self.vault.entries + fresh):
                fresh.append(entry)
        if fresh:
            self.vault.put_many(fresh)
        return len(fresh)

    # --- импорт из браузеров ----------------------------------------------- #
    #
    # Где пароли защищены только учётной записью Windows (Vivaldi, Opera,
    # Chromium, Firefox без основного пароля) — читаем напрямую. Chrome, Edge,
    # Brave закрывают их App-Bound Encryption: открываем страницу выгрузки,
    # браузер спрашивает PIN Windows и сохраняет CSV, а мы ждём этот файл
    # (vault/watch.py), импортируем и стираем — только его.

    def import_browser(self, key):
        browser = next((b for b in browsers.installed() if b.key == key), None)
        if browser is None or not self.vault.is_unlocked():
            return
        if browsers.app_bound(browser):
            self.export_from_browser(browser)
            return
        self.hud.show_text(tr("hud.browser_reading", name=browser.name))
        self._background(lambda: browsers.read(browser),
                         lambda result: self._browser_read(browser, result))

    def _browser_read(self, browser, result):
        if isinstance(result, Exception) or result.error == "unreadable":
            logbook.log("импорт из браузера не прочитался:", browser.key, repr(result))
            self.hud.show_text(tr("hud.browser_failed", name=browser.name))
            return
        if result.error == "primary_password" and not result.entries:
            # Основной пароль Firefox знаем не мы — пусть выгрузит сам браузер.
            self.export_from_browser(browser, reason="primary_password")
            return
        if not self.vault.is_unlocked():
            return
        count = self._add_entries(result.entries)
        text = tr("hud.imported", count=count) if count else tr("hud.import_none")
        if result.skipped:
            text += " · " + tr("hud.browser_skipped", count=result.skipped)
        self.hud.show_text(text)
        self.panel.refresh_results()

    def export_from_browser(self, browser, reason="app_bound"):
        self._stop_export()
        self._export = (browser, watch.Waiter(winapi.export_folders()), time.time())
        self._export_timer.start()
        self.panel.dismiss()
        winapi.allow_foreground_for_launched()
        winapi.shell_open(browser.exe, browser.export_url)
        self.toast.show_message(tr("toast.export_title", name=browser.name),
                                tr("toast.export_sub." + reason), 0,
                                on_close=self._stop_export, tag="browser-export")

    def _stop_export(self):
        self._export_timer.stop()
        self._export = None

    def _poll_export(self):
        if self._export is None or not self.vault.is_unlocked():
            self._stop_export()
            return
        browser, waiter, started = self._export
        if time.time() - started > EXPORT_WAIT_S:
            self._stop_export()
            self.toast.show_message(tr("toast.export_timeout"), tr("toast.export_timeout_sub"),
                                    TOAST_LONG_MS, tag="browser-export")
            return
        for folder, path in waiter.poll():
            if self._take_export(browser, waiter, folder, path):
                return

    def _take_export(self, browser, waiter, folder, path):
        """True — файл наш: импортирован (и стёрт, если вышло)."""
        try:
            stamp = watch.fingerprint(path)
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                entries = csvio.parse(f.read())
        except (OSError, ValueError):
            # Возможно, браузер ещё дописывает: свежий файл посмотрим снова.
            try:
                if time.time() - os.path.getmtime(path) < 10:
                    waiter.seen.discard(os.path.normcase(path))
            except OSError:
                pass
            return False
        count = self._add_entries(entries)
        deleted = watch.safe_delete(path, folder, stamp)
        if not deleted:
            logbook.log("выгрузку не удалось стереть:", path)
        self._stop_export()
        self.toast.close_message("browser-export")
        title = tr("hud.imported", count=count) if count else tr("hud.import_none")
        sub = tr("toast.export_deleted") if deleted else tr("toast.export_kept", path=path)
        self.toast.show_message(title, sub, TOAST_LONG_MS if deleted else 0, tag="browser-export",
                                on_click=None if deleted else lambda: winapi.reveal(path))
        self.panel.refresh_results()
        return True

    def _export_csv(self):
        path, _ = self._pick(lambda: QFileDialog.getSaveFileName(
            self.panel, tr("dialog.export"), "aegis-export.csv", "CSV (*.csv)"))
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(csvio.dump(self.vault.entries))
        except OSError:
            logbook.exc("экспорт")
            self.hud.show_text(tr("hud.save_failed"))
            return
        self.hud.show_text(tr("hud.exported"))

    # --- расширение -------------------------------------------------------- #

    def set_bridge_enabled(self, on):
        self.config.set("bridge_enabled", on)
        if on:
            bridge_mod.register()
        else:
            bridge_mod.unregister()

    def unpair(self, pair_id):
        self.bridge.unpair(pair_id)
        self.panel.settings.refresh()

    def ask_pairing(self, browser, answer):
        self.panel.ask(tr("confirm.pair_title"), tr("confirm.pair_text", browser=browser),
                       tr("confirm.pair_yes"), tr("confirm.pair_no"), answer)

    def offer_save(self, url, username, password):
        """Расширение заметило вход с новым паролем — предложить сохранить."""
        if not password:
            return
        site = site_of(Context(url=url).host) or url
        prefill = {"title": csvio.title_from_url(url), "url": url, "username": username,
                   "password": password}

        def open_editor():
            existing = next((e for e in self.vault.entries
                             if e.username == username and site_of(Context(url=e.url).host)
                             == site), None)
            if existing is not None:
                existing.password = password
                self.panel.edit(existing)
            else:
                self.panel.edit(None, prefill)

        def clicked():
            self.panel.summon()
            if self.vault.is_unlocked():
                open_editor()
            else:
                self._after_unlock = open_editor

        def closed():
            prefill.clear()

        self.toast.show_message(tr("toast.save_title", site=site), tr("toast.save_sub"),
                                SAVE_TOAST_MS, on_click=clicked, on_close=closed, tag="save")

    # --- настройки --------------------------------------------------------- #

    def set_hotkey(self, combo):
        old = self.config.get("hotkey")
        if self.hotkeys.register("toggle", combo):
            self.config.set("hotkey", combo)
            return True
        self.hotkeys.register("toggle", old)
        return False

    def suspend_hotkey(self, suspended):
        self._recording = suspended
        if suspended:
            self.hotkeys.unregister("toggle")
        elif not self.hotkeys.register("toggle", self.config.get("hotkey")):
            logbook.log("хоткей занят:", self.config.get("hotkey"))

    def autostart_enabled(self):
        return bool(self.config.get("autostart"))

    def set_autostart(self, on):
        self.config.set("autostart", on)
        autostart.set_enabled(on)

    def _sync_autostart(self):
        """
        Как в Spotty: настройка — источник истины, и путь к exe переписываем на
        каждом старте. Из реестра берём, только если настройки ещё нет (галочка
        установщика) или автозапуск выключили в диспетчере задач.
        """
        if not autostart.supported():
            return
        wanted = self.config.get("autostart")
        if wanted is None or (wanted and autostart.disabled_in_task_manager()):
            wanted = autostart.is_enabled()
            self.config.set("autostart", wanted)
        autostart.set_enabled(wanted)

    def set_auto_update(self, on):
        self.config.set("auto_update", on)
        if on:
            self._auto_check()

    def set_update_mode(self, mode):
        self.config.set("update_mode", mode)
        if self._background_updates() and self.updates.latest_available():
            self.toast.close_message("update")
            self.updates.download()

    def set_glass(self, on):
        self.config.set("glass", on)
        self.panel.set_glass(on)

    def set_live_glass(self, on):
        self.config.set("live_glass", on)
        self.panel.set_live_glass(on)

    def set_live_fps(self, fps):
        self.config.set("live_fps", int(fps))
        self.panel.live.set_rate(int(fps))

    def set_language(self, code):
        self.config.set("language", code)
        i18n.set_language(code)
        self.panel.retranslate()

    # --- обновления (как в Spotty) ----------------------------------------- #
    #
    #   notify     — найдено: плашка в углу. Клик по ней или «Установить» в
    #                настройках — карточка в строке с полосой прогресса.
    #   background — найдено: качается само. В конце справа в поле поиска —
    #                «Перезапустить и обновить», ждёт, пока её не нажмут.

    def _background_updates(self):
        return self.config.get("update_mode") == "background"

    def _auto_check(self):
        if self.config.get("auto_update") and self.updates.supported():
            self.updates.check(silent=True, then_download=self._background_updates())

    def check_updates(self):
        self.updates.check(then_download=self._background_updates())

    def _check_from_tray(self):
        if not self.updates.supported():
            self.toast.show_message(tr("update.dev"))
            return
        ready = self.updates.ready_version()
        if ready:
            self._toast_ready(ready)
            return
        self._tray_check = True
        if self.updates.downloading():
            self.toast.show_message(tr("toast.downloading", version=self.updates.downloading()),
                                    tr("toast.downloading_sub"), tag="update")
            return
        self.toast.show_message(tr("toast.checking"), tag="update")
        self.updates.check(then_download=True)

    def install_update(self):
        if not self.updates.supported():
            self.toast.show_message(tr("update.dev"))
            return
        self.toast.close_message("update")
        if self.updates.ready_version():
            self.restart_and_update()
            return
        self._install_now = True
        version = self.updates.downloading() or self.updates.latest_available()
        self.panel.show_update_card(version, self.updates.fraction()
                                    if self.updates.downloading() else 0.0)
        self.updates.download()

    def restart_and_update(self):
        version = self.updates.ready_version()
        if not version:
            return
        self._install_now = True
        self.toast.close_message("update")
        self.panel.show_update_card(version, 1.0, restarting=True)
        QTimer.singleShot(RESTART_DELAY_MS, self._apply_update)

    def _apply_update(self):
        """Сначала помощник, потом выход. Не запустился — программа остаётся целой."""
        if self.updates.start_helper():
            self.clipboard.clear()
            self.vault.lock()
            self.hotkeys.unregister_all()
            self.toast.hide()
            self.tray.hide()
            self.updates.exit_now()
            return
        logbook.log("обновление: помощник не запустился")
        self._install_now = False
        self.panel.set_update_ready("")
        self.panel.hide_update_card()
        self.toast.show_message(tr("toast.install_failed"), tr("toast.install_failed_sub"),
                                TOAST_LONG_MS)

    def _toast_ready(self, version):
        self.toast.show_message(tr("toast.ready", version=version), tr("toast.ready_sub"),
                                0, on_click=self.restart_and_update, tag="update")

    def _on_update_progress(self, fraction):
        if self._install_now:
            self.panel.update_card.set_progress(fraction)

    def _on_update_state(self, state, version):
        tray = self._tray_check
        if state in ("current", "error", "ready", "failed"):
            self._tray_check = False

        if state == "available":
            if self._install_now:
                return
            if tray:
                self.toast.show_message(tr("toast.downloading", version=version),
                                        tr("toast.downloading_sub"), tag="update")
            elif (not self._background_updates() and version != self._notified_version
                  and version != self.config.get("update_dismissed_version")):
                self._notified_version = version
                self.toast.show_message(
                    tr("toast.available", version=version), tr("toast.available_sub"), 0,
                    on_click=self.install_update,
                    on_close=lambda: self.config.set("update_dismissed_version", version),
                    tag="update")
        elif state == "downloading":
            if self._install_now:
                self.panel.show_update_card(version, self.updates.fraction())
        elif state == "ready":
            if self._install_now:
                self.panel.update_card.set_restarting()
                QTimer.singleShot(RESTART_DELAY_MS, self._apply_update)
                return
            self.panel.set_update_ready(version)
            if tray:
                self._toast_ready(version)
        elif state == "failed":
            if self._install_now or tray:
                self._install_now = False
                self.panel.hide_update_card()
                self.toast.show_message(tr("toast.download_failed"),
                                        tr("toast.download_failed_sub"), TOAST_LONG_MS,
                                        tag="update")
        elif state == "current":
            if tray:
                self.toast.show_message(tr("toast.current"), tag="update")
        elif state == "error":
            if tray:
                self.toast.show_message(tr("toast.check_failed"), tag="update")


def main():
    winapi.set_app_id(APP_ID)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    aegis = Aegis(qapp)
    aegis.start()
    if "--show" in sys.argv:
        QTimer.singleShot(0, aegis.panel.summon)
    return qapp.exec()
