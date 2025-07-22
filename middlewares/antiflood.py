# middlewares/antiflood.py

import asyncio
import logging
from typing import Callable, Dict, Any, Awaitable
from collections import defaultdict
from datetime import timedelta
import time

from aiogram import BaseMiddleware
from aiogram.types import Message, ChatPermissions

user_messages = defaultdict(lambda: defaultdict(list))

class AntiFloodMiddleware(BaseMiddleware):
    MSG_LIMIT = 5
    TIME_LIMIT_SECONDS = 2
    MUTE_DURATION_MINUTES = 2

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        # Мидлварь зарегистрирован на dp.message, так что event всегда будет Message
        # Проверяем только то, что сообщение пришло из группы
        if event.chat.type not in ('group', 'supergroup'):
            return await handler(event, data)

        chat_id = event.chat.id
        user_id = event.from_user.id
        current_time = time.time()

        # Очищаем список от временных меток, которые старше TIME_LIMIT_SECONDS
        user_messages[chat_id][user_id] = [
            t for t in user_messages[chat_id][user_id] if current_time - t < self.TIME_LIMIT_SECONDS
        ]

        # Добавляем время текущего сообщения
        user_messages[chat_id][user_id].append(current_time)

        # Проверяем, превышен ли лимит
        if len(user_messages[chat_id][user_id]) >= self.MSG_LIMIT:
            # Добавим лог, чтобы точно видеть срабатывание
            logging.info(f"!!! ОБНАРУЖЕН ФЛУД от user_id={user_id} в chat_id={chat_id} !!!")
            try:
                # Сначала выдаем мут
                mute_duration = timedelta(minutes=self.MUTE_DURATION_MINUTES)
                await event.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=mute_duration
                )
                
                # Затем удаляем сообщение, вызвавшее флуд
                await event.delete()
                
                # Отправляем уведомление и планируем его удаление
                msg = await event.answer(
                    f"🔇 Пользователь {event.from_user.mention_html()} замучен на {self.MUTE_DURATION_MINUTES} минут за флуд.",
                    parse_mode="HTML"
                )
                await asyncio.sleep(10)
                await msg.delete()

            except Exception as e:
                logging.error(f"Ошибка в анти-флуде: {e}")
            
            # Останавливаем дальнейшую обработку сообщения
            return
        
        # Если флуда нет, передаем управление дальше
        return await handler(event, data)