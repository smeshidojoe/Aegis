"""Настройки программы: %APPDATA%\\Aegis\\config.json.

Автозапуск хранится здесь и на каждом старте переносится в реестр (см.
Aegis.start). Пока его тут нет (первый запуск), берём из реестра: галочку мог
поставить или снять установщик.
"""

from . import jsonfile
from .constants import CONFIG_PATH

UPDATE_MODES = ("notify", "background")

DEFAULTS = {
    # Строка: поиск записей, а если позвали из окна — сразу подходящие ему.
    "hotkey": "ctrl+shift+e",
    "auto_update": True,
    # notify — плашка в углу, установка с полосой прогресса в строке;
    # background — качается само, в строке появляется «Перезапустить и обновить».
    "update_mode": "background",
    "update_dismissed_version": "",   # о ней уже сказали «позже» — не напоминаем
    "language": "ru",            # en | ru
    "glass": True,
    # Стекло следит за тем, что под строкой, пока она открыта (ui/live_glass.py).
    "live_glass": False,
    "live_fps": 24,              # кадров в секунду у живого фона: 24 | 30 | 60
    "autostart": None,           # None — ещё не решали, берём из реестра
    # Запирать базу: после стольких минут простоя (0 — никогда), при
    # блокировке Windows и уходе в сон.
    "lock_idle_minutes": 15,
    "lock_on_session": True,
    # Через сколько секунд стирать скопированный пароль из буфера (0 — не стирать).
    "clipboard_clear_s": 20,
    # Адрес страницы из окна браузера через UI Automation (core/context.py).
    "read_browser_url": True,
    # Вторая папка для копий базы: облако, флешка. "" — только своя.
    "backup_extra_dir": "",
    "generator_length": 20,
    "generator_symbols": True,
    # Расширение браузера: ключи сопряжённых расширений {id: {"name", "key"}}.
    "bridge_enabled": True,
    "bridge_pairs": {},
}

# В файл пишем только то, что человек менял: тогда новое умолчание в
# следующей версии дойдёт до всех, кто эту настройку не трогал.


class Config:
    def __init__(self, path=CONFIG_PATH):
        self._path = path
        saved = jsonfile.load(path, {})
        if not isinstance(saved, dict):
            saved = {}
        self._saved = saved
        self._data = dict(DEFAULTS)
        self._data.update(saved)

    def get(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        if self._data.get(key) == value:
            return
        self._data[key] = value
        self._saved[key] = value
        jsonfile.save(self._path, self._saved)
