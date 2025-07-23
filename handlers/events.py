# handlers/events.py
import logging
import asyncio
from datetime import timedelta
from aiogram import Router, F, types, Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.requests import get_chat_settings, add_chat, update_reputation
from .filters import stop_words_cache
# Импортируем наш временный кэш
from .callbacks import VERIFIED_USERS

router = Router()

async def kick_if_not_verified(bot: Bot, chat_id: int, user_id: int, captcha_message_id: int, timeout: int):
    """
    Финальная версия фоновой задачи. Принимает объект 'bot' напрямую.
    """
    logging.info(f"Запущен таймер на {timeout} сек. для user {user_id} в чате {chat_id}.")
    await asyncio.sleep(timeout)
    logging.info(f"Таймер для user {user_id} истек. Проверяем верификацию...")
    
    # Проверяем, есть ли пользователь в списке верифицированных
    if chat_id in VERIFIED_USERS and user_id in VERIFIED_USERS[chat_id]:
        logging.info(f"Пользователь {user_id} прошел проверку. Кик отменен.")
        VERIFIED_USERS[chat_id].discard(user_id)
        if not VERIFIED_USERS[chat_id]:
            del VERIFIED_USERS[chat_id]
        return

    logging.info(f"Пользователь {user_id} НЕ прошел проверку. Попытка кика...")
    try:
        await bot.ban_chat_member(chat_id, user_id, until_date=timedelta(seconds=60))
        await bot.delete_message(chat_id, captcha_message_id)
        logging.info(f"УСПЕХ: Пользователь {user_id} кикнут из чата {chat_id} за не пройденную капчу.")
    except Exception as e:
        logging.error(f"ОШИБКА: Не удалось кикнуть пользователя {user_id} по таймауту: {e}")


@router.message(F.new_chat_members)
async def new_chat_member_handler(message: types.Message, bot: Bot):
    settings = await get_chat_settings(message.chat.id)
    
    bot_obj = await bot.get_me()
    if any(member.id == bot_obj.id for member in message.new_chat_members):
        await add_chat(message.chat.id)
        stop_words_cache[message.chat.id] = set()
        return await message.answer("Спасибо, что добавили меня! Я готов к работе.")

    if not settings.get('captcha_enabled', False):
        welcome_text = settings.get('welcome_message', "Добро пожаловать в чат, {user_mention}!")
        for member in message.new_chat_members:
            final_text = welcome_text.replace("{user_mention}", member.mention_html())
            await message.answer(final_text, parse_mode="HTML")
        return

    captcha_timeout = settings.get('captcha_timeout', 60)
    for member in message.new_chat_members:
        try:
            await bot.restrict_chat_member(
                chat_id=message.chat.id, user_id=member.id,
                permissions=types.ChatPermissions(can_send_messages=False)
            )
            
            keyboard = InlineKeyboardBuilder()
            keyboard.add(InlineKeyboardButton(text="✅ Я не бот", callback_data=f"verify_{member.id}"))
            
            captcha_message = await message.answer(
                f"Добро пожаловать, {member.mention_html()}!\n\n"
                f"Чтобы получить возможность отправлять сообщения, нажмите на кнопку ниже в течение {captcha_timeout} секунд.",
                parse_mode="HTML", reply_markup=keyboard.as_markup()
            )
            
            # ИСПРАВЛЕНИЕ: Передаем 'bot' как первый аргумент в нашу задачу
            asyncio.create_task(
                kick_if_not_verified(bot, message.chat.id, member.id, captcha_message.message_id, captcha_timeout)
            )
        except Exception as e:
            logging.error(f"Не удалось выдать капчу пользователю {member.id}: {e}")

@router.message(F.text.lower().in_({"спасибо", "+", "дякую", "спасибі", "thanks"}))
async def thanks_handler(message: types.Message):
    if not message.reply_to_message:
        return
    
    sender = message.from_user
    recipient = message.reply_to_message.from_user

    if sender.id == recipient.id:
        return
        
    await update_reputation(recipient.id, message.chat.id, 1)
    try:
        await message.reply_to_message.react([types.ReactionTypeEmoji(emoji="👍")])
    except Exception:
        pass

@router.message(F.left_chat_member)
async def left_chat_member_handler(message: types.Message, bot: Bot):
    """
    Обработчик для прощания с ушедшими участниками.
    """
    # Не реагируем на уход самого бота
    bot_obj = await bot.get_me()
    if message.left_chat_member.id == bot_obj.id:
        return

    settings = await get_chat_settings(message.chat.id)
    goodbye_text = settings.get('goodbye_message')

    # Отправляем сообщение, только если оно не пустое
    if goodbye_text:
        final_text = goodbye_text.replace("{user_mention}", message.left_chat_member.mention_html())
        await message.answer(final_text, parse_mode="HTML")
