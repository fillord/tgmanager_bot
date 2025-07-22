import logging # <-- ДОБАВЛЕН ИМПОРТ
from aiogram import Router, F, types, Bot
# ДОБАВЛЕНЫ ИМПОРТЫ для клавиатуры
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.requests import (
    get_chat_settings, 
    add_chat, 
    update_reputation
)
from .filters import stop_words_cache

router = Router()

@router.message(F.new_chat_members)
async def new_chat_member_handler(message: types.Message, bot: Bot):
    """
    Обработчик для новых участников с логикой CAPTCHA.
    """
    settings = await get_chat_settings(message.chat.id)
    
    # Проверяем, не добавили ли самого бота
    bot_obj = await bot.get_me()
    if any(member.id == bot_obj.id for member in message.new_chat_members):
        await add_chat(message.chat.id)
        stop_words_cache[message.chat.id] = set()
        return await message.answer("Спасибо, что добавили меня! Я готов к работе.")

    # Если CAPTCHA выключена, просто приветствуем
    if not settings.get('captcha_enabled', False):
        welcome_text = settings.get('welcome_message', "Добро пожаловать в чат, {user_mention}!")
        for member in message.new_chat_members:
            final_text = welcome_text.replace("{user_mention}", member.mention_html())
            await message.answer(final_text, parse_mode="HTML")
        return

    # Если CAPTCHA включена
    for member in message.new_chat_members:
        try:
            # Ограничиваем права пользователя (только чтение)
            await bot.restrict_chat_member(
                chat_id=message.chat.id,
                user_id=member.id,
                permissions=types.ChatPermissions(can_send_messages=False)
            )
            
            # Создаем кнопку для верификации
            keyboard = InlineKeyboardBuilder()
            keyboard.add(
                InlineKeyboardButton(
                    text="✅ Я не бот",
                    # В callback_data зашиваем ID пользователя
                    callback_data=f"verify_{member.id}"
                )
            )
            
            # Отправляем сообщение с капчей
            await message.answer(
                f"Добро пожаловать, {member.mention_html()}!\n\n"
                f"Чтобы получить возможность отправлять сообщения, пожалуйста, подтвердите, что вы не бот.",
                parse_mode="HTML",
                reply_markup=keyboard.as_markup()
            )
        except Exception as e:
            logging.error(f"Не удалось выдать капчу пользователю {member.id}: {e}")


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
