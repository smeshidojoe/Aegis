"""
Тонкие обёртки над WinAPI: фокус окна, запуск через оболочку, окно на
переднем плане, ввод клавиш, простой пользователя.

Всё на ctypes: pywin32 ради десятка вызовов тянуть в сборку незачем.
"""

import ctypes
import os
import subprocess
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32
# Отдельная загрузка с use_last_error: иначе код ошибки ShellExecuteEx затрёт
# сам ctypes, и отказ в UAC не отличить от настоящей ошибки.
_shell32_err = ctypes.WinDLL("shell32", use_last_error=True)

SW_SHOWNORMAL = 1
ASFW_ANY = -1
SPI_GETCLIENTAREAANIMATION = 0x1042
SEE_MASK_NOASYNC = 0x00000100
ERROR_CANCELLED = 1223
QS_KEY = 0x0001


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong),
        ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
        ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


_shell32_err.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
_shell32_err.ShellExecuteExW.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.GetForegroundWindow.restype = wintypes.HWND


def force_foreground(hwnd):
    """
    Вывести окно на передний план и отдать ему клавиатуру.

    Обычно хватает SetForegroundWindow: процесс, получивший WM_HOTKEY, имеет
    право забрать фокус. Если Windows всё же отказала (бывает после клика в
    трей), на время подцепляемся к очереди ввода окна, которое сейчас в фокусе,
    — тогда запрет не действует.
    """
    hwnd = wintypes.HWND(int(hwnd))
    if user32.SetForegroundWindow(hwnd) and user32.GetForegroundWindow() == hwnd.value:
        return True
    foreground = user32.GetForegroundWindow()
    theirs = user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
    ours = kernel32.GetCurrentThreadId()
    attached = bool(theirs and theirs != ours
                    and user32.AttachThreadInput(ours, theirs, True))
    try:
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        if attached:
            user32.AttachThreadInput(ours, theirs, False)


def allow_foreground_for_launched():
    """
    Разрешаем запускаемой программе забрать фокус.

    Пока строка открыта, передний план наш. Без разрешения только что
    запущенное окно Windows может оставить под другим — ради мигающей кнопки на
    панели задач никто Aegis не открывает.
    """
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass


def shell_open(target, params=None, verb=None, cwd=None):
    """
    ShellExecuteEx. verb="runas" — от администратора.
    True — запуск принят, False — ошибка, None — отказ в окне UAC.

    Вызывается из фонового потока (см. launcher), поэтому SEE_MASK_NOASYNC:
    поток завершится сразу после вызова, и запуск должен закончиться до этого.
    """
    allow_foreground_for_launched()
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOASYNC
    info.lpVerb = verb
    info.lpFile = target
    info.lpParameters = params
    info.lpDirectory = cwd
    info.nShow = SW_SHOWNORMAL
    if _shell32_err.ShellExecuteExW(ctypes.byref(info)):
        return True
    return None if ctypes.get_last_error() == ERROR_CANCELLED else False


def reveal(path):
    """Открыть папку в проводнике с выделенным файлом."""
    allow_foreground_for_launched()
    # Строкой, а не списком: explorer разбирает /select,"путь" сам и не
    # понимает кавычки, которые расставил бы list2cmdline.
    try:
        subprocess.Popen('explorer.exe /select,"%s"' % os.path.normpath(path))
        return True
    except OSError:
        return False


def keys_pending():
    """В очереди главного потока ждут нажатия клавиш — человек ещё печатает."""
    try:
        return bool((user32.GetQueueStatus(QS_KEY) >> 16) & QS_KEY)
    except Exception:
        return False


def animations_enabled():
    """Флажок «Анимация элементов управления» в параметрах быстродействия."""
    value = wintypes.BOOL(True)
    try:
        user32.SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION, 0,
                                     ctypes.byref(value), 0)
    except Exception:
        return True
    return bool(value.value)


def set_app_id(app_id):
    """Свой AppUserModelID: иначе уведомления трея подписаны как python.exe."""
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass


# --- окно на переднем плане -------------------------------------------------- #

GA_ROOT = 2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]


def foreground_window():
    return user32.GetForegroundWindow() or 0


def root_window(hwnd):
    """Окно верхнего уровня: фокус бывает у дочернего окна или всплывающего списка."""
    if not hwnd:
        return 0
    return user32.GetAncestor(wintypes.HWND(int(hwnd)), GA_ROOT) or int(hwnd)


def is_window(hwnd):
    return bool(hwnd) and bool(user32.IsWindow(wintypes.HWND(int(hwnd))))


def window_title(hwnd):
    if not hwnd:
        return ""
    handle = wintypes.HWND(int(hwnd))
    length = user32.GetWindowTextLengthW(handle)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(handle, buf, length + 1)
    return buf.value


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    if hwnd:
        user32.GetClassNameW(wintypes.HWND(int(hwnd)), buf, 256)
    return buf.value


def window_pid(hwnd):
    pid = wintypes.DWORD()
    if hwnd:
        user32.GetWindowThreadProcessId(wintypes.HWND(int(hwnd)), ctypes.byref(pid))
    return pid.value


def process_path(pid):
    if not pid:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


# --- ввод клавиш --------------------------------------------------------------- #

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU = 0x09, 0x0D, 0x10, 0x11, 0x12
VK_LWIN, VK_RWIN = 0x5B, 0x5C
_MODIFIERS = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN,
              0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5)


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _key(vk=0, scan=0, flags=0):
    item = _INPUT()
    item.type = INPUT_KEYBOARD
    item.u.ki = _KEYBDINPUT(vk, scan, flags, 0, 0)
    return item


def _send(items):
    if not items:
        return 0
    array = (_INPUT * len(items))(*items)
    return user32.SendInput(len(items), array, ctypes.sizeof(_INPUT))


def modifiers_down():
    """Зажат ли ещё какой-то модификатор — после хоткея человек мог не отпустить Ctrl."""
    return any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIERS)


def send_key(vk):
    _send([_key(vk), _key(vk, 0, KEYEVENTF_KEYUP)])


def send_text(text):
    """Текст событиями KEYEVENTF_UNICODE — не зависит от раскладки и не трогает буфер."""
    items = []
    for ch in text:
        data = ch.encode("utf-16-le")
        for i in range(0, len(data), 2):          # символы вне BMP — суррогатной парой
            unit = int.from_bytes(data[i:i + 2], "little")
            items += [_key(0, unit, KEYEVENTF_UNICODE),
                      _key(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    for i in range(0, len(items), 200):           # длинный текст — пачками
        _send(items[i:i + 200])


# --- простой ------------------------------------------------------------------- #

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    """Сколько секунд к компьютеру не прикасались (клавиатура, мышь)."""
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return max(0, (kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


# --- папки пользователя --------------------------------------------------------- #

_FOLDERS = {
    "desktop":   "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
}


def known_folder(name):
    """Рабочий стол, документы, загрузки — с учётом того, что их могли перенести."""
    try:
        import uuid
        guid = uuid.UUID(_FOLDERS[name])
        buf = ctypes.c_wchar_p()
        folder_id = (ctypes.c_byte * 16).from_buffer_copy(guid.bytes_le)
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None,
                                        ctypes.byref(buf)) == 0:
            path = buf.value
            ctypes.windll.ole32.CoTaskMemFree(buf)
            if path:
                return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), name.capitalize())


def export_folders():
    """Куда браузер обычно сохраняет выгрузку паролей."""
    return [known_folder(n) for n in ("downloads", "documents", "desktop")]
