"""
Поиск записей и подбор под окно, из которого вызвали строку.

Контекст — то, что было на переднем плане до строки: заголовок окна, имя exe
и адрес страницы, если это браузер (aegis/core/context.py). Запись подходит
окну, если совпал сайт (по домену: login.github.com подходит записи
github.com) или в заголовке окна есть её «окно» — для программ без адреса.

Пустой запрос: сначала подходящие окну, потом избранное, потом недавние.
С запросом — одна общая выдача, подходящие окну чуть выше.
"""

from dataclasses import dataclass, field
from urllib.parse import urlparse

from . import matcher

# Вторые уровни, под которыми регистрируют домены: example.co.uk, site.com.ru.
_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "ac", "edu", "ltd", "plc", "msk",
                 "spb", "in", "or", "ne", "go"}
RECENT_LIMIT = 8
CONTEXT_BOOST = 25.0


@dataclass
class Context:
    title: str = ""
    process: str = ""        # имя exe в нижнем регистре: chrome.exe
    url: str = ""
    hwnd: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def host(self):
        return host_of(self.url)


def host_of(url):
    url = (url or "").strip()
    if not url:
        return ""
    if "//" not in url:
        url = "//" + url
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def site_of(host):
    """Регистрируемый домен: accounts.google.com -> google.com."""
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    if len(parts[-1]) == 2 and parts[-2] in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def matches_context(entry, context):
    if context is None:
        return False
    host = context.host
    if host and entry.url:
        entry_host = host_of(entry.url)
        if entry_host and site_of(entry_host) == site_of(host):
            return True
    title = context.title.lower()
    if title and entry.window and entry.window.lower() in title:
        return True
    # Запись без адреса и без «окна»: подходит, если её название есть в
    # заголовке (как в KeePass). Короткие названия дают ложные совпадения.
    if title and not entry.url and not entry.window and len(entry.title) >= 4:
        return entry.title.lower() in title
    return False


def _score(query, alt, entry):
    best = matcher.best_score(query, alt, entry.title) if entry.title else 0.0
    host = host_of(entry.url)
    if host:
        best = max(best, matcher.best_score(query, alt, host) * 0.9)
    if entry.username:
        best = max(best, matcher.best_score(query, alt, entry.username) * 0.8)
    return best


def _recent_key(entry):
    return (entry.used, entry.modified)


def search(entries, query, context=None):
    """[(ключ секции, [Entry])] — секции переводятся в интерфейсе."""
    query = query.strip().lower()
    if not query:
        fitting = [e for e in entries if matches_context(e, context)]
        fitting.sort(key=_recent_key, reverse=True)
        taken = {e.id for e in fitting}
        favorites = sorted((e for e in entries if e.favorite and e.id not in taken),
                           key=lambda e: e.title.lower())
        taken |= {e.id for e in favorites}
        rest = [e for e in entries if e.id not in taken]
        recent = sorted((e for e in rest if e.used), key=_recent_key, reverse=True)
        recent = recent[:RECENT_LIMIT]
        taken |= {e.id for e in recent}
        others = sorted((e for e in rest if e.id not in taken), key=lambda e: e.title.lower())
        return [("context", fitting), ("favorites", favorites), ("recent", recent),
                ("all", others)]

    alt = matcher.other_layout(query)
    scored = []
    for entry in entries:
        s = _score(query, alt, entry)
        if s <= 0:
            continue
        if matches_context(entry, context):
            s += CONTEXT_BOOST
        if entry.favorite:
            s += 2
        scored.append((s, entry.used, entry))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [("results", [e for _, _, e in scored])]
