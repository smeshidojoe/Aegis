import os
import sys

APP_NAME    = "Aegis"
APP_VERSION = "0.1.0"

GITHUB_REPO   = "SmeshidoJoe/Aegis"
DEVELOPER_URL = "https://github.com/SmeshidoJoe"

# Идентификатор для Windows: под ним группируются уведомления и панель задач.
APP_ID = "SmeshidoJoe.Aegis"

# Именованный мьютекс защиты от второго запуска (см. main.py). Тот же знает
# установщик — по нему он закрывает программу перед заменой exe.
INSTANCE_MUTEX = "Aegis-Single-Instance-Mutex"

# Локальный сокет: второй запуск просит первый показать строку, а посредник
# расширения браузера (aegis/bridge.py) передаёт через него запросы.
IPC_NAME = "Aegis-IPC"

# Имя посредника для native messaging — его ищут браузеры в реестре.
NATIVE_HOST = "com.smeshidojoe.aegis"
# Расширение с ключом из extension/manifest.json получает этот id и
# распакованным, и собранным. Другим расширениям посредник не откроется.
CHROME_EXTENSION_ID = "cpmcdhghjcoegjcjgkedndjkdckkchka"
FIREFOX_EXTENSION_ID = "aegis@smeshidojoe"

# В сборке PyInstaller ресурсы лежат во временной папке _MEIPASS, в разработке —
# в корне репозитория.
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
APP_ICO    = os.path.join(ASSETS_DIR, "app.ico")
# Расширение внутри сборки. Браузер загружает его не отсюда (временная папка
# exe исчезает после выхода), а из копии в CACHE_DIR — см. bridge.sync_extension.
BUNDLED_EXTENSION = os.path.join(BASE_DIR, "extension")

# Всё своё — в %APPDATA%\Aegis: маленькое и переживает переустановку.
#   vault.aegis  — зашифрованная база
#   backups\     — копии базы (aegis/vault/backup.py)
#   config.json  — настройки, без секретов
_ROAMING = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
_LOCAL = os.environ.get("LOCALAPPDATA") or _ROAMING
APP_DIR   = os.path.join(_ROAMING, APP_NAME)
CACHE_DIR = os.path.join(_LOCAL, APP_NAME)

CONFIG_PATH = os.path.join(APP_DIR, "config.json")
VAULT_PATH  = os.path.join(APP_DIR, "vault.aegis")
BACKUP_DIR  = os.path.join(APP_DIR, "backups")
LOG_PATH    = os.path.join(APP_DIR, "aegis.log")
# Манифесты посредника для браузеров (их путь прописан в реестре).
HOST_DIR    = os.path.join(CACHE_DIR, "native-host")
# Папка, которую показываем для «Загрузить распакованное»: постоянная, и
# обновляется вместе с программой. В разработке — прямо extension/ репозитория.
EXTENSION_DIR = (os.path.join(CACHE_DIR, "extension") if getattr(sys, "frozen", False)
                 else BUNDLED_EXTENSION)

# Первый ли это запуск — снимаем до того, как что-либо создаст APP_DIR.
IS_FIRST_RUN = not os.path.isdir(APP_DIR)
