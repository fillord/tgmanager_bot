# handlers/admin.py

import html
import logging # <-- ДОБАВЛЕН ИМПОРТ
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
from .callbacks import get_main_settings_keyboard
from .utils import is_admin 
from .filters import stop_words_cache
router = Router()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

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
async def cmd_settings(message: types.Message, bot: Bot):
    if not await is_admin(message, bot): return
    
    keyboard = await get_main_settings_keyboard(message.chat.id)
    text = "PARAMETRY\n<b>Группа:</b> {chat_title}\n\nВыберите один из параметров, который вы хотите изменить.".format(chat_title=html.escape(message.chat.title))
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("set_log_channel"))
async def cmd_set_log_channel(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        # Команда выглядит как /set_log_channel -100123456789
        channel_id_str = message.text.split()[1]
        if not (channel_id_str.startswith('-100') and channel_id_str[1:].isdigit()):
             raise ValueError("ID канала должен быть отрицательным числом, начинающимся с -100.")
        
        channel_id = int(channel_id_str)
        
        # Простая проверка, что бот может отправить сообщение в этот канал
        await bot.send_message(channel_id, "Канал для логов успешно подключен.")
        
        await update_chat_setting(message.chat.id, 'log_channel_id', channel_id)
        await message.answer("✅ Канал для логов успешно установлен.")
        
        log_text = (f"⚙️ <b>Установлен канал для логов</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>ID канала:</b> <code>{channel_id}</code>")
        await log_action(message.chat.id, log_text, bot)

    except (IndexError, ValueError):
        await message.answer("Неверный формат. Используйте: /set_log_channel <ID канала>\nID канала должен быть отрицательным числом, например, -100123456789.")
    except Exception as e:
        logging.error(f"Ошибка при подключении канала логов: {e}")
        await message.answer("Не удалось подключить канал. Убедитесь, что ID верный и бот добавлен в канал как администратор с правом публикации сообщений.")

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
