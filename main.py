import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

# Импортируем наши роутеры, включая новый 'events'
from handlers import user, admin, callbacks, events, note_handler, filters as msg_filters
from middlewares.antiflood import AntiFloodMiddleware
from db.requests import create_tables, upsert_user, get_or_create_user_profile, log_message, get_chat_settings, add_xp, add_chat
from utils.commands import set_bot_commands
logging.basicConfig(level=logging.INFO)

async def log_action(chat_id: int, text: str, bot: Bot):
    """Отправляет лог в установленный для чата канал."""
    settings = await get_chat_settings(chat_id)
    log_channel_id = settings.get('log_channel_id')
    if log_channel_id:
        try:
            await bot.send_message(chat_id=log_channel_id, text=text, parse_mode="HTML")
        except Exception as e:
            logging.error(f"Не удалось отправить лог в канал {log_channel_id}: {e}")

async def on_startup(bot: Bot):
    await create_tables()
    # ВЫЗЫВАЕМ ФУНКЦИЮ УСТАНОВКИ КОМАНД
    await set_bot_commands(bot)
    logging.info("База данных готова к работе")
    logging.info("Команды бота установлены")

async def main():
    storage = MemoryStorage()
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher(storage=storage)

    # Передаем функцию логирования и объект бота во все обработчики через data
    dp['log_action'] = log_action
    dp['bot'] = bot

    # --- MIDDLEWARE ---
    # Этот обработчик будет срабатывать на КАЖДОЕ сообщение
    @dp.message.middleware()
    async def user_register_middleware(handler, event: types.Message, data):
        # Пропускаем команды, чтобы за них не начислялся опыт
        if event.text and event.text.startswith('/'):
            return await handler(event, data)

        bot = data['bot']
        await upsert_user(event.from_user)
        if event.chat.type != 'private':
            # ИСПРАВЛЕНИЕ: Сначала убеждаемся, что чат существует в БД
            await add_chat(event.chat.id)
            
            # Теперь можно безопасно создавать профиль и логировать сообщение
            await get_or_create_user_profile(event.from_user.id, event.chat.id)
            await log_message(event.chat.id, event.from_user.id)
            
            # Начисляем опыт за сообщение
            new_level, leveled_up = await add_xp(event.from_user.id, event.chat.id, 1)
            
            # Если уровень повысился, поздравляем
            if leveled_up:
                await event.answer(f"🎉 Поздравляем {event.from_user.mention_html()}, вы достигли {new_level} уровня!", parse_mode="HTML")

        return await handler(event, data)

    # Регистрируем антифлуд
    dp.message.middleware(AntiFloodMiddleware())

    # Подключаем роутеры
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(callbacks.router)
    dp.include_router(events.router)
    dp.include_router(note_handler.router)
    dp.include_router(msg_filters.router)

    dp.startup.register(on_startup)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
