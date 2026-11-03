"""Генератор паролей: криптостойкий random (secrets), по символу из каждой группы."""

import math
import secrets
import string

# Без похожих друг на друга символов (l/1/I, O/0): пароль иногда приходится
# читать глазами и набирать на другом устройстве.
LOWER = "abcdefghijkmnopqrstuvwxyz"
UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
DIGITS = "23456789"
SYMBOLS = "!@#$%^&*()-_=+[]{};:,.?"

DEFAULT_LENGTH = 20
MIN_LENGTH = 8
MAX_LENGTH = 64


def generate(length=DEFAULT_LENGTH, symbols=True):
    length = max(MIN_LENGTH, min(MAX_LENGTH, int(length)))
    groups = [LOWER, UPPER, DIGITS] + ([SYMBOLS] if symbols else [])
    alphabet = "".join(groups)
    while True:
        chars = [secrets.choice(alphabet) for _ in range(length)]
        if all(any(c in g for c in chars) for g in groups):
            return "".join(chars)


def strength(password):
    """Грубая оценка 0..4 по длине и разнообразию — для полоски в редакторе."""
    if not password:
        return 0
    pools = 0
    if any(c in string.ascii_lowercase for c in password):
        pools += 26
    if any(c in string.ascii_uppercase for c in password):
        pools += 26
    if any(c.isdigit() for c in password):
        pools += 10
    if any(not c.isalnum() for c in password):
        pools += 30
    if any(ord(c) > 127 for c in password):
        pools += 60
    bits = len(password) * math.log2(max(pools, 2))
    if bits < 40:
        return 1
    if bits < 60:
        return 2
    if bits < 85:
        return 3
    return 4
