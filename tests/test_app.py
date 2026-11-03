import os

import pytest

from aegis.vault import crypto
from conftest import pump


@pytest.fixture
def aegis(qapp, monkeypatch, tmp_path):
    real = crypto.derive
    monkeypatch.setattr(crypto, "derive",
                        lambda password, salt=None, t=None, m=None, p=None:
                        real(password, salt, 1, 1024, 1))
    from aegis.app import Aegis
    from aegis.core import constants
    monkeypatch.setattr("aegis.app.VAULT_PATH", str(tmp_path / "vault.aegis"))
    monkeypatch.setattr("aegis.app.BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(constants, "VAULT_PATH", str(tmp_path / "vault.aegis"))
    app = Aegis(qapp)
    yield app
    app.panel.hide()
    app.hotkeys.unregister_all()
    app.tray.hide()


def _submit(app, qapp, **fields):
    page = app.panel.unlock
    page.password.setText(fields.get("password", ""))
    page.repeat.setText(fields.get("repeat", ""))
    page.current.setText(fields.get("current", ""))
    page.submit()


def test_first_run_create_add_search_lock(aegis, qapp, tmp_path):
    panel = aegis.panel
    panel.summon()
    assert panel.mode == "setup"

    _submit(aegis, qapp, password="short", repeat="short")
    assert panel.mode == "setup" and not aegis.vault.exists()

    _submit(aegis, qapp, password="long-master-password", repeat="long-master-password")
    assert pump(qapp, lambda: panel.mode == "search")
    assert os.path.isfile(aegis.vault.path)

    panel.edit(None, {"title": "GitHub", "username": "me", "password": "pw-123",
                      "url": "https://github.com"})
    assert panel.mode == "edit"
    panel.editor.submit()
    assert panel.mode == "search"
    assert [e.title for e in aegis.vault.entries] == ["GitHub"]
    assert aegis.backups.all()                         # копия появилась после записи

    panel.input.setText("git")
    assert panel.current().title == "GitHub"
    assert panel.footer.primary                        # «Копировать пароль»

    aegis.lock()
    assert panel.mode == "locked" and aegis.vault.entries == []

    _submit(aegis, qapp, password="wrong-password")
    assert pump(qapp, lambda: not panel.unlock.busy)
    assert panel.mode == "locked"

    _submit(aegis, qapp, password="long-master-password")
    assert pump(qapp, lambda: panel.mode == "search")
    assert aegis.vault.entries[0].password == "pw-123"


def test_settings_page_builds_in_both_states(aegis, qapp):
    aegis.panel.summon("settings")
    assert aegis.panel.mode == "settings"
    assert not aegis.panel.settings.security.isVisibleTo(aegis.panel.settings.widget())
    aegis.set_language("en")
    aegis.set_language("ru")


def test_lock_during_unlock_keeps_vault_closed(aegis, qapp):
    aegis.vault.create("long-master-password")
    aegis.vault.lock()
    aegis.panel.summon()
    aegis.password_submitted("locked", {"password": "long-master-password"})
    aegis.lock()                                   # Win+L, пока считается ключ
    pump(qapp, timeout=1.0)
    assert not aegis.vault.is_unlocked() and aegis.vault.entries == []


def test_open_url_only_web(aegis, monkeypatch):
    from aegis.vault.store import Entry
    opened = []
    monkeypatch.setattr("aegis.core.winapi.shell_open", lambda target, *a, **k: opened.append(target))
    for url in ("file:///C:/x.exe", "\\\\server\\share\\x.exe", "github.com", "http://a.com"):
        aegis._do_open_url(Entry(title="x", url=url), None)
    assert opened == ["https://C:/x.exe", "https://server\\share\\x.exe", "https://github.com",
                      "http://a.com"]


def test_offer_save_cancel_keeps_old_password(aegis, qapp):
    from aegis.vault.store import Entry
    aegis.vault.create("long-master-password")
    entry = Entry(title="GitHub", username="me", password="old", url="https://github.com")
    aegis.vault.put(entry)
    aegis.offer_save("https://github.com/login", "me", "new")
    aegis.toast._on_click()
    assert aegis.panel.mode == "edit" and aegis.panel.editor.password.text() == "new"
    aegis.panel.editor.cancelled.emit()
    assert aegis.vault.get(entry.id).password == "old"


def test_browser_export_imports_and_deletes_only_its_file(aegis, qapp, tmp_path, monkeypatch):
    from aegis.vault import browsers, watch
    aegis.vault.create("long-master-password")
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    keep = downloads / "report.csv"
    keep.write_text("a,b\n1,2\n")
    monkeypatch.setattr("aegis.core.winapi.export_folders", lambda: [str(downloads)])
    monkeypatch.setattr("aegis.core.winapi.shell_open", lambda *a, **k: True)
    browser = browsers.Browser("chrome", "Chrome", str(tmp_path), "chrome.exe", "chrome://x")
    aegis.export_from_browser(browser)

    unrelated = downloads / "other.csv"          # новый, но не выгрузка паролей
    unrelated.write_text("city,population\nX,1\n")
    export = downloads / "Chrome Passwords.csv"
    export.write_text("name,url,username,password\nGitHub,https://github.com,me,pw\n")
    aegis._poll_export()
    assert export.exists()                       # первый опрос — ждём, что дописан
    aegis._poll_export()

    assert [e.title for e in aegis.vault.entries] == ["GitHub"]
    assert not export.exists()
    assert keep.exists() and unrelated.exists()
    assert aegis._export is None
    assert watch.snapshot(str(downloads)) == {"report.csv", "other.csv"}
