"""
Ждём CSV, который выгрузит браузер, и после импорта удаляем ровно его.

Удаляется только файл, который одновременно:
  * появился в папке ПОСЛЕ начала ожидания (его имени не было в снимке папки);
  * лежит прямо в этой папке, обычный файл, не ярлык и не ссылка;
  * оканчивается на .csv и разобрался как выгрузка паролей (есть столбец пароля);
  * не менялся между чтением и удалением (тот же размер и время изменения).
Никаких масок и обхода папки при удалении — только этот один путь. Перед
удалением содержимое затирается нулями: в нём пароли открытым текстом.
"""

import os
import time


def snapshot(folder):
    """Имена файлов в папке сейчас — их не трогаем никогда."""
    try:
        return {os.path.normcase(n) for n in os.listdir(folder)}
    except OSError:
        return set()


def new_csv_files(folder, before, since):
    """Новые .csv в folder: не было в снимке before и изменены после since."""
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        if os.path.normcase(name) in before or not name.lower().endswith(".csv"):
            continue
        path = os.path.join(folder, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if os.path.islink(path) or not os.path.isfile(path) or st.st_mtime < since - 2:
            continue
        out.append(path)
    return out


def fingerprint(path):
    st = os.lstat(path)
    return st.st_size, st.st_mtime_ns


def safe_delete(path, folder, expected):
    """Затереть и удалить path, только если он всё тот же файл в folder.
    expected — fingerprint() на момент чтения. True — удалён."""
    try:
        if os.path.normcase(os.path.dirname(os.path.abspath(path))) != \
                os.path.normcase(os.path.abspath(folder)):
            return False
        if os.path.islink(path) or not os.path.isfile(path) or not path.lower().endswith(".csv"):
            return False
        if fingerprint(path) != expected:
            return False
        size = expected[0]
        with open(path, "r+b") as f:
            f.write(b"\x00" * size)
            f.flush()
            os.fsync(f.fileno())
        os.remove(path)
        return True
    except OSError:
        return False


class Waiter:
    """Опрос папок: poll() возвращает новые CSV, ещё не отданные раньше."""

    def __init__(self, folders):
        self.since = time.time()
        self.folders = [f for f in folders if f and os.path.isdir(f)]
        self.before = {f: snapshot(f) for f in self.folders}
        self.seen = set()

    def poll(self):
        out = []
        for folder in self.folders:
            for path in new_csv_files(folder, self.before[folder], self.since):
                key = os.path.normcase(path)
                if key not in self.seen:
                    self.seen.add(key)
                    out.append((folder, path))
        return out
