# handlers/events.py
from aiogram import Router, F, types, Bot

from db.requests import (
    get_chat_settings, 
    add_chat, 
    update_reputation
)
# Импортируем кэш из модуля фильтров
from .filters import stop_words_cache

router = Router()

@router.message(F.new_chat_members)
async def new_chat_member_handler(message: types.Message, bot: Bot):
    """
    Обработчик для приветствия новых участников.
    """
    settings = await get_chat_settings(message.chat.id)
    
    # Проверяем, не добавили ли самого бота
    bot_obj = await bot.get_me()
    if any(member.id == bot_obj.id for member in message.new_chat_members):
        await add_chat(message.chat.id)
        # Инициализируем кэш для нового чата
        stop_words_cache[message.chat.id] = set()
        return await message.answer("Спасибо, что добавили меня! Я готов к работе.")

    # Приветствуем обычных пользователей
    welcome_text = settings.get('welcome_message', "Добро пожаловать в чат, {user_mention}!")
    
    for member in message.new_chat_members:
        final_text = welcome_text.replace("{user_mention}", member.mention_html())
        await message.answer(final_text, parse_mode="HTML")

@router.message(F.text.lower().in_({"спасибо", "+", "дякую", "спасибі", "thanks"}))
async def thanks_handler(message: types.Message):
    """
    Обработчик для повышения репутации.
    """
    if not message.reply_to_message:
        return
    
    sender = message.from_user
    recipient = message.reply_to_message.from_user

    # Запрещаем благодарить самого себя
    if sender.id == recipient.id:
        return
        
    await update_reputation(recipient.id, message.chat.id, 1)
    try:
        # Бот ставит реакцию на сообщение, за которое поблагодарили
        await message.reply_to_message.react([types.ReactionTypeEmoji(emoji="👍")])
    except Exception:
        # Если у бота нет прав на установку реакций, он просто проигнорирует это
        pass
