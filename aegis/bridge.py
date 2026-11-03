"""
Расширение браузера: регистрация посредника и ответы на его запросы.

Цепочка: расширение -> браузер -> посредник (aegis/host.py) -> канал
Aegis-IPC -> этот модуль. Расширение — дополнительная возможность: без него
всё остальное работает через хоткей и автонабор.

Доступ расширения к базе — только после сопряжения. Первым сообщением оно
просит «pair»; Aegis показывает вопрос, и только если человек согласился,
выдаёт расширению случайный ключ. Дальше каждый запрос несёт этот ключ.
Канал Aegis-IPC и так открыт только своему пользователю Windows, ключ
отсекает чужие расширения в том же браузере.

Расширению никогда не отдаётся список паролей. На «query» — только названия
и логины записей, подходящих сайту; пароль — на «fill» одной выбранной
записи и только если она подходит сайту, с которого просят.

Протокол — по строке JSON на сообщение, на каждое ровно один ответ (см.
host.py). В ответ кладём тот же rid, что пришёл в запросе.
"""

import hmac
import json
import os
import secrets
import shutil
import sys

from PySide6.QtCore import QObject, QTimer

from .core import jsonfile, logbook
from .core.constants import (BUNDLED_EXTENSION, CHROME_EXTENSION_ID, EXTENSION_DIR,
                             FIREFOX_EXTENSION_ID, HOST_DIR, NATIVE_HOST)
from .vault import search, totp

PAIR_TIMEOUT_MS = 60_000

# Где браузеры ищут посредников. Brave, Vivaldi, Opera и Arc читают ключ Chrome.
_CHROMIUM_KEYS = (
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\Chromium\NativeMessagingHosts",
    r"Software\Yandex\YandexBrowser\NativeMessagingHosts",
)
_FIREFOX_KEY = r"Software\Mozilla\NativeMessagingHosts"


# --- регистрация посредника --------------------------------------------------- #

def host_command():
    """Что запускает браузер. В разработке — .bat с python main.py --native-host."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bat = os.path.join(HOST_DIR, "aegis-host-dev.bat")
    os.makedirs(HOST_DIR, exist_ok=True)
    python = sys.executable.replace("pythonw.exe", "python.exe")
    with open(bat, "w", encoding="utf-8") as f:
        f.write('@echo off\r\n"%s" "%s" --native-host %%*\r\n'
                % (python, os.path.join(root, "main.py")))
    return bat


def register():
    """Манифесты посредника и ключи реестра — на каждом старте: путь к exe мог
    смениться после переустановки."""
    try:
        import winreg
        command = host_command()
        base = {"name": NATIVE_HOST, "description": "Aegis password manager",
                "path": command, "type": "stdio"}
        chrome = os.path.join(HOST_DIR, "chrome.json")
        firefox = os.path.join(HOST_DIR, "firefox.json")
        jsonfile.save(chrome, dict(base, allowed_origins=[
            "chrome-extension://%s/" % CHROME_EXTENSION_ID]))
        jsonfile.save(firefox, dict(base, allowed_extensions=[FIREFOX_EXTENSION_ID]))
        for key, manifest in [(k, chrome) for k in _CHROMIUM_KEYS] + [(_FIREFOX_KEY, firefox)]:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + "\\" + NATIVE_HOST) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, manifest)
        return True
    except OSError:
        logbook.exc("регистрация посредника")
        return False


def sync_extension():
    """
    Копия расширения из сборки в постоянную папку — если её нет или версия в
    manifest.json другая. После обновления Aegis браузер подхватит новую
    версию при следующем запуске (или по «Обновить» на странице расширений).
    """
    if os.path.normcase(EXTENSION_DIR) == os.path.normcase(BUNDLED_EXTENSION):
        return
    try:
        bundled = jsonfile.load(os.path.join(BUNDLED_EXTENSION, "manifest.json"), {})
        current = jsonfile.load(os.path.join(EXTENSION_DIR, "manifest.json"), {})
        if bundled and bundled.get("version") == current.get("version"):
            return
        shutil.copytree(BUNDLED_EXTENSION, EXTENSION_DIR, dirs_exist_ok=True)
    except OSError:
        logbook.exc("копия расширения")


def unregister():
    try:
        import winreg
        for key in _CHROMIUM_KEYS + (_FIREFOX_KEY,):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key + "\\" + NATIVE_HOST)
            except OSError:
                pass
    except ImportError:
        pass


# --- запросы ------------------------------------------------------------------ #

class Connection(QObject):
    """Один посредник (один браузер). Читает строки, отвечает строками."""

    def __init__(self, socket, bridge):
        super().__init__(bridge)
        self.socket = socket
        self.bridge = bridge
        self.buf = b""
        self.browser = ""
        socket.readyRead.connect(self._on_ready)
        socket.disconnected.connect(self._on_gone)

    def feed(self, data):
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                message = json.loads(line.decode("utf-8"))
            except ValueError:
                self.reply({}, {"type": "error", "error": "bad_json"})
                continue
            if isinstance(message, dict):
                self.bridge.handle(self, message)

    def _on_ready(self):
        self.feed(bytes(self.socket.readAll()))

    def _on_gone(self):
        self.bridge.forget(self)
        self.socket.deleteLater()

    def reply(self, request, message):
        message = dict(message, rid=request.get("rid"))
        if self.socket.isValid():
            self.socket.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
            self.socket.flush()


class Bridge(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.connections = []
        self.tab_url = {}         # браузер (имя exe) -> адрес активной вкладки

    def adopt(self, socket, rest=b""):
        conn = Connection(socket, self)
        self.connections.append(conn)
        if rest:
            conn.feed(rest)

    def forget(self, conn):
        if conn in self.connections:
            self.connections.remove(conn)

    # --- сопряжение -------------------------------------------------------- #

    def _pairs(self):
        pairs = self.app.config.get("bridge_pairs")
        return dict(pairs) if isinstance(pairs, dict) else {}

    def _authorized(self, message):
        pair = self._pairs().get(str(message.get("pair_id", "")))
        key = str(message.get("key", ""))
        return bool(pair and key) and hmac.compare_digest(pair.get("key", ""), key)

    def unpair(self, pair_id):
        pairs = self._pairs()
        pairs.pop(pair_id, None)
        self.app.config.set("bridge_pairs", pairs)

    def _pair(self, conn, message):
        name = str(message.get("browser") or "browser")[:40]
        answered = {"done": False}

        def answer(allowed):
            if answered["done"]:
                return
            answered["done"] = True
            if not allowed:
                conn.reply(message, {"type": "denied"})
                return
            pair_id, key = secrets.token_hex(8), secrets.token_urlsafe(32)
            pairs = self._pairs()
            pairs[pair_id] = {"name": name, "key": key}
            self.app.config.set("bridge_pairs", pairs)
            conn.reply(message, {"type": "paired", "pair_id": pair_id, "key": key})

        self.app.ask_pairing(name, answer)
        QTimer.singleShot(PAIR_TIMEOUT_MS, lambda: answer(False))

    # --- разбор ------------------------------------------------------------ #

    def handle(self, conn, message):
        kind = message.get("type")
        if not self.app.config.get("bridge_enabled"):
            conn.reply(message, {"type": "error", "error": "disabled"})
            return
        if kind == "pair":
            self._pair(conn, message)
            return
        if kind == "ping":
            conn.reply(message, {"type": "pong"})
            return
        if not self._authorized(message):
            conn.reply(message, {"type": "error", "error": "not_paired"})
            return
        vault = self.app.vault
        try:
            if kind == "hello":
                conn.browser = str(message.get("browser", ""))
                conn.reply(message, {"type": "hello", "locked": not vault.is_unlocked()})
            elif kind == "tab":
                self.tab_url[str(message.get("process", "")).lower()] = str(message.get("url", ""))
                conn.reply(message, {"type": "ok"})
            elif kind == "unlock":
                self.app.summon_unlock()
                conn.reply(message, {"type": "ok"})
            elif kind == "open":
                self.app.summon_for_url(str(message.get("url", "")))
                conn.reply(message, {"type": "ok"})
            elif kind == "query":
                self._query(conn, message)
            elif kind == "fill":
                self._fill(conn, message)
            elif kind == "save":
                self.app.offer_save(str(message.get("url", "")),
                                    str(message.get("username", "")),
                                    str(message.get("password", "")))
                conn.reply(message, {"type": "ok"})
            else:
                conn.reply(message, {"type": "error", "error": "unknown"})
        except Exception:
            logbook.exc("мост: " + str(kind))
            conn.reply(message, {"type": "error", "error": "internal"})

    def _matching(self, url):
        context = search.Context(url=url)
        return [e for e in self.app.vault.entries if e.url and search.matches_context(e, context)]

    def _query(self, conn, message):
        vault = self.app.vault
        if not vault.is_unlocked():
            conn.reply(message, {"type": "entries", "locked": True, "entries": []})
            return
        url = str(message.get("url", ""))
        entries = sorted(self._matching(url), key=lambda e: (e.used, e.modified), reverse=True)
        known = message.get("username"), message.get("password")
        conn.reply(message, {
            "type": "entries", "locked": False,
            "entries": [{"id": e.id, "title": e.title, "username": e.username} for e in entries],
            # Для предложения «сохранить»: есть ли уже такая пара логин+пароль.
            "known": bool(known[1]) and any((e.username, e.password) == known for e in entries),
        })

    def _fill(self, conn, message):
        vault = self.app.vault
        if not vault.is_unlocked():
            conn.reply(message, {"type": "error", "error": "locked"})
            return
        entry = vault.get(str(message.get("entry_id", "")))
        if entry is None or entry not in self._matching(str(message.get("url", ""))):
            conn.reply(message, {"type": "error", "error": "no_entry"})
            return
        code = ""
        if entry.totp:
            try:
                code = totp.code(entry.totp)
            except ValueError:
                pass
        vault.touch(entry)
        conn.reply(message, {"type": "credentials", "username": entry.username,
                             "password": entry.password, "totp": code})
