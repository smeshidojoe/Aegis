"""
Пароли, сохранённые в браузерах.

Два пути:

* Напрямую — где браузер хранит пароли под защитой одной лишь учётной записи
  Windows: Chromium без App-Bound Encryption (Vivaldi, Opera, Chromium) и
  Firefox без основного пароля. Читаем копию базы браузера и расшифровываем
  так же, как это сделал бы сам браузер под вашим пользователем.
* Через выгрузку — Chrome, Edge, Brave (с 2024 года App-Bound Encryption:
  расшифровать может только сам браузер). Обходить эту защиту не будем —
  так делают программы-стилеры. Открываем страницу выгрузки в браузере,
  человек подтверждает PIN Windows, а файл подхватывает watch.py.

Записи отсюда — обычные Entry; повторы отсекает импорт (csvio.is_duplicate).
"""

import base64
import ctypes
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import tempfile
from ctypes import wintypes
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .csvio import title_from_url
from .store import Entry

try:                                        # cryptography 43+ держит 3DES отдельно
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:                         # pragma: no cover
    TripleDES = algorithms.TripleDES

_L = os.environ.get("LOCALAPPDATA", "")
_R = os.environ.get("APPDATA", "")


@dataclass
class Browser:
    key: str
    name: str
    root: str                 # папка с профилями
    exe: str                  # для ShellExecute (App Paths знает полный путь)
    export_url: str = ""      # страница выгрузки паролей
    kind: str = "chromium"    # chromium | firefox


KNOWN = (
    Browser("chrome", "Google Chrome", os.path.join(_L, r"Google\Chrome\User Data"),
            "chrome.exe", "chrome://password-manager/settings"),
    Browser("edge", "Microsoft Edge", os.path.join(_L, r"Microsoft\Edge\User Data"),
            "msedge.exe", "edge://settings/passwords"),
    Browser("brave", "Brave", os.path.join(_L, r"BraveSoftware\Brave-Browser\User Data"),
            "brave.exe", "brave://password-manager/settings"),
    Browser("vivaldi", "Vivaldi", os.path.join(_L, r"Vivaldi\User Data"),
            "vivaldi.exe", "chrome://password-manager/settings"),
    Browser("opera", "Opera", os.path.join(_R, r"Opera Software\Opera Stable"),
            "opera.exe", "opera://settings/passwords"),
    Browser("yandex", "Яндекс Браузер", os.path.join(_L, r"Yandex\YandexBrowser\User Data"),
            "browser.exe"),
    Browser("chromium", "Chromium", os.path.join(_L, r"Chromium\User Data"), "chrome.exe",
            "chrome://password-manager/settings"),
    Browser("firefox", "Firefox", os.path.join(_R, r"Mozilla\Firefox"), "firefox.exe",
            "about:logins", kind="firefox"),
)


@dataclass
class Result:
    entries: list = field(default_factory=list)
    skipped: int = 0          # записи, которые расшифровать не вышло
    error: str = ""           # "" | app_bound | primary_password | unreadable


def installed():
    """Браузеры, у которых есть папка профилей."""
    out = []
    for browser in KNOWN:
        if browser.kind == "firefox":
            if _firefox_profiles(browser.root):
                out.append(browser)
        elif os.path.isfile(os.path.join(browser.root, "Local State")):
            out.append(browser)
    return out


def app_bound(browser):
    """Chromium с App-Bound Encryption: пароли расшифровывает только сам браузер."""
    if browser.kind != "chromium":
        return False
    state = _local_state(browser.root)
    return "app_bound_encrypted_key" in state.get("os_crypt", {})


def can_read(browser):
    return not app_bound(browser)


def read(browser):
    """Записи браузера напрямую. Без исключений: что не вышло — в Result."""
    try:
        if browser.kind == "firefox":
            return _read_firefox(browser)
        if app_bound(browser):
            return Result(error="app_bound")
        return _read_chromium(browser)
    except Exception:
        return Result(error="unreadable")


# --- Chromium ----------------------------------------------------------------- #

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi_unprotect(data):
    """CryptUnprotectData: расшифровать то, что зашифровано под этим пользователем."""
    src = _BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                       ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None,
                                                    None, 0, ctypes.byref(out)):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _local_state(root):
    try:
        with open(os.path.join(root, "Local State"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _chromium_profiles(root):
    """Папки с базой паролей: Default, Profile 1… — или сам root (Opera)."""
    if os.path.isfile(os.path.join(root, "Login Data")):
        return [root]
    out = []
    try:
        for name in os.listdir(root):
            if os.path.isfile(os.path.join(root, name, "Login Data")):
                out.append(os.path.join(root, name))
    except OSError:
        pass
    return out


def _copy_db(path):
    """Копия базы во временную папку: открытый браузер держит оригинал."""
    folder = tempfile.mkdtemp(prefix="aegis-import-")
    target = os.path.join(folder, "db")
    shutil.copyfile(path, target)
    return folder, target


def chromium_decrypt(value, key):
    """password_value -> текст или None (v20 и всё, что не расшифровалось)."""
    if value[:3] in (b"v10", b"v11"):
        if key is None:
            return None
        nonce, cipher = value[3:15], value[15:]
        return AESGCM(key).decrypt(nonce, cipher, None).decode("utf-8")
    if value[:3] == b"v20":
        return None
    return dpapi_unprotect(value).decode("utf-8")


def _read_chromium(browser):
    state = _local_state(browser.root)
    encoded = state.get("os_crypt", {}).get("encrypted_key")
    key = None
    if encoded:
        raw = base64.b64decode(encoded)
        if raw.startswith(b"DPAPI"):
            key = dpapi_unprotect(raw[5:])
    result = Result()
    for profile in _chromium_profiles(browser.root):
        folder, db = _copy_db(os.path.join(profile, "Login Data"))
        try:
            with sqlite3.connect(db) as conn:
                rows = conn.execute("SELECT origin_url, username_value, password_value "
                                    "FROM logins WHERE blacklisted_by_user = 0").fetchall()
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        for url, username, blob in rows:
            if not blob:
                continue
            try:
                password = chromium_decrypt(bytes(blob), key)
            except Exception:
                password = None
            if password is None:
                result.skipped += 1
                continue
            result.entries.append(_entry(url, username, password))
    return result


def _entry(url, username, password):
    url = url or ""
    title = title_from_url(url) if url and not url.startswith("android://") else (url or "—")
    return Entry(title=title, url=url, username=username or "", password=password)


# --- Firefox ------------------------------------------------------------------ #
#
# logins.json — логины и пароли, каждый зашифрован ключом из key4.db. Сам ключ
# в key4.db зашифрован основным паролем Firefox (по умолчанию пустым): PBES2
# (PBKDF2-SHA256 + AES-256-CBC) у новых профилей, SHA1 + 3DES у старых.

def _firefox_profiles(root):
    out = []
    profiles = os.path.join(root, "Profiles")
    try:
        for name in os.listdir(profiles):
            path = os.path.join(profiles, name)
            if os.path.isfile(os.path.join(path, "logins.json")) and \
                    os.path.isfile(os.path.join(path, "key4.db")):
                out.append(path)
    except OSError:
        pass
    return out


def der(data, pos=0):
    """Минимальный разбор DER: (значение, позиция после). SEQUENCE -> list,
    OCTET STRING -> bytes, OID -> "1.2.3", INTEGER -> int, NULL -> None."""
    tag = data[pos]
    length = data[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[pos:pos + count], "big")
        pos += count
    body = data[pos:pos + length]
    end = pos + length
    if tag == 0x30:
        items, i = [], 0
        while i < len(body):
            item, i = der(body, i)
            items.append(item)
        return items, end
    if tag == 0x06:
        parts = [body[0] // 40, body[0] % 40]
        value = 0
        for b in body[1:]:
            value = (value << 7) | (b & 0x7F)
            if not b & 0x80:
                parts.append(value)
                value = 0
        return ".".join(map(str, parts)), end
    if tag == 0x02:
        return int.from_bytes(body, "big"), end
    if tag == 0x05:
        return None, end
    return bytes(body), end


_PBES2 = "1.2.840.113549.1.5.13"
_PBE_SHA1_3DES = "1.2.840.113549.1.12.5.1.3"
_DES3_CBC = "1.2.840.113549.3.7"
_AES256_CBC = "2.16.840.1.101.3.4.1.42"


def _unpad(data):
    n = data[-1] if data else 0
    return data[:-n] if 0 < n <= 16 else data


def _cbc(algo, key, iv, data):
    cipher = Cipher(algo(key), modes.CBC(iv)).decryptor()
    return cipher.update(data) + cipher.finalize()


def _pbe_decrypt(blob, global_salt, password=b""):
    (algo, cipher), _ = der(blob)
    oid = algo[0]
    if oid == _PBES2:
        kdf, enc = algo[1]
        salt, iterations, key_len = kdf[1][0], kdf[1][1], kdf[1][2]
        k = hashlib.sha1(global_salt + password).digest()
        key = hashlib.pbkdf2_hmac("sha256", k, salt, iterations, key_len)
        iv = b"\x04\x0e" + enc[1]
        return _unpad(_cbc(algorithms.AES, key, iv, cipher))
    if oid == _PBE_SHA1_3DES:
        entry_salt = algo[1][0]
        hp = hashlib.sha1(global_salt + password).digest()
        pes = entry_salt + b"\x00" * (20 - len(entry_salt))
        chp = hashlib.sha1(hp + entry_salt).digest()
        k1 = hmac.new(chp, pes + entry_salt, hashlib.sha1).digest()
        tk = hmac.new(chp, pes, hashlib.sha1).digest()
        k2 = hmac.new(chp, tk + entry_salt, hashlib.sha1).digest()
        k = k1 + k2
        return _unpad(_cbc(TripleDES, k[:24], k[-8:], cipher))
    raise ValueError("unknown pbe " + oid)


def firefox_key(key4_path):
    """Ключ логинов. ValueError("primary_password") — задан основной пароль."""
    with sqlite3.connect(key4_path) as conn:
        global_salt, check = conn.execute(
            "SELECT item1, item2 FROM metadata WHERE id = 'password'").fetchone()
        if _pbe_decrypt(bytes(check), bytes(global_salt)) != b"password-check":
            raise ValueError("primary_password")
        for a11, _a102 in conn.execute("SELECT a11, a102 FROM nssPrivate"):
            key = _pbe_decrypt(bytes(a11), bytes(global_salt))
            if len(key) >= 24:
                return key
    raise ValueError("no key")


def firefox_decrypt(value, key):
    (_key_id, (oid, iv), cipher), _ = der(base64.b64decode(value))
    if oid == _AES256_CBC:
        return _unpad(_cbc(algorithms.AES, key[:32], iv, cipher)).decode("utf-8")
    if oid == _DES3_CBC:
        return _unpad(_cbc(TripleDES, key[:24], iv, cipher)).decode("utf-8")
    raise ValueError("unknown cipher " + oid)


def _read_firefox(browser):
    result = Result()
    for profile in _firefox_profiles(browser.root):
        folder, key4 = _copy_db(os.path.join(profile, "key4.db"))
        try:
            key = firefox_key(key4)
        except ValueError as error:
            if str(error) == "primary_password":
                result.error = "primary_password"
                continue
            raise
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        with open(os.path.join(profile, "logins.json"), encoding="utf-8") as f:
            logins = json.load(f).get("logins", [])
        for login in logins:
            try:
                username = firefox_decrypt(login["encryptedUsername"], key)
                password = firefox_decrypt(login["encryptedPassword"], key)
            except Exception:
                result.skipped += 1
                continue
            result.entries.append(_entry(login.get("hostname", ""), username, password))
    return result
