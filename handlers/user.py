# handlers/user.py

import html
from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from aiogram.utils.markdown import hbold

from db.requests import (
    get_or_create_user_profile, 
    get_chat_stats, 
    get_user_first_name,
    calculate_xp_for_next_level, # <-- Новый импорт
    get_top_users_by_xp,
    get_all_notes,      # <-- НОВЫЙ ИМПОРТ
    get_all_triggers,
    get_chat_settings    # <-- НОВЫЙ ИМПОРТ
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

@router.message(Command("rank"))
async def cmd_rank(message: types.Message):
    """Показывает текущий уровень и опыт пользователя."""
    profile = await get_or_create_user_profile(message.from_user.id, message.chat.id)
    xp_needed = calculate_xp_for_next_level(profile.level)
    
    text = (
        f"🏆 Ваш ранг\n\n"
        f"<b>Уровень:</b> {profile.level}\n"
        f"<b>Опыт:</b> {profile.xp} / {xp_needed}"
    )
    await message.reply(text, parse_mode="HTML")

@router.message(Command("top"))
async def cmd_top(message: types.Message):
    """Показывает топ-10 самых активных пользователей чата."""
    top_users = await get_top_users_by_xp(message.chat.id, limit=10)
    
    if not top_users:
        return await message.reply("В этом чате пока нет статистики.")

    text = ["🏆 <b>Топ активных пользователей:</b>\n"]
    for i, profile in enumerate(top_users, 1):
        user_name = await get_user_first_name(profile.user_id)
        text.append(f"{i}. {html.escape(user_name)} - {profile.level} уровень ({profile.xp} XP)")
        
    await message.answer("\n".join(text), parse_mode="HTML")

@router.message(Command("notes"))
async def cmd_list_notes(message: types.Message):
    """Показывает список доступных заметок."""
    notes = await get_all_notes(message.chat.id)
    if not notes:
        return await message.reply("В этом чате еще нет заметок.")
    
    text = "📋 <b>Список доступных заметок:</b>\n\n" + "\n".join(
        f"• <code>#{html.escape(note)}</code>" for note in notes
    )
    await message.reply(text, parse_mode="HTML")

@router.message(Command("triggers"))
async def cmd_list_triggers(message: types.Message):
    """Показывает список настроенных триггеров."""
    triggers = await get_all_triggers(message.chat.id)
    if not triggers:
        return await message.reply("В этом чате еще нет триггеров.")
    
    text = "🤖 <b>Список настроенных триггеров:</b>\n\n" + "\n".join(
        f"• <code>{html.escape(keyword)}</code>" for keyword in triggers
    )
    await message.reply(text, parse_mode="HTML")

@router.message(Command("rules"))
async def cmd_rules(message: types.Message):
    """Показывает правила чата."""
    settings = await get_chat_settings(message.chat.id)
    rules_text = settings.get('rules_text', 'Правила в этом чате еще не установлены.')
    await message.reply(rules_text, parse_mode="HTML")
