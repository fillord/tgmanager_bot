# handlers/filters.py

import html
import logging
from aiogram import Router, F, types, Bot

from db.requests import get_chat_settings, get_stop_words, get_all_triggers
# ИМПОРТИРУЕМ ИЗ ПРАВИЛЬНОГО МЕСТА
from .utils import is_user_admin_silent

router = Router()

# --- ЦЕНТРАЛЬНОЕ ХРАНИЛИЩЕ КЭШЕЙ ---
# Оба кэша теперь определены здесь, чтобы избежать циклических импортов.
stop_words_cache = {}
triggers_cache = {}


@router.message(F.text)
async def message_filter(message: types.Message, bot: Bot, log_action: callable):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_mention = message.from_user.mention_html()
    text_lower = message.text.lower()
    
    # --- 1. Проверка на триггеры ---
    if chat_id not in triggers_cache:
        triggers_cache[chat_id] = await get_all_triggers(chat_id)
    
    for keyword, response in triggers_cache.get(chat_id, {}).items():
        if keyword in text_lower:
            await message.reply(response, parse_mode="HTML")
            return # Если сработал триггер, дальше не проверяем

    # --- 2. Проверка на ссылки ---
    settings = await get_chat_settings(chat_id)
    if settings.get('antilink_enabled', False):
        if not await is_user_admin_silent(message.chat, user_id, bot):
            if message.entities and any(e.type in ['url', 'text_link'] for e in message.entities):
                try:
                    await message.delete()
                    log_text = (f"🗑 <b>Удалено сообщение (ссылка)</b>\n"
                                f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                                f"<b>Сообщение:</b> <code>{html.escape(message.text)}</code>")
                    await log_action(chat_id, log_text, bot) 
                except Exception as e:
                    logging.error(f"Не удалось удалить сообщение со ссылкой: {e}")
                return

    # --- 3. Проверка на стоп-слова ---
    if chat_id not in stop_words_cache:
        words = await get_stop_words(chat_id)
        stop_words_cache[chat_id] = set(words)

    for word in stop_words_cache.get(chat_id, set()):
        if word in text_lower:
            try:
                await message.delete()
                log_text = (f"🗑 <b>Удалено сообщение (стоп-слово)</b>\n"
                            f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                            f"<b>Слово:</b> <code>{html.escape(word)}</code>")
                await log_action(chat_id, log_text, bot)
            except Exception as e:
                logging.error(f"Ошибка в фильтре стоп-слов: {e}")
            return