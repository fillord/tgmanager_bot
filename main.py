import asyncio
import os
import logging
import html
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatMemberStatus
from aiogram.utils.markdown import hbold
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.requests import (
    add_chat, create_tables, update_chat_setting, 
    add_stop_word, delete_stop_word, get_stop_words,
    add_warning, count_warnings, get_chat_settings, remove_last_warning,
    upsert_user, get_or_create_user_profile, update_reputation, clear_warnings
)
from utils.time_parser import parse_time

logging.basicConfig(level=logging.INFO)

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
stop_words_cache = {}



@dp.message.middleware()
async def user_register_middleware(handler, event, data):
    # Добавляем или обновляем пользователя в БД
    await upsert_user(event.from_user)
    # Создаем его профиль в чате, если еще нет
    await get_or_create_user_profile(event.from_user.id, event.chat.id)
    return await handler(event, data)

async def on_startup(dispatcher):
    await create_tables()
    # Загружаем стоп-слова в кэш при старте (для уже добавленных чатов)
    # В будущем это можно оптимизировать
    logging.info("База данных готова к работе")

# --- СИСТЕМНЫЕ ОБРАБОТЧИКИ ---
async def log_action(chat_id: int, text: str):
    """Отправляет лог в установленный для чата канал."""
    settings = await get_chat_settings(chat_id)
    log_channel_id = settings.get('log_channel_id')
    if log_channel_id:
        try:
            # Используем parse_mode="HTML", так как он более гибкий
            await bot.send_message(chat_id=log_channel_id, text=text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Не удалось отправить лог в канал {log_channel_id}: {e}")

@dp.message(Command("set_log_channel"))
async def cmd_set_log_channel(message: types.Message):
    if not await is_admin(message): return
    try:
        channel_id = int(message.text.split()[1])
        # Простая проверка, что бот может отправить сообщение в этот канал
        await bot.send_message(channel_id, "Канал для логов успешно подключен.")
        await update_chat_setting(message.chat.id, 'log_channel_id', channel_id)
        await message.answer("✅ Канал для логов успешно установлен.")
    except (IndexError, ValueError):
        await message.answer("Неверный формат. Используйте: /set_log_channel <ID канала>")
    except Exception as e:
        logging.error(e)
        await message.answer("Не удалось подключить канал. Убедитесь, что ID верный и бот добавлен в канал как администратор.")

# --- КОМАНДЫ РЕПУТАЦИИ ---
@dp.message(Command("myrep"))
async def cmd_myrep(message: types.Message):
    profile = await get_or_create_user_profile(message.from_user.id, message.chat.id)
    await message.reply(f"Ваша репутация: {profile.reputation}")

@dp.message(Command("userrep"))
async def cmd_userrep(message: types.Message):
    if not await is_admin(message): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
    
    target_user = message.reply_to_message.from_user
    profile = await get_or_create_user_profile(target_user.id, message.chat.id)
    await message.reply(f"Репутация {hbold(target_user.full_name)}: {profile.reputation}", parse_mode="HTML")

@dp.message(Command("set_welcome"))
async def cmd_set_welcome(message: types.Message):
    if not await is_admin(message): return
    welcome_text = message.text.split(maxsplit=1)
    if len(welcome_text) < 2:
        return await message.reply("Неверный формат.")
    
    text_to_save = welcome_text[1]
    await update_chat_setting(message.chat.id, 'welcome_message', text_to_save)
    await message.answer("✅ Новое приветственное сообщение установлено.")
    
    log_text = (f"⚙️ <b>Изменено приветствие</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Новый текст:</b>\n<code>{html.escape(text_to_save)}</code>")
    await log_action(message.chat.id, log_text)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    if message.chat.type == 'private':
        await message.answer("Привет! Я бот для модерации групп.")

@dp.message(F.new_chat_members)
async def new_chat_member(message: types.Message):
    settings = await get_chat_settings(message.chat.id)

    # Обрабатываем добавление бота
    bot_obj = await bot.get_me()
    if any(member.id == bot_obj.id for member in message.new_chat_members):
        await add_chat(message.chat.id)
        stop_words_cache[message.chat.id] = set()
        return await message.answer("Спасибо, что добавили меня! Я готов к работе.")

    # Приветствуем новых пользователей
    welcome_text = settings.get('welcome_message', "Добро пожаловать в чат, {user_mention}!")

    for member in message.new_chat_members:
        # Заменяем плейсхолдеры
        final_text = welcome_text.replace("{user_mention}", member.mention_html())
        await message.answer(final_text, parse_mode="HTML")

# --- КОМАНДЫ АДМИНИСТРАТОРА ---
async def is_user_admin_silent(chat: types.Chat, user_id: int) -> bool:
    """Тихая проверка на админа, не отправляет сообщений."""
    member = await bot.get_chat_member(chat.id, user_id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}

async def is_admin(message: types.Message) -> bool:
    """Вспомогательная функция для проверки прав администратора."""
    if message.chat.type == 'private':
        await message.answer("Эта команда работает только в группах.")
        return False
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        await message.reply("Эту команду могут использовать только администраторы.")
        return False
    return True

async def get_settings_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    settings = await get_chat_settings(chat_id)
    
    # Текст кнопки зависит от текущего состояния
    antilink_status = "✅ Включена" if settings.get('antilink_enabled', False) else "❌ Выключена"
    
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text=f"Защита от ссылок: {antilink_status}", callback_data="toggle_antilink"),
        # В будущем можно добавить другие кнопки
        # InlineKeyboardButton(text="Изменить лимит варнов", callback_data="change_warn_limit")
    )
    builder.adjust(1) # Располагаем кнопки по одной в строке
    return builder.as_markup()

@dp.message(Command("settings"))
async def cmd_settings(message: types.Message):
    if not await is_admin(message): return

    chat_id = message.chat.id
    settings = await get_chat_settings(chat_id)
    warn_limit = settings.get('warn_limit', 3)
    text = (
        f"⚙️ <b>Настройки чата</b>\n\n"
        f"• Лимит предупреждений: <code>{warn_limit}</code> (изменить: /set_warn_limit &lt;число&gt;)\n"
        f"• Стоп-слова (управление: /add_word, /del_word, /list_words)\n\n"
        f"Нажмите на кнопки ниже, чтобы управлять настройками:"
    )
    keyboard = await get_settings_keyboard(chat_id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(F.data == "toggle_antilink")
async def callback_toggle_antilink(callback: types.CallbackQuery):
    # Проверяем, что нажал админ
    member = await callback.message.chat.get_member(callback.from_user.id)
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        await callback.answer("Это действие доступно только администраторам.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    settings = await get_chat_settings(chat_id)
    current_status = settings.get('antilink_enabled', False)
    new_status = not current_status
    
    await update_chat_setting(chat_id, 'antilink_enabled', new_status)
    
    # Обновляем клавиатуру в существующем сообщении
    new_keyboard = await get_settings_keyboard(chat_id)
    await callback.message.edit_reply_markup(reply_markup=new_keyboard)
    await callback.answer() # Закрываем "часики" на кнопке


async def process_warning(message: types.Message, user_to_warn: types.User):
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
            await message.answer(
                f"🚫 Пользователь {user_mention} получил {warnings_count} предупреждение и забанен на 1 день.",
                parse_mode="HTML"
            )
            log_text = (f"🚫 <b>Авто-бан</b>\n"
                        f"<b>Админ:</b> {admin_mention}\n"
                        f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                        f"<b>Причина:</b> Достигнут лимит предупреждений ({warnings_count}/{warn_limit})")
            await log_action(chat_id, log_text)
        except Exception as e:
            logging.error(f"Не удалось забанить пользователя {user_id} в чате {chat_id}: {e}")
            await message.answer(f"Не удалось забанить пользователя {user_mention}. Возможно, у меня недостаточно прав.", parse_mode="HTML")
    else:
        await message.answer(
            f"⚠️ Пользователю {user_mention} вынесено предупреждение ({warnings_count}/{warn_limit}).",
            parse_mode="HTML"
        )
        log_text = (f"⚠️ <b>Предупреждение</b>\n"
                    f"<b>Админ:</b> {admin_mention}\n"
                    f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                    f"<b>Счетчик:</b> {warnings_count}/{warn_limit}")
        await log_action(chat_id, log_text)


@dp.message(Command("set_warn_limit"))
async def cmd_set_warn_limit(message: types.Message):
    if not await is_admin(message): return
    try:
        limit = int(message.text.split()[1])
        if limit < 1: raise ValueError()
        await update_chat_setting(message.chat.id, 'warn_limit', limit)
        await message.answer(f"✅ Лимит предупреждений изменен на {hbold(limit)}.", parse_mode="HTML")

        log_text = (f"⚙️ <b>Изменен лимит варнов</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Новое значение:</b> {limit}")
        await log_action(message.chat.id, log_text)
    except (IndexError, ValueError):
        await message.answer("Неверный формат.")

@dp.message(Command("warn"))
async def cmd_warn(message: types.Message):
    if not await is_admin(message):
        return await message.reply("Эту команду могут использовать только администраторы.")
    
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение пользователя.")
    
    user_to_warn = message.reply_to_message.from_user
    await process_warning(message, user_to_warn)
    await message.delete() # Удаляем саму команду /warn

@dp.message(Command("unwarn"))
async def cmd_unwarn(message: types.Message):
    if not await is_admin(message): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение пользователя.")

    user_to_unwarn = message.reply_to_message.from_user
    if await remove_last_warning(user_to_unwarn.id, message.chat.id):
        warnings_count = await count_warnings(user_to_unwarn.id, message.chat.id)
        await message.answer(f"✅ Последнее предупреждение для {user_to_unwarn.mention_html()} снято. Текущее количество: {warnings_count}.", parse_mode="HTML")
        
        log_text = (f"✅ <b>Снято предупреждение</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Пользователь:</b> {user_to_unwarn.mention_html()} (<code>{user_to_unwarn.id}</code>)")
        await log_action(message.chat.id, log_text)
    else:
        await message.answer(f"У пользователя {user_to_unwarn.mention_html()} нет предупреждений.", parse_mode="HTML")
    await message.delete()

@dp.message(Command("clearwarns"))
async def cmd_clearwarns(message: types.Message):
    if not await is_admin(message): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")

    target_user = message.reply_to_message.from_user
    await clear_warnings(target_user.id, message.chat.id)
    await message.answer(f"✅ Все предупреждения для пользователя {target_user.mention_html()} были очищены.", parse_mode="HTML")

    log_text = (f"🗑 <b>Очищены предупреждения</b>\n"
                f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                f"<b>Пользователь:</b> {target_user.mention_html()} (<code>{target_user.id}</code>)")
    await log_action(message.chat.id, log_text)

@dp.message(Command("mute"))
async def cmd_mute(message: types.Message):
    if not await is_admin(message): return
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
        await log_action(message.chat.id, log_text)

        await message.delete()
    except Exception as e:
        logging.error(f"Ошибка при муте: {e}")
        await message.reply("Не удалось замутить пользователя.")


@dp.message(Command("unmute"))
async def cmd_unmute(message: types.Message):
    if not await is_admin(message): return
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
    await log_action(message.chat.id, log_text)

    await message.delete()


@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not await is_admin(message): return
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
        await log_action(message.chat.id, log_text)

        await message.delete()
        await message.reply_to_message.delete()
    except Exception as e:
        logging.error(f"Ошибка при бане: {e}")
        await message.reply("Произошла ошибка при выполнении команды.")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not await is_admin(message): return
    if not message.reply_to_message:
        return await message.reply("Эта команда должна быть ответом на сообщение.")
    try:
        user_to_unban = message.reply_to_message.from_user
        await bot.unban_chat_member(chat_id=message.chat.id, user_id=user_to_unban.id)
        await message.answer(f"✅ Пользователь {user_to_unban.mention_html()} успешно разбанен.", parse_mode="HTML")
        
        log_text = (f"✅ <b>Ручной разбан</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Пользователь:</b> {user_to_unban.mention_html()} (<code>{user_to_unban.id}</code>)")
        await log_action(message.chat.id, log_text)

        await message.delete()
    except Exception as e:
        logging.error(f"Ошибка при разбане: {e}")
        await message.reply("Не удалось разбанить пользователя.")


@dp.message(Command("add_word"))
async def cmd_add_word(message: types.Message):
    if not await is_admin(message): return
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
            await log_action(message.chat.id, log_text)
        else:
            await message.answer("Это слово уже есть в списке.")
    except IndexError:
        await message.answer("Неверный формат.")

@dp.message(Command("del_word"))
async def cmd_del_word(message: types.Message):
    if not await is_admin(message): return
    try:
        word = message.text.split(maxsplit=1)[1].lower()
        if await delete_stop_word(message.chat.id, word):
            if message.chat.id in stop_words_cache:
                stop_words_cache[message.chat.id].discard(word)
            await message.answer(f"✅ Слово {hbold(word)} удалено из черного списка.", parse_mode="HTML")

            log_text = (f"➖ <b>Удалено стоп-слово</b>\n"
                        f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                        f"<b>Слово:</b> <code>{html.escape(word)}</code>")
            await log_action(message.chat.id, log_text)
        else:
            await message.answer("Такого слова нет в списке.")
    except IndexError:
        await message.answer("Неверный формат.")


@dp.message(Command("list_words"))
async def cmd_list_words(message: types.Message):
    if not await is_admin(message): return
    words = await get_stop_words(message.chat.id)
    if not words:
        return await message.answer("Черный список слов пуст.")
    
    # Используем стандартную библиотеку html для экранирования
    text = "Текущие стоп-слова:\n\n" + "\n".join(
        f"• <code>{html.escape(word)}</code>" for word in words
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("antilink"))
async def cmd_antilink(message: types.Message):
    if not await is_admin(message): return
    try:
        mode = message.text.split()[1].lower()
        if mode not in ['on', 'off']: raise ValueError
        
        is_enabled = mode == 'on'
        await update_chat_setting(message.chat.id, 'antilink_enabled', is_enabled)
        status = "включена" if is_enabled else "выключена"
        await message.answer(f"✅ Защита от ссылок успешно {status}.")

        log_text = (f"⚙️ <b>Изменена защита от ссылок</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Новый статус:</b> {status}")
        await log_action(message.chat.id, log_text)
    except (IndexError, ValueError):
        await message.answer("Неверный формат.")

@dp.message(F.text.lower().in_({"спасибо", "+", "дякую", "спасибі", "thanks"}))
async def thanks_handler(message: types.Message):
    if not message.reply_to_message:
        return
    
    sender = message.from_user
    recipient = message.reply_to_message.from_user

    if sender.id == recipient.id:
        return await message.reply("Нельзя благодарить самого себя!", show_alert=False)
        
    await update_reputation(recipient.id, message.chat.id, 1)
    await message.reply_to_message.react([types.ReactionTypeEmoji(emoji="👍")])


# --- ФИЛЬТР СООБЩЕНИЙ ---

@dp.message(F.text)
async def message_filter(message: types.Message):
    chat_id = message.chat.id
    user_mention = message.from_user.mention_html()
    user_id = message.from_user.id
    
    # 1. Проверка на ссылки
    settings = await get_chat_settings(chat_id)
    if settings.get('antilink_enabled', False):
        if not await is_user_admin_silent(message.chat, user_id):
            if message.entities and any(e.type in ['url', 'text_link'] for e in message.entities):
                try:
                    await message.delete()
                    log_text = (f"🗑 <b>Удалено сообщение (ссылка)</b>\n"
                                f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                                f"<b>Сообщение:</b> <code>{html.escape(message.text)}</code>")
                    await log_action(chat_id, log_text)
                except Exception as e:
                    logging.error(f"Не удалось удалить сообщение со ссылкой: {e}")
                return

    # 2. Проверка на стоп-слова
    if chat_id not in stop_words_cache:
        words = await get_stop_words(chat_id)
        stop_words_cache[chat_id] = set(words)

    text_lower = message.text.lower()
    for word in stop_words_cache.get(chat_id, set()):
        if word in text_lower:
            try:
                await message.delete()
                log_text = (f"🗑 <b>Удалено сообщение (стоп-слово)</b>\n"
                            f"<b>Пользователь:</b> {user_mention} (<code>{user_id}</code>)\n"
                            f"<b>Слово:</b> <code>{html.escape(word)}</code>")
                await log_action(chat_id, log_text)
            except Exception as e:
                logging.error(f"Ошибка в фильтре стоп-слов: {e}")
            return
        
async def main():
    dp.startup.register(on_startup)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())