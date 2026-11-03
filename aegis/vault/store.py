"""
База паролей: записи в памяти, файл на диске.

Пока база заперта, в памяти нет ни записей, ни ключа — только путь к файлу.
Открыли — расшифровали целиком: записей у человека сотни, не миллионы, и
искать по ним проще и быстрее в памяти.

Каждое изменение сразу пишется на диск: во временный файл рядом, потом
os.replace — оборванная запись оставит прежнюю базу целой. После записи
backup.py решает, пора ли сделать копию.
"""

import os
import time
import uuid
from dataclasses import asdict, dataclass, field

from . import crypto

FORMAT = 1


@dataclass
class Entry:
    title: str = ""
    username: str = ""
    password: str = ""
    url: str = ""
    # Часть заголовка окна для программ без адреса: «Steam», «Telegram».
    window: str = ""
    notes: str = ""
    # Секрет TOTP (base32) или ссылка otpauth://.
    totp: str = ""
    # Пустая — по умолчанию (autotype.DEFAULT_SEQUENCE).
    sequence: str = ""
    favorite: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: float = field(default_factory=time.time)
    modified: float = field(default_factory=time.time)
    used: float = 0.0
    uses: int = 0

    @classmethod
    def from_dict(cls, data):
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self):
        return asdict(self)


class Locked(Exception):
    """Действие требует открытой базы."""


class Vault:
    def __init__(self, path, on_saved=None):
        self.path = path
        self.on_saved = on_saved        # вызывается после каждой записи на диск
        self._key = None
        self.entries = []

    # --- состояние --------------------------------------------------------- #

    def exists(self):
        return os.path.isfile(self.path)

    def is_unlocked(self):
        return self._key is not None

    def create(self, password):
        """Новая пустая база. Существующую не перезаписывает."""
        if self.exists():
            raise FileExistsError(self.path)
        self._key = crypto.derive(password)
        self.entries = []
        self.save()

    def unlock(self, password):
        """Бросает crypto.InvalidPassword или crypto.BadFile."""
        with open(self.path, "rb") as f:
            blob = f.read()
        payload, key = crypto.decrypt(password, blob)
        self.entries = [Entry.from_dict(e) for e in payload.get("entries", [])
                        if isinstance(e, dict)]
        self._key = key

    def lock(self):
        if self._key is not None:
            self._key.wipe()
        self._key = None
        self.entries = []

    def check_password(self, password):
        """Тот ли это мастер-пароль — перед опасными действиями (экспорт)."""
        if not self.is_unlocked():
            return False
        try:
            with open(self.path, "rb") as f:
                crypto.decrypt(password, f.read())
            return True
        except (OSError, crypto.InvalidPassword, crypto.BadFile):
            return False

    def change_password(self, new_password):
        self._require()
        self._key = crypto.derive(new_password)
        self.save()

    # --- записи ------------------------------------------------------------ #

    def get(self, entry_id):
        return next((e for e in self.entries if e.id == entry_id), None)

    def put(self, entry):
        """Новая запись или изменённая существующая."""
        self._require()
        entry.modified = time.time()
        for i, old in enumerate(self.entries):
            if old.id == entry.id:
                self.entries[i] = entry
                break
        else:
            self.entries.append(entry)
        self.save()

    def put_many(self, entries):
        """Импорт: одна запись на диск и одна копия, а не по штуке на запись."""
        self._require()
        self.entries.extend(entries)
        self.save()

    def delete(self, entry_id):
        self._require()
        self.entries = [e for e in self.entries if e.id != entry_id]
        self.save()

    def touch(self, entry):
        """Запись использовали — для порядка «недавние». Без копии: не изменение."""
        self._require()
        entry.used = time.time()
        entry.uses += 1
        self.save(backup=False)

    # --- диск -------------------------------------------------------------- #

    def save(self, backup=True):
        self._require()
        payload = {"format": FORMAT, "saved": time.time(),
                   "entries": [e.to_dict() for e in self.entries]}
        blob = crypto.encrypt(self._key, payload)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        if backup and self.on_saved is not None:
            self.on_saved(self.path)

    def _require(self):
        if self._key is None:
            raise Locked()
