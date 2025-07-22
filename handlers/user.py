# handlers/user.py

import html
from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.utils.markdown import hbold

from db.requests import (
    get_or_create_user_profile, 
    get_chat_stats, 
    get_user_first_name
)

# Создаем "роутер" для команд пользователей
router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == 'private':
        await message.answer("Привет! Я бот для модерации групп.")

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    stats = await get_chat_stats(message.chat.id)
    
    top_users_text = []
    for i, user in enumerate(stats['top_users'], 1):
        user_id, msg_count = user
        first_name = await get_user_first_name(user_id)
        top_users_text.append(f"{i}. {html.escape(first_name)} - {msg_count} сообщ.")

    text = [
        "📊 <b>Статистика чата</b>\n",
        f"Всего сообщений: <code>{stats['total']}</code>",
        f"Сообщений за 24 часа: <code>{stats['last_24h']}</code>",
        "\n<b>Топ-5 активных пользователей:</b>",
        "\n".join(top_users_text) if top_users_text else "Пока нет данных"
    ]
    await message.answer("\n".join(text), parse_mode="HTML")

@router.message(Command("myrep"))
async def cmd_myrep(message: types.Message):
    profile = await get_or_create_user_profile(message.from_user.id, message.chat.id)
    await message.reply(f"Ваша репутация: {profile.reputation}")

@router.message(Command("userrep"))
async def cmd_userrep(message: types.Message):
    # Эта команда доступна всем, но логичнее ее оставить здесь
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
    
    target_user = message.reply_to_message.from_user
    profile = await get_or_create_user_profile(target_user.id, message.chat.id)
    await message.reply(f"Репутация {hbold(target_user.full_name)}: {profile.reputation}", parse_mode="HTML")
