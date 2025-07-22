import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

# Импортируем наши роутеры, включая новый 'events'
from handlers import user, admin, callbacks, events, filters as msg_filters
from middlewares.antiflood import AntiFloodMiddleware
from db.requests import create_tables, upsert_user, get_or_create_user_profile, log_message, get_chat_settings

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
    logging.info("База данных готова к работе")

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
        await upsert_user(event.from_user)
        if event.chat.type != 'private':
            await get_or_create_user_profile(event.from_user.id, event.chat.id)
            await log_message(event.chat.id, event.from_user.id)
        return await handler(event, data)

    # Регистрируем антифлуд
    dp.message.middleware(AntiFloodMiddleware())

    # Подключаем роутеры
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(callbacks.router)
    dp.include_router(events.router)
    # Фильтры должны идти последними, чтобы не перехватывать команды
    dp.include_router(msg_filters.router)

    # Регистрируем функцию on_startup
    dp.startup.register(on_startup)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
