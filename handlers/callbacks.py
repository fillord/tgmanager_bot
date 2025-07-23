import html
import logging
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

# ИСПРАВЛЕНИЕ: Импортируем оба кэша из filters.py
from .filters import stop_words_cache, triggers_cache

router = Router()



VERIFIED_USERS = {}

# --- ФАБРИКИ КЛАВИАТУР (Создатели меню) ---

async def get_main_settings_keyboard() -> InlineKeyboardMarkup:
    """Создает главное меню настроек."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛡️ Модерация", callback_data="menu:moderation"),
        InlineKeyboardButton(text="📝 Контент", callback_data="menu:content")
    )
    builder.row(InlineKeyboardButton(text="👋 Приветствие", callback_data="menu:welcome"))
    builder.row(InlineKeyboardButton(text="Закрыть меню", callback_data="menu:close"))
    return builder.as_markup()

async def get_moderation_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    """Создает меню настроек модерации."""
    settings = await get_chat_settings(chat_id)
    antilink_status = "✅ Включена" if settings.get('antilink_enabled', False) else "❌ Выключена"
    captcha_status = "✅ Включена" if settings.get('captcha_enabled', False) else "❌ Выключена"
    captcha_timeout = settings.get('captcha_timeout', 60)
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=f"Лимит варнов: {settings.get('warn_limit', 3)}", callback_data="action:change_warn_limit"))
    builder.add(InlineKeyboardButton(text=f"Защита от ссылок: {antilink_status}", callback_data="action:toggle_antilink"))
    builder.add(InlineKeyboardButton(text=f"CAPTCHA для новичков: {captcha_status}", callback_data="action:toggle_captcha"))
    builder.add(InlineKeyboardButton(text=f"Таймаут CAPTCHA: {captcha_timeout} сек.", callback_data="action:change_captcha_timeout"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    builder.adjust(1)
    return builder.as_markup()

async def get_content_settings_keyboard() -> InlineKeyboardMarkup:
    """Создает меню настроек контента."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚫 Стоп-слова", callback_data="menu:stopwords"),
        InlineKeyboardButton(text="🤖 Триггеры", callback_data="menu:triggers"),
        InlineKeyboardButton(text="🗒️ Заметки", callback_data="menu:notes")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))
    return builder.as_markup()

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

async def get_welcome_menu(chat_id: int):
    """Создает текст и клавиатуру для меню приветствий."""
    settings = await get_chat_settings(chat_id)
    welcome_text = settings.get('welcome_message', "Добро пожаловать в чат, {user_mention}!")
    
    text = (
        "👋 **Управление приветствием**\n\n"
        "Текущее сообщение:\n"
        f"<code>{html.escape(welcome_text)}</code>\n\n"
        "Вы можете использовать плейсхолдер <code>{user_mention}</code> для упоминания нового участника."
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Изменить текст", callback_data="action:change_welcome"))
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


# --- ОБРАБОТЧИКИ НАВИГАЦИИ ПО МЕНЮ ---

@router.callback_query(F.data.startswith("menu:"))
async def handle_menu_navigation(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    menu_type = callback.data.split(":")[1]
    chat_id = callback.message.chat.id

    text, keyboard = "", None
    if menu_type == "main":
        text = "⚙️ **Главное меню настроек**"
        keyboard = await get_main_settings_keyboard()
    elif menu_type == "moderation":
        text = "🛡️ **Настройки модерации**"
        keyboard = await get_moderation_settings_keyboard(chat_id)
    elif menu_type == "content":
        text = "📝 **Настройки контента**"
        keyboard = await get_content_settings_keyboard()
    elif menu_type == "stopwords":
        text, keyboard = await get_stopwords_menu(chat_id)
    elif menu_type == "welcome":
        text, keyboard = await get_welcome_menu(chat_id)
    elif menu_type == "notes":
        text, keyboard = await get_notes_menu(chat_id)
    elif menu_type == "triggers":
        text, keyboard = await get_triggers_menu(chat_id)
    elif menu_type == "close":
        await callback.message.delete()
        return await callback.answer()

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()



# --- ОБРАБОТЧИКИ ДЕЙСТВИЙ ИЗ МЕНЮ (которые запускают FSM) ---

@router.callback_query(F.data.startswith("action:"))
async def handle_menu_actions(callback: types.CallbackQuery, state: FSMContext, bot: Bot, log_action: callable):
    member = await bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return await callback.answer("Это действие доступно только администраторам.", show_alert=True)

    action = callback.data.split(":")[1]
    prompts = {
        "change_warn_limit": ("Пожалуйста, отправьте новое число для лимита предупреждений (например, 3).", SettingsStates.waiting_for_warn_limit),
        "change_captcha_timeout": ("Отправьте новое время в секундах для прохождения капчи (например, 60).", SettingsStates.waiting_for_captcha_timeout),
        "add_stopword": ("Отправьте слово или фразу, которую нужно добавить в черный список.", SettingsStates.waiting_for_stop_word_to_add),
        "del_stopword": ("Отправьте слово или фразу, которую нужно удалить из черного списка.", SettingsStates.waiting_for_stop_word_to_delete),
        "change_welcome": ("Пожалуйста, отправьте новый текст для приветственного сообщения.", SettingsStates.waiting_for_welcome_message),
        "add_note": ("Отправьте имя для новой заметки (одно слово без #).", SettingsStates.waiting_for_note_name_to_add),
        "del_note": ("Отправьте имя заметки, которую нужно удалить (без #).", SettingsStates.waiting_for_note_name_to_delete),
        "add_trigger": ('Отправьте ключевую фразу для нового триггера.', SettingsStates.waiting_for_trigger_keyword_to_add),
        "del_trigger": ('Отправьте ключевую фразу триггера, который нужно удалить.', SettingsStates.waiting_for_trigger_keyword_to_delete),
    }

    if action in prompts:
        prompt_text, new_state = prompts[action]
        await callback.message.edit_text(prompt_text)
        await state.set_state(new_state)
    
    elif action in ["toggle_antilink", "toggle_captcha"]:
        setting_name = "antilink_enabled" if action == "toggle_antilink" else "captcha_enabled"
        settings = await get_chat_settings(callback.message.chat.id)
        new_status = not settings.get(setting_name, False)
        await update_chat_setting(callback.message.chat.id, setting_name, new_status)
        
        setting_name_rus = "Защита от ссылок" if action == "toggle_antilink" else "CAPTCHA"
        status_text = "включена" if new_status else "выключена"
        log_text = (f"⚙️ <b>Изменена настройка: {setting_name_rus}</b>\n"
                    f"<b>Админ:</b> {callback.from_user.mention_html()}\n"
                    f"<b>Новый статус:</b> {status_text}")
        await log_action(callback.message.chat.id, log_text, bot)
        
        new_keyboard = await get_moderation_settings_keyboard(callback.message.chat.id)
        await callback.message.edit_reply_markup(reply_markup=new_keyboard)

    await callback.answer()

# --- ОБРАБОТЧИКИ СОСТОЯНИЙ (FSM) ---
@router.message(SettingsStates.waiting_for_captcha_timeout)
async def process_new_captcha_timeout(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    if not message.text.isdigit() or not (10 <= int(message.text) <= 300):
        return await message.reply("Пожалуйста, введите число от 10 до 300 секунд.")
    
    timeout = int(message.text)
    await update_chat_setting(message.chat.id, 'captcha_timeout', timeout)
    await message.answer(f"✅ Таймаут для капчи изменен на {timeout} секунд.")
    
    # Логирование
    log_text = (f"⚙️ <b>Изменен таймаут CAPTCHA</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новое значение:</b> {timeout} сек.")
    await log_action(message.chat.id, log_text, bot)

    await state.clear()
    keyboard = await get_moderation_settings_keyboard(message.chat.id)
    await message.answer("🛡️ **Настройки модерации**", reply_markup=keyboard)
    
@router.message(SettingsStates.waiting_for_warn_limit)
async def process_new_warn_limit(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    if not message.text.isdigit() or int(message.text) < 1:
        return await message.reply("Пожалуйста, введите целое число больше 0.")
    
    limit = int(message.text)
    await update_chat_setting(message.chat.id, 'warn_limit', limit)
    await message.answer(f"✅ Лимит предупреждений успешно изменен на {hbold(limit)}.", parse_mode="HTML")

    log_text = (f"⚙️ <b>Изменен лимит варнов</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новое значение:</b> {limit}")
    await log_action(message.chat.id, log_text, bot)

    await state.clear()
    
    keyboard = await get_moderation_settings_keyboard(message.chat.id)
    await message.answer("🛡️ **Настройки модерации**", reply_markup=keyboard)

@router.message(SettingsStates.waiting_for_welcome_message)
async def process_new_welcome_message(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    new_text = message.text
    await update_chat_setting(message.chat.id, 'welcome_message', new_text)
    await message.answer("✅ Новое приветственное сообщение установлено.")

    log_text = (f"⚙️ <b>Изменено приветствие</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новый текст:</b>\n<code>{html.escape(new_text)}</code>")
    await log_action(message.chat.id, log_text, bot)
    
    await state.clear()
    
    text, keyboard = await get_welcome_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(SettingsStates.waiting_for_stop_word_to_add)
async def process_add_stop_word(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    word = message.text.lower()
    if await add_stop_word(message.chat.id, word):
        stop_words_cache[message.chat.id] = set(await get_stop_words(message.chat.id))
        await message.answer(f"✅ Слово <code>{html.escape(word)}</code> добавлено.", parse_mode="HTML")
        
        log_text = (f"➕ <b>Добавлено стоп-слово</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Слово:</b> <code>{html.escape(word)}</code>")
        await log_action(message.chat.id, log_text, bot)
    else:
        await message.answer("Это слово уже есть в списке.")
    
    await state.clear()
    text, keyboard = await get_stopwords_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(SettingsStates.waiting_for_stop_word_to_delete)
async def process_del_stop_word(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    word = message.text.lower()
    if await delete_stop_word(message.chat.id, word):
        stop_words_cache[message.chat.id] = set(await get_stop_words(message.chat.id))
        await message.answer(f"✅ Слово <code>{html.escape(word)}</code> удалено.", parse_mode="HTML")
        
        log_text = (f"➖ <b>Удалено стоп-слово</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Слово:</b> <code>{html.escape(word)}</code>")
        await log_action(message.chat.id, log_text, bot)
    else:
        await message.answer("Такого слова нет в списке.")
        
    await state.clear()
    text, keyboard = await get_stopwords_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(SettingsStates.waiting_for_note_name_to_add)
async def process_add_note_name(message: types.Message, state: FSMContext):
    await state.update_data(note_name=message.text.lower().split()[0])
    await message.reply("Отлично. Теперь отправьте содержимое заметки. Можно использовать HTML-разметку.")
    await state.set_state(SettingsStates.waiting_for_note_content)

@router.message(SettingsStates.waiting_for_note_content)
async def process_add_note_content(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    data = await state.get_data()
    name = data['note_name']
    content = message.html_text
    
    is_new = await add_note(message.chat.id, name, content)
    status = "создана" if is_new else "обновлена"
    await message.answer(f"✅ Заметка `#{name}` успешно {status}.")
    
    log_text = (f"📝 <b>{status.capitalize()} заметка</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Имя:</b> #{name}")
    await log_action(message.chat.id, log_text, bot)
    
    await state.clear()
    text, keyboard = await get_notes_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

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
    await message.reply("Отлично. Теперь отправьте текст автоматического ответа.")
    await state.set_state(SettingsStates.waiting_for_trigger_response)

@router.message(SettingsStates.waiting_for_trigger_response)
async def process_add_trigger_response(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    data = await state.get_data()
    keyword = data['trigger_keyword']
    response = message.html_text
    
    is_new = await add_trigger(message.chat.id, keyword, response)
    triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
    status = "создан" if is_new else "обновлен"
    await message.answer(f"✅ Триггер на фразу «{keyword}» успешно {status}.")
    
    log_text = (f"🤖 <b>{status.capitalize()} триггер</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Фраза:</b> {html.escape(keyword)}")
    await log_action(message.chat.id, log_text, bot)

    await state.clear()
    text, keyboard = await get_triggers_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(SettingsStates.waiting_for_trigger_keyword_to_delete)
async def process_del_trigger(message: types.Message, state: FSMContext, bot: Bot, log_action: callable):
    keyword = message.text.lower()
    if await delete_trigger(message.chat.id, keyword):
        triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
        await message.answer(f"✅ Триггер на фразу «{keyword}» удален.")
        log_text = (f"🗑 <b>Удален триггер</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Фраза:</b> {html.escape(keyword)}")
        await log_action(message.chat.id, log_text, bot)
    else:
        await message.answer("Такого триггера не существует.")
        
    await state.clear()
    text, keyboard = await get_triggers_menu(message.chat.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

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
