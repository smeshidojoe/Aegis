"""
Когда запирать базу: простой, блокировка Windows (Win+L), сон.

Блокировку и сон Windows сообщает окну, подписанному через
WTSRegisterSessionNotification, — подписываем строку; сообщения ловим общим
nativeEventFilter, как и хоткей. Простой меряем по GetLastInputInfo: время
последнего ввода во всей системе, а не только в Aegis.
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal

from . import winapi

WM_WTSSESSION_CHANGE = 0x02B1
WM_POWERBROADCAST = 0x0218
WTS_SESSION_LOCK = 0x7
PBT_APMSUSPEND = 0x4
NOTIFY_FOR_THIS_SESSION = 0
IDLE_CHECK_MS = 15_000


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt_x", wintypes.LONG), ("pt_y", wintypes.LONG)]


class SessionWatcher(QObject, QAbstractNativeEventFilter):
    """lock_requested(причина): 'session' | 'suspend' | 'idle'."""

    lock_requested = Signal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self.idle_minutes = 0           # 0 — по простою не запирать
        self._timer = QTimer(self, interval=IDLE_CHECK_MS)
        self._timer.timeout.connect(self._check_idle)

    def install(self, app, hwnd):
        app.installNativeEventFilter(self)
        self.watch(hwnd)
        self._timer.start()

    def watch(self, hwnd):
        """Подписать окно на блокировку Windows — и заново, если его пересоздали."""
        try:
            ctypes.windll.wtsapi32.WTSRegisterSessionNotification(
                wintypes.HWND(int(hwnd)), NOTIFY_FOR_THIS_SESSION)
        except Exception:
            pass

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        msg = _MSG.from_address(int(message))
        if msg.message == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_LOCK:
            self.lock_requested.emit("session")
        elif msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMSUSPEND:
            self.lock_requested.emit("suspend")
        return False, 0

    def _check_idle(self):
        if self.idle_minutes and winapi.idle_seconds() >= self.idle_minutes * 60:
            self.lock_requested.emit("idle")
