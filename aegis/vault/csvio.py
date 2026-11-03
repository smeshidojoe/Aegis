"""
Импорт и экспорт CSV.

Импорт понимает выгрузки Chrome/Edge/Opera, Firefox, Bitwarden, KeePass и
1Password: столбцы ищутся по названию, а не по порядку. Экспорт — тот же
формат, что у Chrome: его понимают почти все менеджеры паролей.
"""

import csv
import io
from urllib.parse import urlparse

from .store import Entry

_COLUMNS = {
    "title": ("name", "title", "account", "item name"),
    "url": ("url", "login_uri", "website", "web site", "origin", "login url"),
    "username": ("username", "login_username", "login", "user name", "user", "email",
                 "e-mail"),
    "password": ("password", "login_password", "pass"),
    "notes": ("note", "notes", "extra", "comments", "comment"),
    "totp": ("totp", "login_totp", "otpauth", "one-time password"),
}

EXPORT_FIELDS = ("name", "url", "username", "password", "note", "totp")


def _pick(header):
    """{поле Entry: номер столбца}."""
    lower = [h.strip().lower() for h in header]
    out = {}
    for field, names in _COLUMNS.items():
        for name in names:
            if name in lower:
                out[field] = lower.index(name)
                break
    return out


def title_from_url(url):
    host = urlparse(url if "//" in url else "//" + url).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host or url


def parse(text):
    """Записи из текста CSV. ValueError — не нашлось ни столбца пароля."""
    text = text.lstrip("﻿")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    columns = _pick(rows[0])
    if "password" not in columns:
        raise ValueError("no password column")
    entries = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue

        def cell(field):
            i = columns.get(field)
            return row[i].strip() if i is not None and i < len(row) else ""

        entry = Entry(title=cell("title"), url=cell("url"), username=cell("username"),
                      password=cell("password"), notes=cell("notes"), totp=cell("totp"))
        if not entry.title:
            entry.title = title_from_url(entry.url) if entry.url else entry.username
        if entry.password or entry.username:
            entries.append(entry)
    return entries


def is_duplicate(entry, existing):
    return any(e.username == entry.username and e.password == entry.password
               and title_from_url(e.url) == title_from_url(entry.url) for e in existing)


def dump(entries):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_FIELDS)
    for e in entries:
        writer.writerow([e.title, e.url, e.username, e.password, e.notes, e.totp])
    return out.getvalue()
