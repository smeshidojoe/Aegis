"""
Копии базы.

Копия — тот же зашифрованный файл, поэтому её можно спокойно класть в облачную
папку или на флешку: без мастер-пароля она бесполезна.

Когда: после каждого изменения базы. Правки, идущие подряд (завёл запись,
поправил, добавил ещё), не плодят по копии на каждую: если последней копии
меньше COALESCE_SECONDS, она заменяется свежей. Так в копиях остаётся итог
каждого «сеанса правок», а не сотня почти одинаковых файлов.

Сколько хранить: последние KEEP_RECENT копий всегда; из более старых — самая
новая за каждый день в пределах KEEP_DAYS и за каждый месяц в пределах
KEEP_MONTHS. Остальное удаляется.

Куда: %APPDATA%\\Aegis\\backups и, если выбрана в настройках, вторая папка —
туда пишется то же самое и чистится по тем же правилам.
"""

import os
import shutil
import time

PREFIX = "vault-"
SUFFIX = ".aegis"
STAMP = "%Y-%m-%d_%H-%M-%S"
# Копии «вручную» (кнопка, перед восстановлением, новая вторая папка): правки
# следом их не заменяют — иначе состояние до восстановления пропало бы.
MANUAL = "-keep"

COALESCE_SECONDS = 10 * 60
KEEP_RECENT = 20
KEEP_DAYS = 30
KEEP_MONTHS = 12


def _name(now, manual=False):
    return PREFIX + time.strftime(STAMP, time.localtime(now)) + (MANUAL if manual else "") + SUFFIX


def is_manual(path):
    return path.endswith(MANUAL + SUFFIX)


def _parse(name):
    """Время копии из имени файла или None, если файл не наш."""
    if not (name.startswith(PREFIX) and name.endswith(SUFFIX)):
        return None
    stamp = name[len(PREFIX):-len(SUFFIX)]
    if stamp.endswith(MANUAL):
        stamp = stamp[:-len(MANUAL)]
    try:
        return time.mktime(time.strptime(stamp, STAMP))
    except ValueError:
        return None


def listing(folder):
    """[(время, путь)] от новых к старым."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for name in names:
        stamp = _parse(name)
        if stamp is not None:
            out.append((stamp, os.path.join(folder, name)))
    out.sort(reverse=True)
    return out


def snapshot(vault_path, folder, now=None, coalesce=True):
    """Скопировать базу в folder. Возвращает путь копии или None при ошибке."""
    now = time.time() if now is None else now
    try:
        os.makedirs(folder, exist_ok=True)
        existing = listing(folder)
        target = os.path.join(folder, _name(now, manual=not coalesce))
        if (coalesce and existing and not is_manual(existing[0][1])
                and 0 <= now - existing[0][0] < COALESCE_SECONDS):
            # Заменяем последнюю: новая копия получает новое имя, старая уходит.
            old = existing[0][1]
            _copy(vault_path, target)
            if os.path.normcase(old) != os.path.normcase(target):
                os.remove(old)
        else:
            _copy(vault_path, target)
        prune(folder, now)
        return target
    except OSError:
        return None


def _copy(src, dst):
    tmp = dst + ".tmp"
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def keep_set(stamps, now):
    """Какие из времён копий оставить (по правилам из шапки)."""
    stamps = sorted(stamps, reverse=True)
    keep = set(stamps[:KEEP_RECENT])
    days, months = set(), set()
    for stamp in stamps:
        local = time.localtime(stamp)
        age_days = (now - stamp) / 86400
        day = (local.tm_year, local.tm_yday)
        month = (local.tm_year, local.tm_mon)
        if age_days <= KEEP_DAYS and day not in days:
            days.add(day)
            keep.add(stamp)
        if age_days <= KEEP_MONTHS * 31 and month not in months:
            months.add(month)
            keep.add(stamp)
    return keep


def prune(folder, now=None):
    now = time.time() if now is None else now
    items = listing(folder)
    keep = keep_set([stamp for stamp, _ in items], now)
    for stamp, path in items:
        if stamp not in keep:
            try:
                os.remove(path)
            except OSError:
                pass


class Backups:
    def __init__(self, folder, extra=""):
        self.folder = folder
        self.extra = extra or ""
        self.last_error = ""

    def folders(self):
        return [f for f in (self.folder, self.extra) if f]

    def after_save(self, vault_path):
        self.last_error = ""
        for folder in self.folders():
            if snapshot(vault_path, folder) is None:
                self.last_error = folder

    def make_now(self, vault_path):
        """Кнопка «Сделать копию сейчас» и копия перед восстановлением —
        отдельным файлом, не заменяя последнюю."""
        ok = True
        for folder in self.folders():
            ok = snapshot(vault_path, folder, coalesce=False) is not None and ok
        return ok

    def all(self):
        """Копии из обеих папок без повторов (одно и то же имя — одна копия)."""
        seen, out = set(), []
        for folder in self.folders():
            for stamp, path in listing(folder):
                name = os.path.basename(path)
                if name not in seen:
                    seen.add(name)
                    out.append((stamp, path))
        out.sort(reverse=True)
        return out

    def restore(self, backup_path, vault_path):
        """Текущая база сначала сама уходит в копию — восстановление обратимо."""
        if os.path.isfile(vault_path):
            self.make_now(vault_path)
        _copy(backup_path, vault_path)
