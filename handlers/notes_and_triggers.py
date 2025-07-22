# handlers/notes_and_triggers.py

import html
from aiogram import Router, F, types, Bot
from aiogram.filters import Command

from db.requests import (
    add_note, delete_note, get_note, get_all_notes,
    add_trigger, delete_trigger, get_all_triggers
)
# ИМПОРТИРУЕМ ИЗ НОВОГО ФАЙЛА
from .utils import is_admin

router = Router()
# Кэш для триггеров, чтобы не обращаться к БД на каждое сообщение
triggers_cache = {}

# --- ЗАМЕТКИ (NOTES) ---

@router.message(Command("addnote"))
async def cmd_add_note(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        parts = message.text.split(maxsplit=2)
        name = parts[1].lower()
        content = parts[2]
        is_new = await add_note(message.chat.id, name, content)
        status = "создана" if is_new else "обновлена"
        await message.reply(f"✅ Заметка `#{name}` успешно {status}.")
        log_text = (f"📝 <b>{status.capitalize()} заметка</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Имя:</b> #{name}")
        await log_action(message.chat.id, log_text, bot)
    except IndexError:
        await message.reply("Неверный формат. Используйте: /addnote <имя> <содержимое>")

@router.message(Command("delnote"))
async def cmd_del_note(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        name = message.text.split(maxsplit=1)[1].lower()
        if await delete_note(message.chat.id, name):
            await message.reply(f"✅ Заметка `#{name}` удалена.")
            log_text = (f"🗑 <b>Удалена заметка</b>\n"
                        f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                        f"<b>Имя:</b> #{name}")
            await log_action(message.chat.id, log_text, bot)
        else:
            await message.reply("Такой заметки не существует.")
    except IndexError:
        await message.reply("Неверный формат. Используйте: /delnote <имя>")

@router.message(Command("notes"))
async def cmd_list_notes(message: types.Message):
    notes = await get_all_notes(message.chat.id)
    if not notes:
        return await message.reply("В этом чате еще нет заметок.")
    text = "📋 **Список доступных заметок:**\n" + "\n".join(f"• `#{note}`" for note in notes)
    await message.reply(text, parse_mode="MarkdownV2")

@router.message(F.text.startswith("#"))
async def handle_note_call(message: types.Message):
    note_name = message.text[1:].lower().split()[0]
    if not note_name: return

    note_content = await get_note(message.chat.id, note_name)
    if note_content:
        # СНАЧАЛА отправляем ответ
        if message.reply_to_message:
            # Если это ответ на другое сообщение, отвечаем на него
            await message.reply_to_message.reply(note_content, parse_mode="HTML")
        else:
            # Если это новое сообщение, просто отправляем в чат
            await message.answer(note_content, parse_mode="HTML")
        
        # ПОТОМ удаляем команду
        try:
            await message.delete()
        except Exception:
            pass

# --- ТРИГГЕРЫ (TRIGGERS) ---

@router.message(Command("addtrigger"))
async def cmd_add_trigger(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        parts = message.text.split('"')
        keyword = parts[1].lower()
        response = parts[3]
        is_new = await add_trigger(message.chat.id, keyword, response)
        triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
        status = "создан" if is_new else "обновлен"
        await message.reply(f"✅ Триггер на фразу «{keyword}» успешно {status}.")
        log_text = (f"🤖 <b>{status.capitalize()} триггер</b>\n"
                    f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                    f"<b>Фраза:</b> {html.escape(keyword)}")
        await log_action(message.chat.id, log_text, bot)
    except IndexError:
        await message.reply('Неверный формат. Используйте: /addtrigger "ключевая фраза" "ответ"')

@router.message(Command("deltrigger"))
async def cmd_del_trigger(message: types.Message, bot: Bot, log_action: callable):
    if not await is_admin(message, bot): return
    try:
        keyword = message.text.split('"')[1].lower()
        if await delete_trigger(message.chat.id, keyword):
            triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
            await message.reply(f"✅ Триггер на фразу «{keyword}» удален.")
            log_text = (f"🗑 <b>Удален триггер</b>\n"
                        f"<b>Админ:</b> {message.from_user.mention_html()}\n"
                        f"<b>Фраза:</b> {html.escape(keyword)}")
            await log_action(message.chat.id, log_text, bot)
        else:
            await message.reply("Такого триггера не существует.")
    except IndexError:
        await message.reply('Неверный формат. Используйте: /deltrigger "ключевая фраза"')

@router.message(Command("triggers"))
async def cmd_list_triggers(message: types.Message):
    if message.chat.id not in triggers_cache:
        triggers_cache[message.chat.id] = await get_all_triggers(message.chat.id)
    triggers = triggers_cache[message.chat.id]
    if not triggers:
        return await message.reply("В этом чате еще нет триггеров.")
    text = "📋 **Список настроенных триггеров:**\n" + "\n".join(f"• «`{html.escape(keyword)}`»" for keyword in triggers)
    await message.reply(text, parse_mode="HTML")
