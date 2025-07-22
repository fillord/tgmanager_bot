# handlers/utils.py

from aiogram import Bot, types
from aiogram.enums import ChatMemberStatus

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
