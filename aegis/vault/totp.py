"""Одноразовые коды TOTP (RFC 6238) — как в Google Authenticator."""

import base64
import hashlib
import hmac
import struct
import time
from urllib.parse import parse_qs, unquote, urlparse

_ALGOS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


def parse(value):
    """Секрет base32 или ссылка otpauth://totp/... -> (секрет, цифр, период, алгоритм)."""
    value = (value or "").strip()
    digits, period, algo = 6, 30, "SHA1"
    if value.lower().startswith("otpauth://"):
        query = parse_qs(urlparse(value).query)
        secret = unquote(query.get("secret", [""])[0])
        digits = int(query.get("digits", [6])[0])
        period = int(query.get("period", [30])[0])
        algo = query.get("algorithm", ["SHA1"])[0].upper()
    else:
        secret = value
    secret = secret.replace(" ", "").replace("-", "").upper()
    if not secret:
        raise ValueError("empty secret")
    return secret, digits, period, algo if algo in _ALGOS else "SHA1"


def _key(secret):
    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def code(value, now=None):
    """Текущий код. ValueError — секрет не разобрать."""
    secret, digits, period, algo = parse(value)
    try:
        key = _key(secret)
    except Exception as error:
        raise ValueError("bad base32") from error
    counter = int((time.time() if now is None else now) // period)
    mac = hmac.new(key, struct.pack(">Q", counter), _ALGOS[algo]).digest()
    offset = mac[-1] & 0x0F
    number = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** digits)).zfill(digits)


def seconds_left(value, now=None):
    _secret, _digits, period, _algo = parse(value)
    now = time.time() if now is None else now
    return period - int(now) % period


def valid(value):
    try:
        code(value)
        return True
    except ValueError:
        return False
