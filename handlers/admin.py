# handlers/admin.py

import html
from datetime import timedelta
from aiogram import Router, Bot, types
from aiogram.filters import Command
from aiogram.enums import ChatMemberStatus
from aiogram.utils.markdown import hbold
from aiogram.types import ChatPermissions

from db.requests import (
    update_chat_setting, add_warning, count_warnings, get_chat_settings, 
    remove_last_warning, clear_warnings, add_stop_word, delete_stop_word, 
    get_stop_words, get_or_create_user_profile, count_user_messages
)
from utils.time_parser import parse_time
from .callbacks import get_settings_keyboard
from .utils import is_admin 
from .filters import stop_words_cache
router = Router()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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

# --- КОМАНДЫ ---

@router.message(Command("settings"))
async def cmd_settings(message: types.Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    settings = await get_chat_settings(chat_id)
    user_warnings = await count_warnings(user_id, chat_id)
    warn_limit = settings.get('warn_limit', 3)
    text = (f"⚙️ <b>Настройки чата и ваш профиль</b>\n\n"
            f"• Ваши предупреждения: <code>{user_warnings} / {warn_limit}</code>\n"
            f"• Лимит предупреждений в чате: <code>{warn_limit}</code>\n\n"
            f"Нажмите на кнопки ниже, чтобы управлять настройками (только для админов):")
    keyboard = await get_settings_keyboard(chat_id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("warn"))
async def cmd_warn(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
    user_to_warn = message.reply_to_message.from_user
    await process_warning(message, user_to_warn, bot, log_action)
    await message.delete()

@router.message(Command("unwarn"))
async def cmd_unwarn(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")

    user_to_unwarn = message.reply_to_message.from_user
    if await remove_last_warning(user_to_unwarn.id, message.chat.id):
        warnings_count = await count_warnings(user_to_unwarn.id, message.chat.id)
        await message.answer(f"✅ Последнее предупреждение для {user_to_unwarn.mention_html()} снято. Текущее количество: {warnings_count}.", parse_mode="HTML")
        
        log_text = (f"✅ <b>Снято предупреждение</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Пользователь:</b> {user_to_unwarn.mention_html()} (<code>{user_to_unwarn.id}</code>)")
        await log_action(message.chat.id, log_text, bot)
    else:
        await message.answer(f"У пользователя {user_to_unwarn.mention_html()} нет предупреждений.", parse_mode="HTML")
    await message.delete()

@router.message(Command("clearwarns"))
async def cmd_clearwarns(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")

    target_user = message.reply_to_message.from_user
    await clear_warnings(target_user.id, message.chat.id)
    await message.answer(f"✅ Все предупреждения для пользователя {target_user.mention_html()} были очищены.", parse_mode="HTML")

    log_text = (f"🗑 <b>Очищены предупреждения</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Пользователь:</b> {target_user.mention_html()} (<code>{target_user.id}</code>)")
    await log_action(message.chat.id, log_text, bot)

@router.message(Command("mute"))
async def cmd_mute(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
    try:
        args = message.text.split()
        user_to_mute = message.reply_to_message.from_user
        time_str = args[1] if len(args) > 1 else "1h"
        duration = parse_time(time_str)
        if not duration:
            return await message.reply("Неверный формат времени.")
        
        await bot.restrict_chat_member(
            chat_id=message.chat.id,
            user_id=user_to_mute.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=duration
        )
        await message.answer(f"🔇 Пользователь {user_to_mute.mention_html()} замучен на {time_str}.", parse_mode="HTML")

        log_text = (f"🔇 <b>Мут</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Пользователь:</b> {user_to_mute.mention_html()} (<code>{user_to_mute.id}</code>)\n"
                    f"<b>Срок:</b> {time_str}")
        await log_action(message.chat.id, log_text, bot)

        await message.delete()
    except Exception as e:
        await message.reply("Не удалось замутить пользователя.")


@router.message(Command("unmute"))
async def cmd_unmute(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
        
    user_to_unmute = message.reply_to_message.from_user
    await bot.restrict_chat_member(
        chat_id=message.chat.id,
        user_id=user_to_unmute.id,
        permissions=ChatPermissions(
            can_send_messages=True, can_send_media_messages=True,
            can_send_other_messages=True, can_add_web_page_previews=True
        )
    )
    await message.answer(f"🔊 Пользователь {user_to_unmute.mention_html()} размучен.", parse_mode="HTML")

    log_text = (f"🔊 <b>Размут</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Пользователь:</b> {user_to_unmute.mention_html()} (<code>{user_to_unmute.id}</code>)")
    await log_action(message.chat.id, log_text, bot)

    await message.delete()


@router.message(Command("ban"))
async def cmd_ban(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")

    try:
        args = message.text.split()
        user_to_ban = message.reply_to_message.from_user
        time_str = args[1] if len(args) > 1 else "1d"
        reason = " ".join(args[2:]) if len(args) > 2 else "без указания причины"
        duration = parse_time(time_str)
        if not duration:
            return await message.reply("Неверный формат времени.")
        
        await bot.ban_chat_member(message.chat.id, user_to_ban.id, until_date=duration)
        await message.answer(
            f"🚫 Пользователь {user_to_ban.mention_html()} забанен.\n"
            f"<b>Срок:</b> {time_str}\n"
            f"<b>Причина:</b> {reason}",
            parse_mode="HTML"
        )
        log_text = (f"🚫 <b>Ручной бан</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Пользователь:</b> {user_to_ban.mention_html()} (<code>{user_to_ban.id}</code>)\n"
                    f"<b>Срок:</b> {time_str}\n"
                    f"<b>Причина:</b> {html.escape(reason)}")
        await log_action(message.chat.id, log_text, bot)

        await message.delete()
        await message.reply_to_message.delete()
    except Exception as e:
        await message.reply("Произошла ошибка при выполнении команды.")

@router.message(Command("unban"))
async def cmd_unban(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
    try:
        user_to_unban = message.reply_to_message.from_user
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=user_to_unban.id)
        await message.answer(f"✅ Пользователь {user_to_unban.mention_html()} успешно разбанен.", parse_mode="HTML")
        
        log_text = (f"✅ <b>Ручной разбан</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Пользователь:</b> {user_to_unban.mention_html()} (<code>{user_to_unban.id}</code>)")
        await log_action(message.chat.id, log_text, bot)

        await message.delete()
    except Exception as e:
        await message.reply("Не удалось разбанить пользователя.")

@router.message(Command("add_word"))
async def cmd_add_word(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        word = message.text.split(maxsplit=1)[1].lower()
        if await add_stop_word(message.chat.id, word):
            # ИСПРАВЛЕНИЕ: Обновляем кэш
            if message.chat.id not in stop_words_cache:
                stop_words_cache[message.chat.id] = set()
            stop_words_cache[message.chat.id].add(word)

            await message.answer(f"✅ Слово {hbold(word)} добавлено в черный список.", parse_mode="HTML")
            log_text = (f"➕ <b>Добавлено стоп-слово</b>\n"
                        f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                        f"<b>Слово:</b> <code>{html.escape(word)}</code>")
            await log_action(message.chat.id, log_text, bot)
        else:
            await message.answer("Это слово уже есть в списке.")
    except IndexError:
        await message.answer("Неверный формат.")

@router.message(Command("del_word"))
async def cmd_del_word(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        word = message.text.split(maxsplit=1)[1].lower()
        if await delete_stop_word(message.chat.id, word):
            # ИСПРАВЛЕНИЕ: Обновляем кэш
            if message.chat.id in stop_words_cache:
                stop_words_cache[message.chat.id].discard(word)

            await message.answer(f"✅ Слово {hbold(word)} удалено из черного списка.", parse_mode="HTML")
            log_text = (f"➖ <b>Удалено стоп-слово</b>\n"
                        f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                        f"<b>Слово:</b> <code>{html.escape(word)}</code>")
            await log_action(message.chat.id, log_text, bot)
        else:
            await message.answer("Такого слова нет в списке.")
    except IndexError:
        await message.answer("Неверный формат.")

@router.message(Command("list_words"))
async def cmd_list_words(message: types.Message, bot: Bot):
    if not await is_admin(message, bot): return
    words = await get_stop_words(message.chat.id)
    if not words:
        return await message.answer("Черный список слов пуст.")
    text = "Текущие стоп-слова:\n\n" + "\n".join(f"• <code>{html.escape(word)}</code>" for word in words)
    await message.answer(text, parse_mode="HTML")

@router.message(Command("set_welcome"))
async def cmd_set_welcome(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    welcome_text = message.text.split(maxsplit=1)
    if len(welcome_text) < 2:
        return await message.reply("Неверный формат.")
    
    text_to_save = welcome_text[1]
    await update_chat_setting(message.chat.id, 'welcome_message', text_to_save)
    await message.answer("✅ Новое приветственное сообщение установлено.")
    
    log_text = (f"⚙️ <b>Изменено приветствие</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новый текст:</b>\n<code>{html.escape(text_to_save)}</code>")
    await log_action(message.chat.id, log_text, bot)

@router.message(Command("info"))
async def cmd_info(message: types.Message, bot: Bot):
    if not await is_admin(message, bot): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение пользователя.")

    target_user = message.reply_to_message.from_user
    chat_id = message.chat.id
    profile = await get_or_create_user_profile(target_user.id, chat_id)
    warnings_count = await count_warnings(target_user.id, chat_id)
    message_count = await count_user_messages(target_user.id, chat_id)
    text = [
        f"👤 <b>Информация о пользователе:</b> {target_user.mention_html()}",
        f"<b>ID:</b> <code>{target_user.id}</code>",
        f"<b>Репутация:</b> {profile.reputation}",
        f"<b>Предупреждения:</b> {warnings_count}",
        f"<b>Всего сообщений:</b> {message_count}"
    ]
    await message.answer("\n".join(text), parse_mode="HTML")
