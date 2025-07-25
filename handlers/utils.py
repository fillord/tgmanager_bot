# handlers/utils.py

from datetime import timedelta
from aiogram import Bot, types
from aiogram.enums import ChatMemberStatus
from aiogram.utils.markdown import hbold

from db.requests import add_warning, count_warnings, get_chat_settings

async def is_admin(message: types.Message, bot: Bot) -> bool:
    """Проверка прав администратора с ответом."""
    if message.chat.type == 'private':
        await message.answer("Эта команда работает только в группах.")
        return False
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        await message.reply("Эту команду могут использовать только администраторы.")
        return False
    return True

async def is_user_admin_silent(chat: types.Chat, user_id: int, bot: Bot) -> bool:
    """Тихая проверка на админа, не отправляет сообщений."""
    member = await bot.get_chat_member(chat.id, user_id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

async def process_warning(message: types.Message, user_to_warn: types.User, bot: Bot, log_action_func: callable):
    """Общая функция для выдачи варна и проверки на бан."""
    chat_id = message.chat.id
    user_id = user_to_warn.id
    
    await add_warning(user_id, chat_id)
    warnings_count = await count_warnings(user_id, chat_id)
    
    settings = await get_chat_settings(chat_id)
    warn_limit = settings.get('warn_limit', 3)
    
    admin_mention = message.from_user.mention_html()
    user_mention = user_to_warn.mention_html()

    if warnings_count >= warn_limit:
        try:
            await bot.ban_chat_member(chat_id, user_id, until_date=timedelta(days=1))
            await message.answer(f"🚫 Пользователь {user_mention} получил {warnings_count} предупреждение и забанен на 1 день.", parse_mode="HTML")
            log_text = (f"🚫 <b>Авто-бан</b>\n<b>Админ:</b> {admin_mention}\n<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n<b>Причина:</b> Достигнут лимит предупреждений ({warnings_count}/{warn_limit})")
            await log_action_func(chat_id, log_text, bot)
        except Exception as e:
            await message.answer(f"Не удалось забанить пользователя {user_mention}. Возможно, у меня недостаточно прав.", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Пользователю {user_mention} вынесено предупреждение ({warnings_count}/{warn_limit}).", parse_mode="HTML")
        log_text = (f"⚠️ <b>Предупреждение</b>\n<b>Админ:</b> {admin_mention}\n<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n<b>Счетчик:</b> {warnings_count}/{warn_limit}")
        await log_action_func(chat_id, log_text, bot)
