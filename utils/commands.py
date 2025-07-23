# utils/commands.py
from aiogram import Bot
# ИСПРАВЛЕНИЕ: Используем правильное имя класса
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeAllChatAdministrators

async def set_bot_commands(bot: Bot):
    """
    Устанавливает списки команд для разных категорий пользователей.
    """
    # --- Команды для обычных пользователей (видны в личных сообщениях и по умолчанию в группах) ---
    user_commands = [
        BotCommand(command="start", description="▶️ Запустить бота"),
        BotCommand(command="stats", description="📊 Статистика чата"),
        BotCommand(command="myrep", description="⭐ Моя репутация"),
        BotCommand(command="rank", description="🏆 Мой ранг и опыт"),
        BotCommand(command="top", description="👑 Топ пользователей"),
        BotCommand(command="notes", description="🗒️ Список заметок"),
        BotCommand(command="triggers", description="🤖 Список триггеров"),
    ]
    await bot.set_my_commands(commands=user_commands, scope=BotCommandScopeDefault())

    # --- Команды, которые видят только администраторы групп ---
    admin_commands = [
        BotCommand(command="settings", description="⚙️ Открыть меню настроек"),
        BotCommand(command="info", description="ℹ️ Инфо о пользователе (ответом)"),
        BotCommand(command="warn", description="⚠️ Выдать варн (ответом)"),
        BotCommand(command="mute", description="🔇 Замутить (ответом)"),
        BotCommand(command="ban", description="🚫 Забанить (ответом)"),
        BotCommand(command="unban", description="✅ Разбанить (ответом)"),
        BotCommand(command="unmute", description="🔊 Размутить (ответом)"),
        BotCommand(command="clearwarns", description="🗑️ Снять все варны (ответом)"),
    ]
    # ИСПРАВЛЕНИЕ: Используем правильное имя класса
    await bot.set_my_commands(commands=user_commands + admin_commands, scope=BotCommandScopeAllChatAdministrators())
