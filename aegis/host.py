"""
Посредник native messaging: браузер запускает его, расширение говорит с ним.

Браузер стартует этот процесс сам (Aegis.exe с адресом расширения в
аргументах) и общается с ним через stdin/stdout: 4 байта длины + JSON. Сам
посредник ничего не знает и не хранит — он только перекладывает сообщения в
канал работающего Aegis (\\\\.\\pipe\\Aegis-IPC) и ответы обратно. Канал открыт
только текущему пользователю Windows (QLocalServer.UserAccessOption).

Без Qt и без остальной программы: посредник живёт столько же, сколько
браузер, и не должен ни есть память, ни долго стартовать.

Aegis не запущен — посредник запускает его и ждёт канала несколько секунд.
"""

import ctypes
import json
import struct
import subprocess
import sys
import time
from ctypes import wintypes

from .core.constants import FIREFOX_EXTENSION_ID, IPC_NAME

PIPE = r"\\.\pipe\%s" % IPC_NAME
START_WAIT_S = 8.0
STD_INPUT_HANDLE = -10
STD_OUTPUT_HANDLE = -11

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.GetStdHandle.restype = wintypes.HANDLE
_kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]


class _Std:
    """stdin/stdout через хэндлы Windows: у exe без консоли sys.stdin — None,
    а хэндлы, которые передал браузер, при этом есть."""

    def __init__(self):
        self.inp = _kernel32.GetStdHandle(STD_INPUT_HANDLE)
        self.out = _kernel32.GetStdHandle(STD_OUTPUT_HANDLE)

    def read_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = ctypes.create_string_buffer(n - len(buf))
            got = wintypes.DWORD()
            if not _kernel32.ReadFile(self.inp, chunk, n - len(buf), ctypes.byref(got), None) \
                    or got.value == 0:
                return None
            buf += chunk.raw[:got.value]
        return bytes(buf)

    def write(self, data):
        pos = 0
        while pos < len(data):
            part = data[pos:]
            done = wintypes.DWORD()
            if not _kernel32.WriteFile(self.out, part, len(part), ctypes.byref(done), None):
                return False
            pos += done.value
        return True


def is_host_launch(argv):
    """Этот запуск — браузер зовёт посредника, а не человек запускает Aegis.
    Chrome передаёт адрес расширения, Firefox — путь к манифесту и id."""
    if "--native-host" in argv:
        return True
    return any(a.startswith("chrome-extension://") for a in argv[1:]) or (
        len(argv) > 2 and argv[1].lower().endswith(".json") and argv[2] == FIREFOX_EXTENSION_ID)


def read_message(std):
    head = std.read_exact(4)
    if head is None:
        return None
    (size,) = struct.unpack("<I", head)
    body = std.read_exact(size)
    if body is None:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(std, message):
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    return std.write(struct.pack("<I", len(body)) + body)


def _launch_aegis():
    """Запустить сам Aegis (в трей) — только у собранного exe; в разработке
    программу запускают руками."""
    if not getattr(sys, "frozen", False):
        return False
    try:
        subprocess.Popen([sys.executable], close_fds=True,
                         creationflags=0x00000008 | 0x00000200)   # DETACHED | NEW_GROUP
        return True
    except OSError:
        return False


def _open_pipe():
    try:
        return open(PIPE, "r+b", buffering=0)
    except OSError:
        return None


def connect():
    pipe = _open_pipe()
    if pipe is not None or not _launch_aegis():
        return pipe
    end = time.monotonic() + START_WAIT_S
    while time.monotonic() < end:
        time.sleep(0.25)
        pipe = _open_pipe()
        if pipe is not None:
            return pipe
    return None


def main():
    std = _Std()
    pipe = connect()
    if pipe is None:
        # Ответить на первое сообщение, чтобы расширение показало причину.
        message = read_message(std)
        write_message(std, {"type": "error", "error": "not_running",
                            "rid": (message or {}).get("rid")})
        return 1
    pipe.write(b"bridge\n")
    # Строго «запрос — ответ»: у синхронного хэндла канала чтение и запись не
    # идут одновременно (Windows ставит их в очередь), поэтому ответ ждём,
    # прежде чем читать следующее сообщение браузера. На каждое сообщение
    # Aegis отвечает ровно одной строкой.
    replies = _Lines(pipe)
    while True:
        message = read_message(std)
        if message is None:
            return 0                 # браузер закрыл порт
        try:
            pipe.write(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
            line = replies.next()
        except OSError:
            line = None
        if line is None:
            return 0                 # Aegis закрылся — браузер переподключится сам
        try:
            write_message(std, json.loads(line.decode("utf-8")))
        except ValueError:
            pass


class _Lines:
    def __init__(self, pipe):
        self.pipe = pipe
        self.buf = b""

    def next(self):
        while b"\n" not in self.buf:
            chunk = self.pipe.read(65536)
            if not chunk:
                return None
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line


if __name__ == "__main__":
    sys.exit(main())
