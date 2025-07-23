import html
import logging
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold

from db.requests import (
    get_chat_settings, update_chat_setting, get_stop_words, 
    add_stop_word, delete_stop_word, get_all_notes, add_note, delete_note,
    get_all_triggers, add_trigger, delete_trigger
)
from states import SettingsStates
from .filters import stop_words_cache, triggers_cache

router = Router()

# ИСПРАВЛЕНИЕ: Импортируем оба кэша из filters.py
from .filters import stop_words_cache, triggers_cache

router = Router()

VERIFIED_USERS = {}


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ АВТО-УДАЛЕНИЯ ---
async def delete_message_after_delay(message: types.Message, delay: int):
    """Запускает таймер и удаляет сообщение после задержки."""
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass # Игнорируем ошибки, если сообщение уже было удалено
# --- ФАБРИКИ КЛАВИАТУР (Создатели меню) ---

async def get_main_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Создает новое главное меню настроек."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📜 Правила", callback_data="menu:rules"),
        InlineKeyboardButton(text="🛡️ Антиспам", callback_data="menu:antispam")
    )
    builder.row(
        InlineKeyboardButton(text="👋 Приветствие", callback_data="menu:welcome"),
        InlineKeyboardButton(text="🌊 Антифлуд", callback_data="menu:antiflood")
    )
    builder.row(
        InlineKeyboardButton(text="🚪 Прощание", callback_data="menu:goodbye"),
        InlineKeyboardButton(text="🧠 Капча", callback_data="menu:captcha")
    )
    builder.row(
        InlineKeyboardButton(text="❗️ Предупреждения", callback_data="menu:warns"),
        InlineKeyboardButton(text="🚫 Блокировки", callback_data="menu:blocks")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Закрыть", callback_data="menu:close"),
        InlineKeyboardButton(text="➡️ Другие", callback_data="menu:other")
    )
    return builder.as_markup()

async def get_rules_menu(chat_id: int):
    """Создает меню для управления правилами."""
    settings = await get_chat_settings(chat_id)
    rules_text = settings.get('rules_text', 'Правила еще не установлены.')
    text = (f"📜 **Управление правилами**\n\nТекущие правила:\n<i>{html.escape(rules_text)}</i>")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить правила", callback_data="action:change_rules"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return text, builder.as_markup()

async def get_welcome_menu(chat_id: int):
    """Создает меню для управления приветствием."""
    settings = await get_chat_settings(chat_id)
    welcome_text = settings.get('welcome_message', "Добро пожаловать, {user_mention}!")
    text = (f"👋 **Управление приветствием**\n\nТекущее сообщение:\n<code>{html.escape(welcome_text)}</code>\n\n"
            "Используйте <code>{user_mention}</code> для упоминания пользователя.")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить текст", callback_data="action:change_welcome"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return text, builder.as_markup()

async def get_goodbye_menu(chat_id: int):
    """Создает меню для управления прощанием."""
    settings = await get_chat_settings(chat_id)
    goodbye_text = settings.get('goodbye_message', "Пользователь {user_mention} покинул чат.")
    text = (f"🚪 **Управление прощанием**\n\nТекущее сообщение:\n<code>{html.escape(goodbye_text)}</code>\n\n"
            "Используйте <code>{user_mention}</code> для упоминания пользователя.")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить текст", callback_data="action:change_goodbye"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return text, builder.as_markup()

async def get_antispam_menu(chat_id: int):
    """Создает меню для настроек антиспама."""
    settings = await get_chat_settings(chat_id)
    antilink_status = "✅ Включена" if settings.get('antilink_enabled', False) else "❌ Выключена"
    text = "🛡️ **Настройки антиспама**"
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=f"Защита от ссылок: {antilink_status}", callback_data="action:toggle_antilink"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return text, builder.as_markup()

async def get_captcha_menu(chat_id: int):
    """Создает меню для настроек капчи."""
    settings = await get_chat_settings(chat_id)
    captcha_status = "✅ Включена" if settings.get('captcha_enabled', False) else "❌ Выключена"
    captcha_timeout = settings.get('captcha_timeout', 60)
    text = "🧠 **Настройки CAPTCHA**"
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=f"CAPTCHA для новичков: {captcha_status}", callback_data="action:toggle_captcha"))
    builder.add(InlineKeyboardButton(text=f"Таймаут: {captcha_timeout} сек.", callback_data="action:change_captcha_timeout"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    builder.adjust(1)
    return text, builder.as_markup()

async def get_warns_menu(chat_id: int):
    """Создает меню для настроек предупреждений."""
    settings = await get_chat_settings(chat_id)
    warn_limit = settings.get('warn_limit', 3)
    text = f"❗️ **Настройки предупреждений**\n\nТекущий лимит варнов до бана: <b>{warn_limit}</b>"
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✏️ Изменить лимит", callback_data="action:change_warn_limit"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return text, builder.as_markup()

async def get_blocks_menu():
    """Создает информационное меню для блокировок."""
    text = (
        "🚫 **Управление блокировками**\n\n"
        "Для управления блокировками используйте следующие команды в ответ на сообщение пользователя:\n\n"
        "• <code>/mute &lt;время&gt;</code> - замутить (1h, 10m, 2d)\n"
        "• <code>/unmute</code> - размутить\n"
        "• <code>/ban &lt;время&gt;</code> - забанить\n"
        "• <code>/unban</code> - разбанить"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return text, builder.as_markup()

async def get_notes_menu(chat_id: int):
    """Создает текст и клавиатуру для меню заметок."""
    notes = await get_all_notes(chat_id)
    text = "🗒️ **Управление заметками**\n\nТекущий список:\n"
    if notes:
        text += "\n".join(f"• <code>#{html.escape(note)}</code>" for note in notes)
    else:
        text += "Список пуст."
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data="action:add_note"),
        InlineKeyboardButton(text="➖ Удалить", callback_data="action:del_note")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:content"))
    return text, builder.as_markup()

async def get_triggers_menu(chat_id: int):
    """Создает текст и клавиатуру для меню триггеров."""
    triggers = await get_all_triggers(chat_id)
    text = "🤖 **Управление триггерами**\n\nТекущий список:\n"
    if triggers:
        text += "\n".join(f"• <code>{html.escape(keyword)}</code>" for keyword in triggers)
    else:
        text += "Список пуст."
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data="action:add_trigger"),
        InlineKeyboardButton(text="➖ Удалить", callback_data="action:del_trigger")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:content"))
    return text, builder.as_markup()

async def get_stopwords_menu(chat_id: int):
    """Создает текст и клавиатуру для меню стоп-слов."""
    words = await get_stop_words(chat_id)
    text = "🚫 **Управление стоп-словами**\n\nТекущий список:\n"
    if words:
        text += "\n".join(f"• <code>{html.escape(word)}</code>" for word in words)
    else:
        text += "Список пуст."
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить", callback_data="action:add_stopword"),
        InlineKeyboardButton(text="➖ Удалить", callback_data="action:del_stopword")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:content"))
    return text, builder.as_markup()


async def get_moderation_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Создает меню настроек модерации (объединяет антиспам, капчу и варны)."""
    settings = await get_chat_settings(chat_id)
    antilink_status = "✅ Включена" if settings.get('antilink_enabled', False) else "❌ Выключена"
    captcha_status = "✅ Включена" if settings.get('captcha_enabled', False) else "❌ Выключена"
    captcha_timeout = settings.get('captcha_timeout', 60)
    warn_limit = settings.get('warn_limit', 3)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=f"Лимит варнов: {warn_limit}", callback_data="action:change_warn_limit"))
    builder.add(InlineKeyboardButton(text=f"Защита от ссылок: {antilink_status}", callback_data="action:toggle_antilink"))
    builder.add(InlineKeyboardButton(text=f"CAPTCHA для новичков: {captcha_status}", callback_data="action:toggle_captcha"))
    builder.add(InlineKeyboardButton(text=f"Таймаут CAPTCHA: {captcha_timeout} сек.", callback_data="action:change_captcha_timeout"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    builder.adjust(1)
    return builder.as_markup()


# --- ОБРАБОТЧИКИ НАВИГАЦИИ ПО МЕНЮ ---

@router.callback_query(F.data.startswith("menu:"))
async def handle_menu_navigation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    menu_type = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    text, keyboard = "Раздел в разработке.", None
    if menu_type == "main":
        text = "PARAMETRY\n<b>Группа:</b> {chat_title}\n\nВыберите один из параметров, который вы хотите изменить.".format(chat_title=html.escape(callback.message.chat.title))
        keyboard = await get_main_settings_keyboard(chat_id)
    elif menu_type == "rules":
        text, keyboard = await get_rules_menu(chat_id)
    elif menu_type == "welcome":
        text, keyboard = await get_welcome_menu(chat_id)
    elif menu_type == "goodbye":
        text, keyboard = await get_goodbye_menu(chat_id)
    elif menu_type == "antispam":
        text, keyboard = await get_antispam_menu(chat_id)
    elif menu_type == "captcha":
        text, keyboard = await get_captcha_menu(chat_id)
    elif menu_type == "warns":
        text, keyboard = await get_warns_menu(chat_id)
    elif menu_type == "blocks":
        text, keyboard = await get_blocks_menu()
    elif menu_type == "notes":
        text, keyboard = await get_notes_menu(chat_id)
    elif menu_type == "triggers":
        text, keyboard = await get_triggers_menu(chat_id)
    elif menu_type == "stopwords":
        text, keyboard = await get_stopwords_menu(chat_id)
    elif menu_type == "close":
        await callback.message.delete()
        return await callback.answer()
    else: # Заглушка
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
        keyboard = builder.as_markup()

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()



# --- ОБРАБОТЧИКИ ДЕЙСТВИЙ ИЗ МЕНЮ ---

@router.callback_query(F.data.startswith("action:"))
async def handle_menu_actions(callback: types.CallbackQuery, state: FSMContext, bot: Bot, log_action: callable):
    member = await bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return await callback.answer("Это действие доступно только администраторам.", show_alert=True)

    action = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    prompts = {
        "change_rules": ("Пожалуйста, отправьте новый текст правил.", SettingsStates.waiting_for_rules_text),
        "change_welcome": ("Пожалуйста, отправьте новый текст приветствия.", SettingsStates.waiting_for_welcome_message),
        "change_goodbye": ("Пожалуйста, отправьте новый текст прощания.", SettingsStates.waiting_for_goodbye_message),
        "change_warn_limit": ("Пожалуйста, отправьте новое число для лимита варнов.", SettingsStates.waiting_for_warn_limit),
        "change_captcha_timeout": ("Отправьте новое время в секундах для капчи (10-300).", SettingsStates.waiting_for_captcha_timeout),
        "add_stopword": ("Отправьте слово или фразу для добавления в черный список.", SettingsStates.waiting_for_stop_word_to_add),
        "del_stopword": ("Отправьте слово или фразу для удаления из черного списка.", SettingsStates.waiting_for_stop_word_to_delete),
        "add_note": ("Отправьте имя для новой заметки (одно слово без #).", SettingsStates.waiting_for_note_name_to_add),
        "del_note": ("Отправьте имя заметки для удаления (без #).", SettingsStates.waiting_for_note_name_to_delete),
        "add_trigger": ('Отправьте ключевую фразу для нового триггера.', SettingsStates.waiting_for_trigger_keyword_to_add),
        "del_trigger": ('Отправьте ключевую фразу триггера для удаления.', SettingsStates.waiting_for_trigger_keyword_to_delete),
    }

    if action in prompts:
        prompt_text, new_state = prompts[action]
        await state.update_data(menu_message_id=callback.message.message_id)
        await callback.message.edit_text(prompt_text)
        await state.set_state(new_state)
    
    elif action in ["toggle_antilink", "toggle_captcha"]:
        setting_name = "antilink_enabled" if action == "toggle_antilink" else "captcha_enabled"
        settings = await get_chat_settings(chat_id)
        new_status = not settings.get(setting_name, False)
        await update_chat_setting(chat_id, setting_name, new_status)
        
        setting_name_rus = "Защита от ссылок" if action == "toggle_antilink" else "CAPTCHA"
        status_text = "включена" if new_status else "выключена"
        log_text = (f"⚙️ <b>Изменена настройка: {setting_name_rus}</b>\n"
                    f"<b>Админ:</b> {callback.from_user.mention_html()}\n"
                    f"<b>Новый статус:</b> {status_text}")
        await log_action(chat_id, log_text, bot)
        
        if action == "toggle_antilink":
            _, new_keyboard = await get_antispam_menu(chat_id)
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)
        else:
            # ИСПРАВЛЕНИЕ: Сначала дожидаемся выполнения, потом берем элемент
            _, new_keyboard = await get_captcha_menu(chat_id)
            await callback.message.edit_reply_markup(reply_markup=new_keyboard)

    await callback.answer()



# --- ОБРАБОТЧИКИ СОСТОЯНИЙ (FSM) ---
async def return_to_menu(message: types.Message, state: FSMContext, menu_func: callable, bot: Bot):
    """Универсальная функция для возврата в меню после изменения настройки."""
    data = await state.get_data()
    menu_message_id = data.get("menu_message_id")
    await state.clear()

    await message.delete()

    if menu_message_id:
        text, keyboard = await menu_func(message.chat.id)
        try:
            await bot.edit_message_text(
                text=text, chat_id=message.chat.id, message_id=menu_message_id,
                parse_mode="HTML", reply_markup=keyboard
            )
        except Exception as e:
            logging.warning(f"Не удалось обновить меню: {e}. Отправляю новое.")
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(SettingsStates.waiting_for_rules_text)
async def process_new_rules_text(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    new_text = message.html_text
    await update_chat_setting(message.chat.id, 'rules_text', new_text)
    confirmation_msg = await message.answer("✅ Новые правила успешно установлены.")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))

    log_text = (f"⚙️ <b>Обновлены правила чата</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}")
    await log_action(message.chat.id, log_text, bot)
    
    await return_to_menu(message, state, get_rules_menu, bot)

@router.message(SettingsStates.waiting_for_goodbye_message)
async def process_new_goodbye_message(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    new_text = message.html_text
    await update_chat_setting(message.chat.id, 'goodbye_message', new_text)
    confirmation_msg = await message.answer("✅ Новое прощальное сообщение установлено.")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))

    log_text = (f"⚙️ <b>Изменено прощание</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}")
    await log_action(message.chat.id, log_text, bot)
    
    await return_to_menu(message, state, get_goodbye_menu, bot)

@router.message(SettingsStates.waiting_for_captcha_timeout)
async def process_new_captcha_timeout(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    if not message.text.isdigit() or not (10 <= int(message.text) <= 300):
        error_msg = await message.reply("Пожалуйста, введите число от 10 до 300 секунд.")
        asyncio.create_task(delete_message_after_delay(error_msg, 5))
        return
    
    timeout = int(message.text)
    await update_chat_setting(message.chat.id, 'captcha_timeout', timeout)
    confirmation_msg = await message.answer(f"✅ Таймаут для капчи изменен на {timeout} секунд.")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))
    
    log_text = (f"⚙️ <b>Изменен таймаут CAPTCHA</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новое значение:</b> {timeout} сек.")
    await log_action(message.chat.id, log_text, bot)

    await return_to_menu(message, state, get_captcha_menu, bot)

@router.message(SettingsStates.waiting_for_warn_limit)
async def process_new_warn_limit(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    if not message.text.isdigit() or int(message.text) < 1:
        error_msg = await message.reply("Пожалуйста, введите целое число больше 0.")
        asyncio.create_task(delete_message_after_delay(error_msg, 5))
        return
    
    limit = int(message.text)
    await update_chat_setting(message.chat.id, 'warn_limit', limit)
    confirmation_msg = await message.answer(f"✅ Лимит предупреждений изменен на {hbold(limit)}.", parse_mode="HTML")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))

    log_text = (f"⚙️ <b>Изменен лимит варнов</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новое значение:</b> {limit}")
    await log_action(message.chat.id, log_text, bot)
    
    await return_to_menu(message, state, get_warns_menu, bot)


@router.message(SettingsStates.waiting_for_welcome_message)
async def process_new_welcome_message(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    new_text = message.html_text
    await update_chat_setting(message.chat.id, 'welcome_message', new_text)
    confirmation_msg = await message.answer("✅ Новое приветственное сообщение установлено.")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))

    log_text = (f"⚙️ <b>Изменено приветствие</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}")
    await log_action(message.chat.id, log_text, bot)
    
    await return_to_menu(message, state, get_welcome_menu, bot)

@router.message(SettingsStates.waiting_for_stop_word_to_add)
async def process_add_stop_word(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    word = message.text.lower()
    if await add_stop_word(message.chat.id, word):
        stop_words_cache[message.chat.id] = set(await get_stop_words(message.chat.id))
        confirmation_msg = await message.answer(f"✅ Слово <code>{html.escape(word)}</code> добавлено.", parse_mode="HTML")
        asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))
        
        log_text = (f"➕ <b>Добавлено стоп-слово</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Слово:</b> <code>{html.escape(word)}</code>")
        await log_action(message.chat.id, log_text, bot)
    else:
        error_msg = await message.answer("Это слово уже есть в списке.")
        asyncio.create_task(delete_message_after_delay(error_msg, 5))
    
    await return_to_menu(message, state, get_stopwords_menu, bot)

@router.message(SettingsStates.waiting_for_stop_word_to_delete)
async def process_del_stop_word(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    word = message.text.lower()
    if await delete_stop_word(message.chat.id, word):
        stop_words_cache[message.chat.id] = set(await get_stop_words(message.chat.id))
        confirmation_msg = await message.answer(f"✅ Слово <code>{html.escape(word)}</code> удалено.", parse_mode="HTML")
        asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))
        
        log_text = (f"➖ <b>Удалено стоп-слово</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Слово:</b> <code>{html.escape(word)}</code>")
        await log_action(message.chat.id, log_text, bot)
    else:
        error_msg = await message.answer("Такого слова нет в списке.")
        asyncio.create_task(delete_message_after_delay(error_msg, 5))
        
    await return_to_menu(message, state, get_stopwords_menu, bot)

@router.message(SettingsStates.waiting_for_note_name_to_add)
async def process_add_note_name(message: types.Message, state: FSMContext):
    await state.update_data(note_name=message.text.lower().split()[0])
    await message.delete() # Удаляем имя заметки
    menu_message_id = (await state.get_data()).get("menu_message_id")
    await bot.edit_message_text("Отлично. Теперь отправьте содержимое заметки.", chat_id=message.chat.id, message_id=menu_message_id)
    await state.set_state(SettingsStates.waiting_for_note_content)

@router.message(SettingsStates.waiting_for_note_content)
async def process_add_note_content(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    data = await state.get_data()
    name = data['note_name']
    content = message.html_text
    
    is_new = await add_note(message.chat.id, name, content)
    status = "создана" if is_new else "обновлена"
    confirmation_msg = await message.answer(f"✅ Заметка `#{name}` успешно {status}.")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))
    
    log_text = (f"📝 <b>{status.capitalize()} заметка</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Имя:</b> #{name}")
    await log_action(message.chat.id, log_text, bot)
    
    await return_to_menu(message, state, get_notes_menu, bot)

@router.message(SettingsStates.waiting_for_note_name_to_delete)
async def process_del_note(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    name = message.text.lower().split()[0]
    if await delete_note(message.chat.id, name):
        await message.answer(f"✅ Заметка `#{name}` удалена.")
        log_text = (f"🗑 <b>Удалена заметка</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Имя:</b> #{name}")
        await log_action(message.chat.id, log_text, bot)
    else:
        await message.answer("Такой заметки не существует.")
        
    await state.clear()
    text, keyboard = await get_notes_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

# --- Обработчики для Триггеров ---
@router.message(SettingsStates.waiting_for_trigger_keyword_to_add)
async def process_add_trigger_keyword(message: types.Message, state: FSMContext):
    await state.update_data(trigger_keyword=message.text.lower())
    await message.delete()
    menu_message_id = (await state.get_data()).get("menu_message_id")
    await bot.edit_message_text("Отлично. Теперь отправьте текст автоматического ответа.", chat_id=message.chat.id, message_id=menu_message_id)
    await state.set_state(SettingsStates.waiting_for_trigger_response)

@router.message(SettingsStates.waiting_for_trigger_response)
async def process_add_trigger_response(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    data = await state.get_data()
    keyword = data['trigger_keyword']
    response = message.html_text
    
    is_new = await add_trigger(message.chat.id, keyword, response)
    triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
    status = "создан" if is_new else "обновлен"
    confirmation_msg = await message.answer(f"✅ Триггер на фразу «{keyword}» успешно {status}.")
    asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))
    
    log_text = (f"🤖 <b>{status.capitalize()} триггер</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Фраза:</b> {html.escape(keyword)}")
    await log_action(message.chat.id, log_text, bot)

    await return_to_menu(message, state, get_triggers_menu, bot)

@router.message(SettingsStates.waiting_for_trigger_keyword_to_delete)
async def process_del_trigger(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    keyword = message.text.lower()
    if await delete_trigger(message.chat.id, keyword):
        triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
        confirmation_msg = await message.answer(f"✅ Триггер на фразу «{keyword}» удален.")
        asyncio.create_task(delete_message_after_delay(confirmation_msg, 5))
        log_text = (f"🗑 <b>Удален триггер</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Фраза:</b> {html.escape(keyword)}")
        await log_action(message.chat.id, log_text, bot)
    else:
        error_msg = await message.answer("Такого триггера не существует.")
        asyncio.create_task(delete_message_after_delay(error_msg, 5))
        
    await return_to_menu(message, state, get_triggers_menu, bot)

@router.callback_query(F.data.startswith("verify_"))
async def callback_verify_user(callback: types.CallbackQuery, bot: Bot):
    chat_id = callback.message.chat.id
    user_id_to_verify = int(callback.data.split("_")[1])
    
    if callback.from_user.id != user_id_to_verify:
        return await callback.answer("Это кнопка не для вас!", show_alert=True)
        
    # Добавляем пользователя в список прошедших проверку
    if chat_id not in VERIFIED_USERS:
        VERIFIED_USERS[chat_id] = set()
    VERIFIED_USERS[chat_id].add(user_id_to_verify)

    try:
        await bot.restrict_chat_member(
            chat_id=callback.message.chat.id,
            user_id=user_id_to_verify,
            permissions=types.ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_other_messages=True, can_add_web_page_previews=True
            )
        )
        # Сначала отвечаем на callback, чтобы убрать "часики"
        await callback.answer()
        
        # Затем удаляем сообщение с капчей
        await callback.message.delete()
        
        # И отправляем приветствие
        settings = await get_chat_settings(callback.message.chat.id)
        welcome_text = settings.get('welcome_message', "Добро пожаловать в чат, {user_mention}!")
        final_text = welcome_text.replace("{user_mention}", callback.from_user.mention_html())
        await bot.send_message(callback.message.chat.id, final_text, parse_mode="HTML")

    except Exception as e:
        await callback.answer("Произошла ошибка. Попросите администратора выдать вам права вручную.", show_alert=True)
        logging.error(f"Ошибка при верификации: {e}")
