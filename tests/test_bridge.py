import io
import json
import struct

from aegis import host
from aegis.bridge import Bridge
from aegis.core import autotype, winapi
from aegis.core.config import Config
from aegis.vault.store import Entry


class _Vault:
    def __init__(self, entries, unlocked=True):
        self.entries = entries
        self.unlocked = unlocked
        self.touched = []

    def is_unlocked(self):
        return self.unlocked

    def get(self, entry_id):
        return next((e for e in self.entries if e.id == entry_id), None)

    def touch(self, entry):
        self.touched.append(entry.id)


class _App:
    def __init__(self, tmp_path, vault):
        from PySide6.QtCore import QObject
        self.qobject = QObject()
        self.config = Config(str(tmp_path / "config.json"))
        self.vault = vault
        self.asked = []
        self.saved = []

    def ask_pairing(self, name, answer):
        self.asked.append(name)
        answer(True)

    def offer_save(self, url, username, password):
        self.saved.append((url, username, password))


class _Conn:
    def __init__(self):
        self.replies = []
        self.browser = ""

    def reply(self, request, message):
        self.replies.append(dict(message, rid=request.get("rid")))


def _bridge(tmp_path, entries, unlocked=True):
    app = _App(tmp_path, _Vault(entries, unlocked))
    bridge = Bridge.__new__(Bridge)
    Bridge.__init__(bridge, app.qobject)
    bridge.app = app
    return bridge, app


def _paired(bridge):
    conn = _Conn()
    bridge.handle(conn, {"type": "pair", "browser": "Chrome", "rid": 1})
    reply = conn.replies[-1]
    assert reply["type"] == "paired"
    return {"pair_id": reply["pair_id"], "key": reply["key"]}


def test_requests_need_pairing(tmp_path):
    bridge, _app = _bridge(tmp_path, [])
    conn = _Conn()
    bridge.handle(conn, {"type": "query", "url": "https://github.com", "rid": 7})
    assert conn.replies == [{"type": "error", "error": "not_paired", "rid": 7}]
    bridge.handle(conn, {"type": "query", "pair_id": "x", "key": "guess", "rid": 8})
    assert conn.replies[-1]["error"] == "not_paired"


def test_query_and_fill_only_for_matching_site(tmp_path):
    github = Entry(title="GitHub", username="me", password="pw", url="github.com")
    other = Entry(title="Bank", username="me", password="money", url="bank.example")
    bridge, app = _bridge(tmp_path, [github, other])
    auth = _paired(bridge)
    conn = _Conn()
    bridge.handle(conn, dict(auth, type="query", url="https://github.com/login", rid=2))
    reply = conn.replies[-1]
    assert [e["id"] for e in reply["entries"]] == [github.id]
    assert "password" not in json.dumps(reply)
    # Пароль чужого сайта со страницы github.com не выдаётся.
    bridge.handle(conn, dict(auth, type="fill", url="https://github.com", entry_id=other.id,
                             rid=3))
    assert conn.replies[-1]["error"] == "no_entry"
    bridge.handle(conn, dict(auth, type="fill", url="https://github.com", entry_id=github.id,
                             rid=4))
    assert conn.replies[-1]["password"] == "pw"
    assert app.vault.touched == [github.id]


def test_locked_vault(tmp_path):
    bridge, _app = _bridge(tmp_path, [Entry(title="A", url="a.com")], unlocked=False)
    auth = _paired(bridge)
    conn = _Conn()
    bridge.handle(conn, dict(auth, type="query", url="https://a.com", rid=5))
    assert conn.replies[-1]["locked"] is True
    assert conn.replies[-1]["entries"] == []


def test_unpair_revokes(tmp_path):
    bridge, _app = _bridge(tmp_path, [])
    auth = _paired(bridge)
    bridge.unpair(auth["pair_id"])
    conn = _Conn()
    bridge.handle(conn, dict(auth, type="hello", rid=6))
    assert conn.replies[-1]["error"] == "not_paired"


def test_known_pair_is_not_offered(tmp_path):
    entry = Entry(title="GitHub", username="me", password="pw", url="github.com")
    bridge, _app = _bridge(tmp_path, [entry])
    auth = _paired(bridge)
    conn = _Conn()
    bridge.handle(conn, dict(auth, type="query", url="https://github.com", username="me",
                             password="pw", rid=9))
    assert conn.replies[-1]["known"] is True


def test_tab_report_is_cleared_for_non_web_pages(tmp_path):
    bridge, _app = _bridge(tmp_path, [])
    auth = _paired(bridge)
    conn = _Conn()
    bridge.handle(conn, dict(auth, type="tab", url="https://github.com", title="GitHub",
                             process="Chrome.exe", rid=10))
    assert bridge.tab_url["chrome.exe"] == ("https://github.com", "GitHub")
    bridge.handle(conn, dict(auth, type="tab", url="", title="", process="chrome.exe", rid=11))
    assert "chrome.exe" not in bridge.tab_url


def test_pairing_timeout_withdraws_question(tmp_path, qapp, monkeypatch):
    import aegis.bridge as bridge_mod
    from conftest import pump
    monkeypatch.setattr(bridge_mod, "PAIR_TIMEOUT_MS", 10)
    bridge, app = _bridge(tmp_path, [])
    withdrawn = []
    app.ask_pairing = lambda name, answer: None          # человек не отвечает
    app.withdraw_pairing = withdrawn.append
    conn = _Conn()
    bridge.handle(conn, {"type": "pair", "browser": "Chrome", "rid": 1})
    assert pump(qapp, lambda: conn.replies)
    assert conn.replies[-1]["type"] == "denied" and len(withdrawn) == 1


# --- посредник ---------------------------------------------------------------- #

class _FakeStd:
    def __init__(self, data):
        self.inp = io.BytesIO(data)
        self.out = io.BytesIO()

    def read_exact(self, n):
        data = self.inp.read(n)
        return data if len(data) == n else None

    def write(self, data):
        self.out.write(data)
        return True


def test_host_launches_aegis_only_for_user_actions(monkeypatch):
    launched = []
    monkeypatch.setattr(host, "_open_pipe", lambda: None)
    monkeypatch.setattr(host, "_launch_aegis", lambda: launched.append(1) or False)
    for kind, expected in (("tab", 0), ("query", 0), ("ping", 1)):
        launched.clear()
        body = json.dumps({"type": kind, "rid": 3}).encode()
        std = _FakeStd(struct.pack("<I", len(body)) + body)
        monkeypatch.setattr(host, "_Std", lambda: std)
        assert host.main() == 1
        assert len(launched) == expected, kind
        reply = json.loads(std.out.getvalue()[4:])
        assert reply == {"type": "error", "error": "not_running", "rid": 3}


def test_native_message_framing():
    body = json.dumps({"type": "ping", "rid": 1}).encode()
    std = _FakeStd(struct.pack("<I", len(body)) + body)
    assert host.read_message(std) == {"type": "ping", "rid": 1}
    assert host.read_message(std) is None
    host.write_message(std, {"type": "pong", "текст": "да"})
    raw = std.out.getvalue()
    (size,) = struct.unpack("<I", raw[:4])
    assert json.loads(raw[4:4 + size].decode()) == {"type": "pong", "текст": "да"}


def test_host_launch_detection():
    assert host.is_host_launch(["Aegis.exe", "chrome-extension://abc/", "--parent-window=0"])
    assert host.is_host_launch(["Aegis.exe", r"C:\x\firefox.json", "aegis@smeshidojoe"])
    assert host.is_host_launch(["python", "main.py", "--native-host"])
    assert not host.is_host_launch(["Aegis.exe"])
    assert not host.is_host_launch(["Aegis.exe", "--show"])


# --- автонабор ---------------------------------------------------------------- #

def test_autotype_parse():
    steps = autotype.parse("{USERNAME}{TAB}{PASSWORD}{DELAY 200}x{ENTER}{WHAT}")
    assert steps == [("field", "username"), ("key", winapi.VK_TAB), ("field", "password"),
                     ("delay", 200), ("text", "x"), ("key", winapi.VK_RETURN),
                     ("text", "{WHAT}")]


def test_autotype_default_sequence():
    assert autotype.sequence_for(Entry(username="me")) == autotype.DEFAULT_SEQUENCE
    assert autotype.sequence_for(Entry()) == autotype.PASSWORD_ONLY
    assert autotype.sequence_for(Entry(sequence="{PASSWORD}")) == "{PASSWORD}"
