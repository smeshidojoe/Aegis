"""
Буфер обмена для паролей.

Скопированное помечается для Windows как «не сохранять»: оно не попадает в
журнал буфера (Win+V) и в облачную синхронизацию буфера. Через заданное
время буфер очищается — но только если в нём всё ещё наш текст: затирать
то, что человек скопировал после, нельзя.
"""

from PySide6.QtCore import QMimeData, QObject, QTimer
from PySide6.QtGui import QGuiApplication

_WIN = 'application/x-qt-windows-mime;value="%s"'
_NO_HISTORY = (
    (_WIN % "ExcludeClipboardContentFromMonitorProcessing", b"\x00"),
    (_WIN % "CanIncludeInClipboardHistory", b"\x00\x00\x00\x00"),
    (_WIN % "CanUploadToCloudClipboard", b"\x00\x00\x00\x00"),
)


class SecureClipboard(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = None
        self._timer = QTimer(self, singleShot=True)
        self._timer.timeout.connect(self.clear)

    def copy(self, text, clear_after_s=20, secret=True):
        data = QMimeData()
        data.setText(text)
        if secret:
            for fmt, value in _NO_HISTORY:
                data.setData(fmt, value)
        QGuiApplication.clipboard().setMimeData(data)
        if secret and clear_after_s > 0:
            self._text = text
            self._timer.start(int(clear_after_s * 1000))
        else:
            self._text = None
            self._timer.stop()

    def clear(self):
        """Убрать наш текст, если он ещё в буфере (по таймеру, при блокировке и выходе)."""
        self._timer.stop()
        text, self._text = self._text, None
        if text is None:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard.text() == text:
            clipboard.clear()
