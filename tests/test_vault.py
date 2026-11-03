import os
import time

import pytest

from aegis.vault import backup, crypto, csvio, generator, totp
from aegis.vault.search import Context, matches_context, search, site_of
from aegis.vault.store import Entry, Locked, Vault

# Быстрый Argon2 для тестов: настоящие параметры тратят полсекунды на вызов.
FAST = dict(t=1, m=1024, p=1)


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch):
    real = crypto.derive

    def derive(password, salt=None, t=None, m=None, p=None):
        return real(password, salt, FAST["t"], FAST["m"], FAST["p"])

    monkeypatch.setattr(crypto, "derive", derive)


# --- шифрование --------------------------------------------------------------- #

def test_roundtrip_and_wrong_password():
    key = crypto.derive("correct horse")
    blob = crypto.encrypt(key, {"entries": [{"title": "Почта"}]})
    payload, _key = crypto.decrypt("correct horse", blob)
    assert payload["entries"][0]["title"] == "Почта"
    with pytest.raises(crypto.InvalidPassword):
        crypto.decrypt("wrong", blob)


def test_tampered_header_is_rejected():
    key = crypto.derive("pw")
    blob = bytearray(crypto.encrypt(key, {"x": 1}))
    # Меняем nonce в открытом заголовке — GCM должен это заметить.
    i = blob.index(b'"nonce":"') + 9
    blob[i] = ord("A") if blob[i] != ord("A") else ord("B")
    with pytest.raises(crypto.InvalidPassword):
        crypto.decrypt("pw", bytes(blob))


def test_not_a_vault():
    with pytest.raises(crypto.BadFile):
        crypto.decrypt("pw", b"hello world, not a vault")


def test_nonce_differs_between_saves():
    key = crypto.derive("pw")
    assert crypto.encrypt(key, {"a": 1}) != crypto.encrypt(key, {"a": 1})


# --- база --------------------------------------------------------------------- #

def test_vault_lifecycle(tmp_path):
    saved = []
    vault = Vault(str(tmp_path / "v.aegis"), on_saved=saved.append)
    vault.create("master-pass")
    vault.put(Entry(title="GitHub", username="me", password="s3cret", url="github.com"))
    assert saved
    vault.lock()
    assert vault.entries == [] and not vault.is_unlocked()
    with pytest.raises(Locked):
        vault.put(Entry(title="x"))
    with pytest.raises(crypto.InvalidPassword):
        vault.unlock("nope")
    vault.unlock("master-pass")
    assert [e.password for e in vault.entries] == ["s3cret"]
    # Пароль на диске не лежит открытым текстом.
    assert b"s3cret" not in (tmp_path / "v.aegis").read_bytes()


def test_change_password(tmp_path):
    vault = Vault(str(tmp_path / "v.aegis"))
    vault.create("old-password")
    vault.put(Entry(title="A"))
    assert vault.check_password("old-password")
    vault.change_password("new-password")
    vault.lock()
    with pytest.raises(crypto.InvalidPassword):
        vault.unlock("old-password")
    vault.unlock("new-password")
    assert vault.entries[0].title == "A"


def test_create_refuses_to_overwrite(tmp_path):
    vault = Vault(str(tmp_path / "v.aegis"))
    vault.create("pw-pw-pw-pw")
    with pytest.raises(FileExistsError):
        Vault(vault.path).create("other")


def test_unknown_fields_are_ignored():
    entry = Entry.from_dict({"title": "A", "from_the_future": 1})
    assert entry.title == "A"


# --- копии -------------------------------------------------------------------- #

def test_backups_coalesce_and_keep(tmp_path):
    src = tmp_path / "v.aegis"
    src.write_bytes(b"v1")
    folder = str(tmp_path / "b")
    now = time.time()
    backup.snapshot(str(src), folder, now)
    backup.snapshot(str(src), folder, now + 60)          # в пределах сеанса — замена
    assert len(backup.listing(folder)) == 1
    backup.snapshot(str(src), folder, now + 3600)        # новый сеанс — новая копия
    assert len(backup.listing(folder)) == 2


def test_manual_copy_survives_next_edit(tmp_path):
    src = tmp_path / "v.aegis"
    src.write_bytes(b"before-restore")
    folder = str(tmp_path / "b")
    now = time.time()
    manual = backup.snapshot(str(src), folder, now, coalesce=False)
    src.write_bytes(b"after")
    backup.snapshot(str(src), folder, now + 60)
    backup.snapshot(str(src), folder, now + 120)       # эта заменяет предыдущую, не ручную
    paths = [p for _, p in backup.listing(folder)]
    assert manual in paths and len(paths) == 2
    assert open(manual, "rb").read() == b"before-restore"


def test_backup_retention():
    now = time.mktime((2026, 11, 3, 12, 0, 0, 0, 0, -1))
    # 100 копий раз в 6 часов: 25 дней назад и ближе.
    stamps = [now - i * 6 * 3600 for i in range(100)]
    keep = backup.keep_set(stamps, now)
    assert set(stamps[:backup.KEEP_RECENT]) <= keep
    assert len(keep) < len(stamps)
    days = {time.localtime(s)[:3] for s in stamps}
    assert days == {time.localtime(s)[:3] for s in keep}       # каждый день остался


def test_backups_restore_keeps_current(tmp_path):
    vault_path = tmp_path / "v.aegis"
    vault_path.write_bytes(b"current")
    old = tmp_path / "old.aegis"
    old.write_bytes(b"old")
    backups = backup.Backups(str(tmp_path / "b"))
    backups.restore(str(old), str(vault_path))
    assert vault_path.read_bytes() == b"old"
    assert any(open(p, "rb").read() == b"current" for _, p in backups.all())


def test_extra_folder_unavailable(tmp_path):
    src = tmp_path / "v.aegis"
    src.write_bytes(b"x")
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    backups = backup.Backups(str(tmp_path / "b"), str(blocker / "sub"))
    backups.after_save(str(src))
    assert backups.last_error
    assert len(backup.listing(str(tmp_path / "b"))) == 1


# --- поиск -------------------------------------------------------------------- #

def test_site_matching():
    assert site_of("accounts.google.com") == "google.com"
    assert site_of("bbc.co.uk") == "bbc.co.uk"
    assert site_of("www.news.bbc.co.uk") == "bbc.co.uk"
    entry = Entry(title="Google", url="https://google.com")
    assert matches_context(entry, Context(url="accounts.google.com/signin"))
    assert not matches_context(entry, Context(url="https://google.com.evil.io"))


def test_window_matching():
    steam = Entry(title="Steam", window="Steam")
    assert matches_context(steam, Context(title="Steam — Вход"))
    telegram = Entry(title="Telegram")
    assert matches_context(telegram, Context(title="Telegram Desktop"))
    short = Entry(title="VK")
    assert not matches_context(short, Context(title="VK Music"))


def test_search_sections_and_layout():
    entries = [Entry(title="GitHub", url="github.com", username="me"),
               Entry(title="Почта", url="mail.ru", favorite=True),
               Entry(title="Steam", window="Steam", used=time.time())]
    sections = dict(search(entries, "", Context(url="https://github.com/login")))
    assert [e.title for e in sections["context"]] == ["GitHub"]
    assert [e.title for e in sections["favorites"]] == ["Почта"]
    assert [e.title for e in sections["recent"]] == ["Steam"]
    # Не та раскладка: «пшерги» — это «github».
    (_, found), = search(entries, "пшерги")
    assert found[0].title == "GitHub"


# --- мелочи ------------------------------------------------------------------- #

def test_totp_rfc6238():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"          # «12345678901234567890»
    assert totp.code("otpauth://totp/x?secret=%s&digits=8" % secret, now=59) == "94287082"
    assert totp.code(secret, now=1111111109) == "081804"
    assert not totp.valid("not base32 !!!")


def test_generator():
    password = generator.generate(24, symbols=True)
    assert len(password) == 24
    assert any(c in generator.SYMBOLS for c in password)
    assert not any(c in generator.SYMBOLS for c in generator.generate(30, symbols=False))
    assert generator.strength("123") < generator.strength(password)


def test_csv_import_formats():
    chrome = "name,url,username,password,note\nGitHub,https://github.com,me,pw1,\n"
    bitwarden = ("folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,"
                 "login_password,login_totp\n,,login,Mail,,,,https://mail.ru,a@b,pw2,\n")
    (a,), (b,) = csvio.parse(chrome), csvio.parse(bitwarden)
    assert (a.title, a.username, a.password) == ("GitHub", "me", "pw1")
    assert (b.title, b.url, b.password) == ("Mail", "https://mail.ru", "pw2")
    assert csvio.is_duplicate(a, [Entry(title="x", url="github.com", username="me",
                                        password="pw1")])
    again = csvio.parse(csvio.dump([a, b]))
    assert [e.password for e in again] == ["pw1", "pw2"]
    with pytest.raises(ValueError):
        csvio.parse("a,b\n1,2\n")


def test_paths_are_temporary():
    from aegis.core import constants
    assert "aegis-tests" in constants.VAULT_PATH or "tests" in constants.VAULT_PATH.lower()
    assert os.environ["APPDATA"] in constants.VAULT_PATH


def test_chromium_v10_and_v20():
    import ctypes
    from ctypes import wintypes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from aegis.vault import browsers

    key = os.urandom(32)
    nonce = os.urandom(12)
    blob = b"v10" + nonce + AESGCM(key).encrypt(nonce, "пароль".encode(), None)
    assert browsers.chromium_decrypt(blob, key) == "пароль"
    assert browsers.chromium_decrypt(b"v20" + blob[3:], key) is None

    # Старые записи без префикса — просто DPAPI текущего пользователя.
    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
    data = b"old-secret"
    src = Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)),
                                      ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    assert ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), None, None, None, None,
                                                  0, ctypes.byref(out))
    protected = ctypes.string_at(out.pbData, out.cbData)
    assert browsers.chromium_decrypt(protected, None) == "old-secret"


def test_der_parser():
    from aegis.vault.browsers import der
    # SEQUENCE { OID 1.2.840.113549.3.7, OCTET STRING 01 02, INTEGER 5 }
    blob = bytes.fromhex("3011" "06082a864886f70d0307" "04020102" "020105")
    assert der(blob)[0] == ["1.2.840.113549.3.7", b"\x01\x02", 5]
