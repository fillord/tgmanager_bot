# handlers/note_handler.py
from aiogram import Router, F, types
from db.requests import get_note

router = Router()

@router.message(F.text.startswith("#"))
async def handle_note_call(message: types.Message):
    # Извлекаем имя заметки из сообщения, например, из "#rules" получаем "rules"
    note_name = message.text[1:].lower().split()[0]
    if not note_name:
        return

    note_content = await get_note(message.chat.id, note_name)
    
    # Если заметка с таким именем найдена, отправляем ее содержимое
    if note_content:
        # Определяем, на какое сообщение отвечать
        target_message = message.reply_to_message or message
        try:
            # Сначала отвечаем
            await target_message.reply(note_content, parse_mode="HTML")
            # Потом удаляем команду вызова
            await message.delete()
        except Exception:
            # Если не удалось удалить (например, нет прав), просто игнорируем
            pass
