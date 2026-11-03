"""
Что можно сделать с записью.

Первое действие — по Enter, остальные — сочетаниями из подписей и из меню
Ctrl+K. Порядок в списке и есть приоритет.

Если строку позвали из окна (есть куда набирать), главное действие —
автонабор. Позвали из трея — набирать некуда, главное — скопировать пароль.

«Удалить…» стоит последним и сразу ничего не делает: меню сменяется вопросом
«Удалить «X»» / «Отмена» (ui/panel.py).
"""

from dataclasses import dataclass

from .core.i18n import tr

ENTER = "↵"


@dataclass
class Action:
    id: str
    title: str
    keys: tuple = ()          # подписи клавиш для меню
    danger: bool = False      # красным: необратимое


def actions_for(entry, can_type):
    actions = []
    if can_type:
        actions.append(Action("type", tr("action.type"), (ENTER,)))
    actions.append(Action("copy_password", tr("action.copy_password"),
                          ("Ctrl", "C") if can_type else (ENTER,)))
    if entry.username:
        actions.append(Action("copy_username", tr("action.copy_username"), ("Ctrl", "B")))
    if entry.totp:
        actions.append(Action("copy_totp", tr("action.copy_totp"), ("Ctrl", "T")))
    if can_type:
        actions.append(Action("type_password", tr("action.type_password"),
                              ("Ctrl", "Shift", ENTER)))
    if entry.url:
        actions.append(Action("open_url", tr("action.open_url"), ("Ctrl", "O")))
    actions.append(Action("edit", tr("action.edit"), ("Ctrl", "E")))
    actions.append(Action("favorite", tr("action.unfavorite" if entry.favorite
                                         else "action.favorite")))
    actions.append(Action("delete", tr("action.delete")))
    return actions


def confirm_delete(entry):
    """Вопрос вместо меню: Enter — удалить, Esc — нет."""
    return [Action("delete_confirm", tr("action.delete_confirm", name=entry.title or "—"),
                   danger=True),
            Action("cancel", tr("action.cancel"))]


def primary_label(entry, can_type):
    if entry is None:
        return ""
    return tr("primary.type" if can_type else "primary.copy")
