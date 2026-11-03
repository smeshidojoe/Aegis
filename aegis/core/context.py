"""
Что было на экране, когда позвали строку: окно, программа и адрес страницы.

Заголовок окна и exe снимаются мгновенно, до показа строки, — потом передний
план уже наш. Адрес страницы у браузера в заголовок не попадает, его читаем
из адресной строки через UI Automation. Это медленнее (до пары сотен мс у
тяжёлого окна), поэтому в своём потоке: строка показывается сразу, а
подходящие сайту записи поднимаются наверх, когда адрес придёт.

Если стоит расширение (aegis/bridge.py), адрес активной вкладки оно сообщает
само, точно и без UI Automation, — тогда этот поток не нужен.
"""

import os
import threading

from PySide6.QtCore import QObject, Signal

from ..vault.search import Context
from . import logbook, winapi

BROWSERS = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
    "browser.exe",          # Яндекс Браузер
    "chromium.exe", "arc.exe", "librewolf.exe", "waterfox.exe", "floorp.exe", "zen.exe",
    "thorium.exe",
}

_UIA_CLSID = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
_UIA_ControlTypePropertyId = 30003
_UIA_EditControlTypeId = 50004
_UIA_ValueValuePropertyId = 30045
_TreeScope_Descendants = 4


# Рабочий стол и панель задач — не окно для набора: Enter там открыл бы
# выделенный файл. Отсюда строку зовут как из трея.
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def capture():
    """Окно на переднем плане прямо сейчас — без адреса страницы. None — его нет
    или это рабочий стол."""
    hwnd = winapi.root_window(winapi.foreground_window())
    if not hwnd or winapi.window_class(hwnd) in SHELL_CLASSES:
        return None
    path = winapi.process_path(winapi.window_pid(hwnd))
    return Context(title=winapi.window_title(hwnd),
                   process=os.path.basename(path).lower(), hwnd=hwnd)


def is_browser(context):
    return context is not None and context.process in BROWSERS


def _automation():
    import comtypes.client
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as uia
    return comtypes.client.CreateObject(_UIA_CLSID, interface=uia.IUIAutomation)


def read_address(hwnd):
    """Текст адресной строки браузера или "" — в своём потоке."""
    import comtypes
    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        own = True
    except OSError:
        own = False             # поток уже в другом апартаменте — так и работаем
    try:
        automation = _automation()
        window = automation.ElementFromHandle(hwnd)
        condition = automation.CreatePropertyCondition(_UIA_ControlTypePropertyId,
                                                       _UIA_EditControlTypeId)
        # Первое поле ввода в окне браузера — адресная строка: у Chromium и
        # Firefox она стоит в дереве раньше содержимого страницы.
        edit = window.FindFirst(_TreeScope_Descendants, condition)
        if not edit:
            return ""
        value = edit.GetCurrentPropertyValue(_UIA_ValueValuePropertyId)
        return str(value or "").strip()
    finally:
        if own:
            comtypes.CoUninitialize()


class AddressReader(QObject):
    """Адрес из окна браузера в фоне; ready(hwnd, адрес)."""

    ready = Signal(int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False

    def request(self, hwnd):
        if self._busy or not hwnd:
            return
        self._busy = True
        threading.Thread(target=self._run, args=(hwnd,), name="aegis-address",
                         daemon=True).start()

    def _run(self, hwnd):
        address = ""
        try:
            address = read_address(hwnd)
        except Exception:
            logbook.exc("адрес браузера")
        self._busy = False
        self.ready.emit(hwnd, address)
