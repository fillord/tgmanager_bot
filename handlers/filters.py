# handlers/filters.py

import html
import logging
from aiogram import Router, F, types, Bot
from aiogram.enums import ChatMemberStatus

from db.requests import get_chat_settings, get_stop_words

router = Router()
stop_words_cache = {}

async def is_user_admin_silent(chat: types.Chat, user_id: int, bot: Bot) -> bool:
    """Тихая проверка на админа, не отправляет сообщений."""
    member = await bot.get_chat_member(chat.id, user_id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

@router.message(F.text)
async def message_filter(message: types.Message, bot: Bot, log_action: callable):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_mention = message.from_user.mention_html()
    
    settings = await get_chat_settings(chat_id)
    if settings.get('antilink_enabled', False):
        if not await is_user_admin_silent(message.chat, user_id, bot):
            if message.entities and any(e.type in ['url', 'text_link'] for e in message.entities):
                try:
                    await message.delete()
                    log_text = (f"🗑 <b>Удалено сообщение (ссылка)</b>\n"
                                f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                                f"<b>Сообщение:</b> <code>{html.escape(message.text)}</code>")
                    # ИСПРАВЛЕНИЕ 1: Добавляем 'bot' в вызов
                    await log_action(chat_id, log_text, bot) 
                except Exception as e:
                    logging.error(f"Не удалось удалить сообщение со ссылкой: {e}")
                return

    # Загружаем стоп-слова в кэш, если его нет
    if chat_id not in stop_words_cache:
        words = await get_stop_words(chat_id)
        stop_words_cache[chat_id] = set(words)

    text_lower = message.text.lower()
    for word in stop_words_cache.get(chat_id, set()):
        if word in text_lower:
            try:
                await message.delete()
                # Мы убрали отсюда авто-варн, как вы просили
                log_text = (f"🗑 <b>Удалено сообщение (стоп-слово)</b>\n"
                            f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                            f"<b>Слово:</b> <code>{html.escape(word)}</code>")
                # ИСПРАВЛЕНИЕ 2: Добавляем 'bot' в вызов
                await log_action(chat_id, log_text, bot)
            except Exception as e:
                logging.error(f"Ошибка в фильтре стоп-слов: {e}")
            return