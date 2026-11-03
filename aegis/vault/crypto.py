"""
Шифрование базы.

Ключ выводится из мастер-пароля Argon2id (стойкий к перебору на видеокартах:
каждая попытка требует 64 МБ памяти), содержимое шифруется AES-256-GCM. GCM
проверяет целостность: неверный пароль и испорченный файл одинаково дают
InvalidPassword, а не мусор вместо записей.

Формат файла:

    b"AEGIS" + версия (1 байт)
    длина заголовка (4 байта, little-endian) + заголовок JSON
    шифротекст

Заголовок открыт — в нём только параметры Argon2, соль и nonce. Он же идёт в
GCM как associated data: подменить параметры, не сломав проверку, нельзя.

Ключ живёт в памяти, пока база открыта, — чтобы каждое сохранение не ждало
Argon2 полсекунды. При блокировке ссылки на него обнуляются; стереть байты в
памяти Python честно не умеет, это ограничение любой программы на нём.
"""

import base64
import json
import os
import struct

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"AEGIS"
VERSION = 1

# Параметры для новых баз. Время на обычном ноутбуке — около 0,3–0,6 с.
# Старые базы читаются с теми параметрами, что записаны в их заголовке.
KDF_TIME = 3
KDF_MEMORY_KIB = 64 * 1024
KDF_LANES = 4
KEY_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12


class InvalidPassword(Exception):
    """Пароль не подошёл или файл повреждён — GCM их не различает."""


class BadFile(Exception):
    """Это не база Aegis или неизвестная версия формата."""


def _b64(data):
    return base64.b64encode(data).decode("ascii")


def _unb64(text):
    return base64.b64decode(text.encode("ascii"))


class Key:
    """Выведенный ключ вместе с солью и параметрами, из которых он получен."""

    def __init__(self, raw, salt, t, m, p):
        self.raw = raw
        self.salt = salt
        self.t, self.m, self.p = t, m, p

    def wipe(self):
        self.raw = b""


def derive(password, salt=None, t=KDF_TIME, m=KDF_MEMORY_KIB, p=KDF_LANES):
    salt = salt or os.urandom(SALT_LEN)
    raw = hash_secret_raw(password.encode("utf-8"), salt, time_cost=t, memory_cost=m,
                          parallelism=p, hash_len=KEY_LEN, type=Type.ID)
    return Key(raw, salt, t, m, p)


def encrypt(key, payload):
    """payload — dict; возвращает байты файла."""
    nonce = os.urandom(NONCE_LEN)
    header = json.dumps({"kdf": "argon2id", "t": key.t, "m": key.m, "p": key.p,
                         "salt": _b64(key.salt), "nonce": _b64(nonce)},
                        separators=(",", ":")).encode("utf-8")
    plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    cipher = AESGCM(key.raw).encrypt(nonce, plain, header)
    return MAGIC + bytes([VERSION]) + struct.pack("<I", len(header)) + header + cipher


def read_header(blob):
    """(заголовок dict, байты заголовка, шифротекст)."""
    if len(blob) < len(MAGIC) + 5 or not blob.startswith(MAGIC):
        raise BadFile("not an Aegis vault")
    pos = len(MAGIC)
    if blob[pos] != VERSION:
        raise BadFile("unsupported version %d" % blob[pos])
    pos += 1
    (size,) = struct.unpack_from("<I", blob, pos)
    pos += 4
    raw_header = blob[pos:pos + size]
    try:
        header = json.loads(raw_header.decode("utf-8"))
    except ValueError as error:
        raise BadFile("broken header") from error
    if header.get("kdf") != "argon2id":
        raise BadFile("unknown kdf")
    return header, raw_header, blob[pos + size:]


def decrypt(password, blob):
    """(payload, key). Ключ возвращается, чтобы сохранять без нового Argon2."""
    header, raw_header, cipher = read_header(blob)
    key = derive(password, _unb64(header["salt"]), int(header["t"]), int(header["m"]),
                 int(header["p"]))
    return decrypt_with(key, blob), key


def decrypt_with(key, blob):
    header, raw_header, cipher = read_header(blob)
    try:
        plain = AESGCM(key.raw).decrypt(_unb64(header["nonce"]), cipher, raw_header)
    except (InvalidTag, ValueError) as error:
        raise InvalidPassword() from error
    return json.loads(plain.decode("utf-8"))
