"""
Автонабор: логин, Tab, пароль, Enter — в окно, из которого позвали строку.

Набор идёт событиями Unicode (SendInput), а не через буфер обмена: пароль не
оседает в истории буфера и не зависит от раскладки.

Последовательность задаётся строкой с метками (как в KeePass):

    {USERNAME} {PASSWORD} {TOTP} {URL} {TAB} {ENTER} {DELAY 300}

Остальной текст печатается как есть. Пустая — DEFAULT_SEQUENCE, а у записи без
логина — только пароль и Enter.

Главное правило — не напечатать пароль не туда. Перед каждым шагом проверяем,
что на переднем плане всё ещё то самое окно; переключился человек куда-то
посередине — набор обрывается.
"""

import re

from PySide6.QtCore import QObject, QTimer, Signal

from ..vault import totp
from . import winapi

DEFAULT_SEQUENCE = "{USERNAME}{TAB}{PASSWORD}{ENTER}"
PASSWORD_ONLY = "{PASSWORD}{ENTER}"

# Окну нужно время, чтобы получить фокус обратно, а человеку — отпустить
# клавиши: Ctrl, зажатый с прошлого сочетания, превратил бы буквы в команды.
FOCUS_WAIT_MS = 120
STEP_MS = 25
MODIFIER_WAIT_MS = 1500

_TOKEN = re.compile(r"\{([A-Z]+)(?:\s+(\d+))?\}", re.IGNORECASE)


def parse(sequence):
    """[(вид, значение)]: ("field", "username"), ("key", VK), ("delay", мс), ("text", "...")."""
    steps, pos = [], 0
    for m in _TOKEN.finditer(sequence):
        if m.start() > pos:
            steps.append(("text", sequence[pos:m.start()]))
        name, arg = m.group(1).upper(), m.group(2)
        if name in ("USERNAME", "PASSWORD", "TOTP", "URL", "TITLE"):
            steps.append(("field", name.lower()))
        elif name == "TAB":
            steps.append(("key", winapi.VK_TAB))
        elif name == "ENTER":
            steps.append(("key", winapi.VK_RETURN))
        elif name == "DELAY":
            steps.append(("delay", min(int(arg or 0), 10_000)))
        else:
            steps.append(("text", m.group(0)))       # неизвестная метка — как текст
        pos = m.end()
    if pos < len(sequence):
        steps.append(("text", sequence[pos:]))
    return steps


def sequence_for(entry):
    if entry.sequence.strip():
        return entry.sequence
    return DEFAULT_SEQUENCE if entry.username else PASSWORD_ONLY


def field_value(entry, name):
    if name == "totp":
        try:
            return totp.code(entry.totp) if entry.totp else ""
        except ValueError:
            return ""
    return getattr(entry, name, "") or ""


class AutoTyper(QObject):
    """finished(True) — всё набрано; finished(False) — оборвали."""

    finished = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps = []
        self._target = 0
        self._entry = None
        self._waited = 0
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self._next)

    def busy(self):
        return bool(self._steps) or self._timer.isActive()

    def run(self, entry, hwnd, sequence=None):
        self._entry = entry
        self._target = winapi.root_window(hwnd)
        self._steps = parse(sequence or sequence_for(entry))
        self._waited = 0
        winapi.force_foreground(self._target)
        self._timer.start(FOCUS_WAIT_MS)

    def cancel(self):
        if self.busy():
            self._timer.stop()
            self._steps = []
            self._entry = None
            self.finished.emit(False)

    def _next(self):
        if winapi.modifiers_down() and self._waited < MODIFIER_WAIT_MS:
            self._waited += STEP_MS
            self._timer.start(STEP_MS)
            return
        if not self._steps:
            self._entry = None
            self.finished.emit(True)
            return
        if winapi.root_window(winapi.foreground_window()) != self._target:
            self.cancel()
            return
        kind, value = self._steps.pop(0)
        delay = STEP_MS
        if kind == "text":
            winapi.send_text(value)
        elif kind == "field":
            winapi.send_text(field_value(self._entry, value))
        elif kind == "key":
            winapi.send_key(value)
        elif kind == "delay":
            delay = value
        self._timer.start(delay)
