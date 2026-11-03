"""
Строки интерфейса на двух языках (перенесено из Spotty).

`tr("ключ", имя=значение)` — строка на текущем языке с подстановкой {имя}.
Пропущенный перевод подменяется английским, а не падает.
"""

LANGUAGES = {"ru": "Русский", "en": "English"}
DEFAULT = "ru"

_language = DEFAULT

STRINGS = {
    "search.placeholder": {"ru": "Поиск записей…", "en": "Search entries…"},
    "empty.nothing": {"ru": "Ничего не найдено", "en": "Nothing found"},
    "empty.vault": {
        "ru": "Записей пока нет — Ctrl+N, чтобы добавить",
        "en": "No entries yet — press Ctrl+N to add one"},
    "section.context": {"ru": "Для {where}", "en": "For {where}"},
    "section.favorites": {"ru": "Избранное", "en": "Favorites"},
    "section.recent": {"ru": "Недавние", "en": "Recent"},
    "section.all": {"ru": "Все записи", "en": "All Entries"},
    "section.results": {"ru": "Найдено", "en": "Results"},
    "primary.type": {"ru": "Набрать", "en": "Auto-Type"},
    "primary.copy": {"ru": "Копировать пароль", "en": "Copy Password"},
    "action.type": {"ru": "Набрать логин и пароль", "en": "Auto-Type Login"},
    "action.type_password": {"ru": "Набрать только пароль", "en": "Auto-Type Password Only"},
    "action.copy_password": {"ru": "Копировать пароль", "en": "Copy Password"},
    "action.copy_username": {"ru": "Копировать логин", "en": "Copy Username"},
    "action.copy_totp": {"ru": "Копировать код 2FA", "en": "Copy 2FA Code"},
    "action.open_url": {"ru": "Открыть сайт", "en": "Open Website"},
    "action.edit": {"ru": "Изменить", "en": "Edit"},
    "action.favorite": {"ru": "В избранное", "en": "Add to Favorites"},
    "action.unfavorite": {"ru": "Убрать из избранного", "en": "Remove from Favorites"},
    "action.delete": {"ru": "Удалить…", "en": "Delete…"},
    "action.delete_confirm": {"ru": "Удалить «{name}»", "en": "Delete “{name}”"},
    "action.cancel": {"ru": "Отмена", "en": "Cancel"},
    "unlock.password": {"ru": "Мастер-пароль", "en": "Master password"},
    "unlock.current": {"ru": "Текущий мастер-пароль", "en": "Current master password"},
    "unlock.new": {"ru": "Новый мастер-пароль", "en": "New master password"},
    "unlock.repeat": {"ru": "Ещё раз", "en": "Repeat"},
    "unlock.title.setup": {"ru": "Новое хранилище", "en": "New Vault"},
    "unlock.title.locked": {"ru": "Aegis заперт", "en": "Aegis Is Locked"},
    "unlock.title.change": {"ru": "Смена мастер-пароля", "en": "Change Master Password"},
    "unlock.title.verify": {"ru": "Подтвердите мастер-пароль", "en": "Confirm Master Password"},
    "unlock.sub.setup": {
        "ru": "Восстановить мастер-пароль нельзя — запомните или запишите его",
        "en": "The master password can’t be recovered — remember it or write it down"},
    "unlock.sub.locked": {
        "ru": "Введите мастер-пароль, чтобы открыть записи",
        "en": "Enter your master password to open your entries"},
    "unlock.sub.change": {
        "ru": "Копии базы останутся со старым паролем",
        "en": "Existing backups keep the old password"},
    "unlock.sub.verify": {
        "ru": "Пароли будут сохранены в файл открытым текстом",
        "en": "Passwords will be saved to a file in plain text"},
    "unlock.button.setup": {"ru": "Создать", "en": "Create"},
    "unlock.button.locked": {"ru": "Открыть", "en": "Unlock"},
    "unlock.button.change": {"ru": "Сменить", "en": "Change"},
    "unlock.button.verify": {"ru": "Продолжить", "en": "Continue"},
    "unlock.checking": {"ru": "Проверяю…", "en": "Checking…"},
    "unlock.wrong": {"ru": "Неверный пароль", "en": "Wrong password"},
    "unlock.broken": {
        "ru": "Файл базы повреждён или это не база Aegis",
        "en": "The vault file is damaged or isn’t an Aegis vault"},
    "unlock.too_short": {"ru": "Не короче {count} символов", "en": "At least {count} characters"},
    "unlock.mismatch": {"ru": "Пароли не совпадают", "en": "Passwords don’t match"},
    "editor.new": {"ru": "Новая запись", "en": "New Entry"},
    "editor.edit": {"ru": "Изменить запись", "en": "Edit Entry"},
    "editor.title": {"ru": "Название", "en": "Title"},
    "editor.title_hint": {"ru": "GitHub, Почта, Steam…", "en": "GitHub, Mail, Steam…"},
    "editor.username": {"ru": "Логин", "en": "Username"},
    "editor.username_hint": {"ru": "Имя или почта", "en": "Name or email"},
    "editor.password": {"ru": "Пароль", "en": "Password"},
    "editor.show": {"ru": "Показать", "en": "Show"},
    "editor.generate": {"ru": "Сгенерировать", "en": "Generate"},
    "editor.url": {"ru": "Сайт", "en": "Website"},
    "editor.window": {"ru": "Окно", "en": "Window"},
    "editor.window_hint": {
        "ru": "Часть заголовка окна программы",
        "en": "Part of the app’s window title"},
    "editor.totp": {"ru": "Код 2FA", "en": "2FA Code"},
    "editor.totp_hint": {"ru": "Секрет или ссылка otpauth://", "en": "Secret or otpauth:// link"},
    "editor.totp_bad": {"ru": "Не разобрать", "en": "Invalid"},
    "editor.sequence": {"ru": "Автонабор", "en": "Auto-Type"},
    "editor.notes": {"ru": "Заметки", "en": "Notes"},
    "editor.notes_hint": {"ru": "Что угодно", "en": "Anything"},
    "editor.favorite": {"ru": "В избранном", "en": "Favorite"},
    "editor.save": {"ru": "Сохранить", "en": "Save"},
    "editor.cancel": {"ru": "Отмена", "en": "Cancel"},
    "editor.delete": {"ru": "Удалить", "en": "Delete"},
    "confirm.delete_title": {"ru": "Удалить «{name}»?", "en": "Delete “{name}”?"},
    "confirm.delete_text": {
        "ru": "Запись останется только в копиях базы.",
        "en": "The entry will remain only in the vault backups."},
    "confirm.delete_yes": {"ru": "Удалить", "en": "Delete"},
    "confirm.pair_title": {"ru": "Подключить расширение?", "en": "Connect the Extension?"},
    "confirm.pair_text": {
        "ru": "Расширение Aegis в {browser} просит доступ к паролям. Разрешайте, только если подключение начали вы сами.",
        "en": "The Aegis extension in {browser} asks for access to your passwords. Allow only if you started the connection yourself."},
    "confirm.pair_yes": {"ru": "Разрешить", "en": "Allow"},
    "confirm.pair_no": {"ru": "Отклонить", "en": "Deny"},
    "confirm.restore_title": {"ru": "Восстановить копию?", "en": "Restore the Backup?"},
    "confirm.restore_text": {
        "ru": "Копия от {when} заменит текущую базу, а сама текущая база сначала уйдёт в копии. Откроется копия тем паролем, который был у неё.",
        "en": "The backup from {when} replaces the current vault; the current vault is backed up first. The backup opens with the password it had."},
    "confirm.restore_yes": {"ru": "Восстановить", "en": "Restore"},
    "confirm.no": {"ru": "Отмена", "en": "Cancel"},
    "hud.copied_password": {
        "ru": "Пароль скопирован · сотру через {seconds} с",
        "en": "Password copied · clearing in {seconds}s"},
    "hud.copied_password_keep": {"ru": "Пароль скопирован", "en": "Password copied"},
    "hud.copied_username": {"ru": "Логин скопирован", "en": "Username copied"},
    "hud.copied_totp": {"ru": "Код скопирован", "en": "Code copied"},
    "hud.no_totp": {"ru": "Код 2FA не разобрать", "en": "Can’t read the 2FA code"},
    "hud.saved": {"ru": "Сохранено", "en": "Saved"},
    "hud.deleted": {"ru": "Удалено", "en": "Deleted"},
    "hud.locked": {"ru": "Aegis заперт", "en": "Aegis locked"},
    "hud.type_failed": {
        "ru": "Окно сменилось — набор прерван",
        "en": "Window changed — auto-type stopped"},
    "hud.password_changed": {"ru": "Мастер-пароль изменён", "en": "Master password changed"},
    "hud.backup_done": {"ru": "Копия сделана", "en": "Backup created"},
    "hud.backup_failed": {"ru": "Не удалось сделать копию", "en": "Couldn’t create a backup"},
    "hud.imported": {"ru": "Импортировано: {count}", "en": "Imported: {count}"},
    "hud.import_none": {"ru": "В файле нет новых записей", "en": "No new entries in the file"},
    "hud.import_failed": {"ru": "Не удалось прочитать CSV", "en": "Couldn’t read the CSV"},
    "hud.exported": {
        "ru": "Готово. Удалите файл, когда он станет не нужен",
        "en": "Done. Delete the file when you no longer need it"},
    "hud.save_failed": {"ru": "Не удалось записать базу", "en": "Couldn’t write the vault"},
    "hud.restored": {
        "ru": "Копия на месте — введите её пароль",
        "en": "Backup restored — enter its password"},
    "toast.welcome": {"ru": "Aegis живёт в трее", "en": "Aegis lives in the tray"},
    "toast.welcome_sub": {
        "ru": "Нажмите {hotkey} в любом окне",
        "en": "Press {hotkey} in any window"},
    "toast.hotkey_busy_sub": {
        "ru": "Нажмите, чтобы выбрать другое",
        "en": "Click to choose another one"},
    "toast.save_title": {
        "ru": "Сохранить пароль для {site}?",
        "en": "Save the password for {site}?"},
    "toast.save_sub": {"ru": "Нажмите, чтобы открыть в Aegis", "en": "Click to open it in Aegis"},
    "toast.backup_failed": {"ru": "Копия базы не записалась", "en": "Vault backup failed"},
    "toast.backup_failed_sub": {
        "ru": "Папка недоступна: {folder}",
        "en": "Folder unavailable: {folder}"},
    "tray.open": {"ru": "Открыть Aegis", "en": "Open Aegis"},
    "tray.new": {"ru": "Новая запись", "en": "New Entry"},
    "tray.lock": {"ru": "Запереть", "en": "Lock"},
    "tray.unlock": {"ru": "Открыть базу…", "en": "Unlock…"},
    "tray.settings": {"ru": "Настройки", "en": "Settings"},
    "tray.update": {"ru": "Проверить обновления", "en": "Check for Updates"},
    "tray.quit": {"ru": "Выход", "en": "Quit"},
    "settings.hotkey_sub": {
        "ru": "Строка с паролями — сразу с подходящими окну",
        "en": "Opens your passwords — matching ones first"},
    "settings.security": {"ru": "БЕЗОПАСНОСТЬ", "en": "SECURITY"},
    "settings.lock_idle": {"ru": "Запирать при простое", "en": "Lock When Idle"},
    "settings.lock_idle_sub": {
        "ru": "Компьютер не трогали столько времени",
        "en": "After this long without any input"},
    "settings.lock_session": {"ru": "Запирать вместе с Windows", "en": "Lock with Windows"},
    "settings.lock_session_sub": {
        "ru": "Win+L, выход из системы, сон",
        "en": "Win+L, sign-out, sleep"},
    "settings.clipboard": {"ru": "Стирать пароль из буфера", "en": "Clear Copied Passwords"},
    "settings.clipboard_sub": {
        "ru": "И не пускать его в журнал буфера (Win+V)",
        "en": "And keep them out of clipboard history (Win+V)"},
    "settings.read_url": {"ru": "Читать адрес из браузера", "en": "Read the Browser’s Address"},
    "settings.read_url_sub": {
        "ru": "Чтобы сразу показывать записи сайта",
        "en": "To show the site’s entries first"},
    "settings.gen_length": {"ru": "Генератор: длина пароля", "en": "Generator: Password Length"},
    "settings.gen_length_sub": {
        "ru": "Для кнопки «Сгенерировать» в записи. Свой пароль — любой длины",
        "en": "For the Generate button in an entry. Your own password can be any length"},
    "settings.gen_symbols": {"ru": "Генератор: спецсимволы", "en": "Generator: Symbols"},
    "settings.gen_symbols_sub": {
        "ru": "Некоторые сайты их не принимают",
        "en": "Some sites don’t accept them"},
    "settings.master": {"ru": "Мастер-пароль", "en": "Master Password"},
    "settings.master_sub": {"ru": "Им зашифрована вся база", "en": "It encrypts the whole vault"},
    "settings.change_password": {"ru": "Сменить", "en": "Change"},
    "settings.minutes": {"ru": "{count} мин", "en": "{count} min"},
    "settings.seconds": {"ru": "{count} с", "en": "{count}s"},
    "settings.never": {"ru": "Никогда", "en": "Never"},
    "settings.backups": {"ru": "КОПИИ БАЗЫ", "en": "BACKUPS"},
    "settings.backup_now": {"ru": "Сделать копию", "en": "Back Up Now"},
    "settings.backup_dir": {"ru": "Папка копий", "en": "Backup Folder"},
    "settings.backup_extra": {"ru": "Ещё одна папка", "en": "Second Folder"},
    "settings.backup_extra_sub": {
        "ru": "Облако или флешка — копии зашифрованы",
        "en": "Cloud folder or USB drive — backups are encrypted"},
    "settings.open": {"ru": "Открыть", "en": "Open"},
    "settings.choose": {"ru": "Выбрать…", "en": "Choose…"},
    "settings.restore": {"ru": "Восстановить", "en": "Restore"},
    "settings.no_backups": {
        "ru": "Копий пока нет — появятся после первого изменения",
        "en": "No backups yet — they appear after the first change"},
    "settings.more_backups": {
        "ru": "И ещё {count} в папке копий",
        "en": "And {count} more in the backup folder"},
    "settings.data": {"ru": "ИМПОРТ И ЭКСПОРТ", "en": "IMPORT & EXPORT"},
    "settings.import_title": {"ru": "Импорт из CSV", "en": "Import from CSV"},
    "settings.import_sub": {
        "ru": "Chrome, Edge, Firefox, Bitwarden, KeePass, 1Password",
        "en": "Chrome, Edge, Firefox, Bitwarden, KeePass, 1Password"},
    "settings.import": {"ru": "Выбрать файл…", "en": "Choose File…"},
    "settings.export_title": {"ru": "Экспорт в CSV", "en": "Export to CSV"},
    "settings.export_sub": {
        "ru": "Открытым текстом — для переезда в другой менеджер",
        "en": "Plain text — for moving to another manager"},
    "settings.export": {"ru": "Экспорт…", "en": "Export…"},
    "settings.browser_from": {"ru": "Импорт из {name}", "en": "Import from {name}"},
    "settings.browser_import": {"ru": "Импорт", "en": "Import"},
    "settings.browser_export": {"ru": "Выгрузить…", "en": "Export…"},
    "settings.browser_direct": {
        "ru": "Прочитаю пароли напрямую",
        "en": "Reads the passwords directly"},
    "settings.browser_via_export": {
        "ru": "Браузер выгрузит их сам, спросив PIN Windows; файл я сотру",
        "en": "The browser exports them after your Windows PIN; I delete the file"},
    "settings.no_browsers": {"ru": "Браузеров с паролями не нашлось", "en": "No browsers with saved passwords found"},
    "hud.browser_reading": {"ru": "Читаю пароли из {name}…", "en": "Reading passwords from {name}…"},
    "hud.browser_failed": {"ru": "Не удалось прочитать пароли из {name}", "en": "Couldn’t read passwords from {name}"},
    "hud.browser_skipped": {"ru": "не расшифровано: {count}", "en": "unreadable: {count}"},
    "toast.export_title": {"ru": "Выгрузите пароли в {name}", "en": "Export passwords in {name}"},
    "toast.export_sub.app_bound": {
        "ru": "Нажмите «Экспорт паролей» и сохраните файл — остальное сделаю сам",
        "en": "Click “Export passwords” and save the file — I’ll do the rest"},
    "toast.export_sub.primary_password": {
        "ru": "В Firefox задан основной пароль: «…» → «Экспорт логинов» — остальное сделаю сам",
        "en": "Firefox has a primary password: “…” → “Export Logins” — I’ll do the rest"},
    "toast.export_timeout": {"ru": "Не дождался файла с паролями", "en": "No password file arrived"},
    "toast.export_timeout_sub": {
        "ru": "Если сохранили в другую папку — «Импорт из CSV»",
        "en": "If you saved it elsewhere, use “Import from CSV”"},
    "toast.export_deleted": {"ru": "Файл выгрузки стёрт", "en": "The export file was deleted"},
    "toast.export_kept": {
        "ru": "Файл с паролями не стёрт — удалите его сами: {path}",
        "en": "The password file wasn’t deleted — delete it yourself: {path}"},
    "settings.extension": {"ru": "РАСШИРЕНИЕ БРАУЗЕРА", "en": "BROWSER EXTENSION"},
    "settings.bridge": {"ru": "Работать с расширением", "en": "Allow the Extension"},
    "settings.bridge_sub": {
        "ru": "Значок Aegis в полях входа на сайтах",
        "en": "Aegis icon in sign-in fields on websites"},
    "settings.ext_install": {"ru": "Установить расширение", "en": "Install the Extension"},
    "settings.ext_install_sub": {
        "ru": "Режим разработчика → Загрузить распакованное → эта папка",
        "en": "Developer mode → Load unpacked → this folder"},
    "settings.no_pairs": {"ru": "Подключённых браузеров нет", "en": "No connected browsers"},
    "settings.paired": {"ru": "Подключён", "en": "Connected"},
    "settings.unpair": {"ru": "Отключить", "en": "Disconnect"},
    "settings.updates": {"ru": "ОБНОВЛЕНИЯ", "en": "UPDATES"},
    "dialog.import": {"ru": "Импорт паролей", "en": "Import Passwords"},
    "dialog.export": {"ru": "Экспорт паролей", "en": "Export Passwords"},
    "dialog.backup_dir": {"ru": "Папка для копий", "en": "Backup Folder"},

    "settings.look": {"ru": "ВИД", "en": "APPEARANCE"},
    "settings.glass": {"ru": "Стеклянный фон", "en": "Glass Background"},
    "settings.glass_sub": {"ru": "Размытие того, что под строкой", "en": "Blurs what is behind the bar"},
    "settings.live_glass": {"ru": "Живой фон", "en": "Live Background"},
    "settings.live_glass_sub": {
        "ru": "Стекло обновляется на лету. Строки не будет на скриншотах",
        "en": "Glass updates in real time. The bar won’t show in screenshots"},
    "settings.live_fps": {"ru": "Кадров в секунду", "en": "Frame Rate"},
    "settings.live_fps_sub": {
        "ru": "Чаще — плавнее, но больше нагрузка",
        "en": "Higher is smoother but uses more CPU"},

    # Обновления и общие подписи — как в Spotty.
    "footer.actions": {"ru": "Действия", "en": "Actions"},
    "footer.back": {"ru": "Назад", "en": "Back"},
    "settings.title": {"ru": "Настройки", "en": "Settings"},
    "settings.hotkey": {"ru": "Сочетание для вызова", "en": "Hotkey"},
    "settings.hotkey_wait": {"ru": "Нажмите сочетание…", "en": "Press keys…"},
    "settings.hotkey_busy": {
        "ru": "Сочетание занято другой программой",
        "en": "Another app already uses this shortcut"},
    "settings.autostart": {"ru": "Запускать вместе с Windows", "en": "Launch at Startup"},
    "settings.autostart_dev": {
        "ru": "Работает только в установленной программе",
        "en": "Works in the installed app only"},
    "settings.auto_update": {"ru": "Проверять обновления", "en": "Check for Updates"},
    "settings.update_mode": {"ru": "Новая версия", "en": "New Versions"},
    "settings.update_mode.notify": {"ru": "Сообщать", "en": "Notify Me"},
    "settings.update_mode.background": {"ru": "Скачивать в фоне", "en": "Download in Background"},
    "settings.update_mode_sub.notify": {
        "ru": "Уведомление в углу, установка — когда скажете",
        "en": "A notice in the corner, install when you choose"},
    "settings.update_mode_sub.background": {
        "ru": "Скачается само, в строке появится кнопка",
        "en": "Downloads on its own, then a button appears"},
    "settings.language": {"ru": "Язык", "en": "Language"},
    "settings.check_now": {"ru": "Проверить", "en": "Check"},
    "settings.install": {"ru": "Установить", "en": "Install"},
    "settings.restart": {"ru": "Перезапустить", "en": "Restart"},
    "settings.version": {"ru": "Версия {version}", "en": "Version {version}"},
    "update.checking": {"ru": "Проверяю…", "en": "Checking…"},
    "update.current": {"ru": "Установлена последняя версия", "en": "You’re up to date"},
    "update.available": {"ru": "Доступна версия {version}", "en": "Version {version} is available"},
    "update.downloading": {
        "ru": "Скачиваю {version}… {percent}%",
        "en": "Downloading {version}… {percent}%"},
    "update.ready": {
        "ru": "Версия {version} скачана — перезапустите",
        "en": "Version {version} is downloaded — restart to update"},
    "update.error": {"ru": "Не удалось проверить", "en": "Couldn’t check"},
    "update.failed": {"ru": "Не удалось скачать", "en": "Couldn’t download"},
    "update.dev": {
        "ru": "В режиме разработки не обновляется",
        "en": "Updates are off in development mode"},
    "update.card": {"ru": "Обновление до {version}", "en": "Updating to {version}"},
    "update.card_downloading": {"ru": "Скачиваю…", "en": "Downloading…"},
    "update.restarting": {"ru": "Перезапускаю…", "en": "Restarting…"},
    "update.restart_button": {"ru": "Перезапустить и обновить", "en": "Restart and Update"},
    "toast.hotkey_busy": {
        "ru": "Сочетание {hotkey} занято",
        "en": "{hotkey} is taken by another app"},
    "toast.checking": {"ru": "Проверяю обновления…", "en": "Checking for updates…"},
    "toast.current": {"ru": "Установлена последняя версия", "en": "You’re on the latest version"},
    "toast.check_failed": {
        "ru": "Не удалось проверить обновления",
        "en": "Couldn’t check for updates"},
    "toast.available": {"ru": "Вышла версия {version}", "en": "Version {version} is out"},
    "toast.available_sub": {"ru": "Нажмите, чтобы обновить", "en": "Click to update"},
    "toast.downloading": {"ru": "Скачиваю версию {version}", "en": "Downloading version {version}"},
    "toast.downloading_sub": {
        "ru": "Пользуйтесь Aegis как обычно",
        "en": "Keep using Aegis as usual"},
    "toast.ready": {"ru": "Версия {version} скачана", "en": "Version {version} is ready"},
    "toast.ready_sub": {
        "ru": "Нажмите, чтобы перезапустить и обновить",
        "en": "Click to restart and update"},
    "toast.download_failed": {
        "ru": "Не удалось скачать обновление",
        "en": "Couldn’t download the update"},
    "toast.download_failed_sub": {
        "ru": "Проверьте интернет и попробуйте ещё раз",
        "en": "Check your connection and try again"},
    "toast.install_failed": {
        "ru": "Не удалось установить обновление",
        "en": "Couldn’t install the update"},
    "toast.install_failed_sub": {
        "ru": "Aegis продолжает работать в прежней версии",
        "en": "Aegis keeps running the current version"},
}


def set_language(code):
    """Неизвестный код (например, «auto» из старых настроек) — английский."""
    global _language
    _language = code if code in LANGUAGES else DEFAULT


def language():
    return _language


def tr(key, **kwargs):
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_language) or entry.get("en") or key
    return text.format(**kwargs) if kwargs else text
