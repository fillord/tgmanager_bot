import os
from aiogram import types
from sqlalchemy import update, select, delete, func as sql_func, text, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

from db.models import Base, Chat, StopWord, Warning, User, UserProfile, Message, Note, Trigger
from datetime import datetime, timedelta

db_url = (
    f"postgresql+asyncpg://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@"
    f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
)

engine = create_async_engine(db_url)

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def add_chat(chat_id: int):
    """Добавляет новый чат в базу данных."""
    async with engine.connect() as conn:
        stmt = pg_insert(Chat).values(chat_id=chat_id) # <-- Исправлено
        stmt = stmt.on_conflict_do_nothing(index_elements=['chat_id'])
        await conn.execute(stmt)
        await conn.commit()
        
async def update_chat_setting(chat_id: int, setting_name: str, value):
    async with engine.connect() as conn:
        current_settings_result = await conn.execute(
            Chat.__table__.select().where(Chat.chat_id == chat_id)
        )
        current_settings = current_settings_result.first()
        
        if current_settings:
            settings_dict = dict(current_settings.settings)
            settings_dict[setting_name] = value
            
            stmt = (
                update(Chat)
                .where(Chat.chat_id == chat_id)
                .values(settings=settings_dict)
            )
            await conn.execute(stmt)
            await conn.commit()

# --- Функции для системы уровней (XP) ---

def calculate_xp_for_next_level(level: int) -> int:
    """Формула для расчета необходимого опыта для следующего уровня."""
    return 5 * (level ** 2) + 50 * level + 100

async def add_xp(user_id: int, chat_id: int, amount: int) -> tuple[int, bool]:
    """
    Добавляет опыт пользователю и проверяет, не повысился ли уровень.
    Возвращает (новый уровень, флаг повышения уровня).
    """
    async with engine.connect() as conn:
        profile = await get_or_create_user_profile(user_id, chat_id)
        
        current_level = profile.level
        new_xp = profile.xp + amount
        xp_needed = calculate_xp_for_next_level(current_level)
        
        leveled_up = False
        while new_xp >= xp_needed:
            current_level += 1
            new_xp -= xp_needed
            xp_needed = calculate_xp_for_next_level(current_level)
            leveled_up = True

        stmt = update(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.chat_id == chat_id
        ).values(level=current_level, xp=new_xp)
        
        await conn.execute(stmt)
        await conn.commit()
        
        return current_level, leveled_up

async def get_top_users_by_xp(chat_id: int, limit: int = 10):
    """Получает топ пользователей по уровню и опыту."""
    async with engine.connect() as conn:
        stmt = select(UserProfile).where(UserProfile.chat_id == chat_id).order_by(
            UserProfile.level.desc(),
            UserProfile.xp.desc()
        ).limit(limit)
        
        result = await conn.execute(stmt)
        return result.all()

async def add_stop_word(chat_id: int, word: str):
    """Добавляет стоп-слово для конкретного чата."""
    async with engine.connect() as conn:
        # Проверяем, может слово уже есть
        existing = await conn.execute(
            select(StopWord).where(StopWord.chat_id == chat_id, StopWord.word == word)
        )
        if existing.first():
            return False # Слово уже есть

        stmt = insert(StopWord).values(chat_id=chat_id, word=word)
        await conn.execute(stmt)
        await conn.commit()
        return True # Слово успешно добавлено

async def delete_stop_word(chat_id: int, word: str):
    """Удаляет стоп-слово для конкретного чата."""
    async with engine.connect() as conn:
        stmt = delete(StopWord).where(StopWord.chat_id == chat_id, StopWord.word == word)
        result = await conn.execute(stmt)
        await conn.commit()
        return result.rowcount > 0 # Возвращает True, если что-то было удалено

async def get_stop_words(chat_id: int):
    """Получает список всех стоп-слов для чата."""
    async with engine.connect() as conn:
        stmt = select(StopWord.word).where(StopWord.chat_id == chat_id)
        result = await conn.execute(stmt)
        return [row.word for row in result.all()]
    
async def add_warning(user_id: int, chat_id: int):
    """Добавляет предупреждение пользователю."""
    async with engine.connect() as conn:
        stmt = insert(Warning).values(user_id=user_id, chat_id=chat_id)
        await conn.execute(stmt)
        await conn.commit()

async def count_warnings(user_id: int, chat_id: int):
    """Считает количество предупреждений у пользователя."""
    async with engine.connect() as conn:
        stmt = select(sql_func.count()).select_from(Warning).where(
            Warning.user_id == user_id,
            Warning.chat_id == chat_id
        )
        result = await conn.execute(stmt)
        return result.scalar_one()
    
async def remove_last_warning(user_id: int, chat_id: int):
    """Удаляет одно последнее предупреждение у пользователя."""
    async with engine.connect() as conn:
        # Находим ID последнего предупреждения для данного пользователя в чате
        subq = select(Warning.id).where(
            Warning.user_id == user_id,
            Warning.chat_id == chat_id
        ).order_by(Warning.created_at.desc()).limit(1).scalar_subquery()

        # Удаляем запись с этим ID
        stmt = delete(Warning).where(Warning.id.in_(subq))
        result = await conn.execute(stmt)
        await conn.commit()
        return result.rowcount > 0

async def clear_warnings(user_id: int, chat_id: int):
    """Удаляет все предупреждения у пользователя в чате."""
    async with engine.connect() as conn:
        stmt = delete(Warning).where(
            Warning.user_id == user_id,
            Warning.chat_id == chat_id
        )
        await conn.execute(stmt)
        await conn.commit()

async def upsert_user(user: types.User):
    """Добавляет или обновляет информацию о пользователе в таблице users."""
    async with engine.connect() as conn:
        stmt = pg_insert(User).values(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        # При конфликте (пользователь уже есть) - обновляем его данные
        stmt = stmt.on_conflict_do_update(
            index_elements=['user_id'],
            set_={
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
        )
        await conn.execute(stmt)
        await conn.commit()

async def get_or_create_user_profile(user_id: int, chat_id: int) -> UserProfile:
    """Получает или создает профиль пользователя в чате."""
    async with engine.connect() as conn:
        # Сначала ищем профиль
        stmt_select = select(UserProfile).where(UserProfile.user_id == user_id, UserProfile.chat_id == chat_id)
        result = await conn.execute(stmt_select)
        profile = result.first()
        
        if profile:
            return profile

        # Если профиля нет, создаем его
        stmt_insert = pg_insert(UserProfile).values(user_id=user_id, chat_id=chat_id, reputation=0)
        await conn.execute(stmt_insert)
        await conn.commit()

        # Повторно запрашиваем, чтобы получить созданный профиль
        result = await conn.execute(stmt_select)
        return result.first()

async def update_reputation(user_id: int, chat_id: int, amount: int):
    """Обновляет репутацию пользователя."""
    async with engine.connect() as conn:
        stmt = update(UserProfile).where(
            UserProfile.user_id == user_id,
            UserProfile.chat_id == chat_id
        ).values(reputation=UserProfile.reputation + amount)
        await conn.execute(stmt)
        await conn.commit()

async def log_message(chat_id: int, user_id: int):
    """Записывает каждое новое сообщение в БД для статистики."""
    async with engine.connect() as conn:
        stmt = pg_insert(Message).values(chat_id=chat_id, user_id=user_id)
        await conn.execute(stmt)
        await conn.commit()

async def get_chat_stats(chat_id: int):
    """Собирает статистику по чату."""
    async with engine.connect() as conn:
        # Общее количество сообщений
        total_stmt = select(sql_func.count(Message.id)).where(Message.chat_id == chat_id)
        total_messages = (await conn.execute(total_stmt)).scalar_one()

        # Сообщения за 24 часа
        day_ago = datetime.utcnow() - timedelta(days=1)
        day_stmt = select(sql_func.count(Message.id)).where(
            Message.chat_id == chat_id,
            Message.timestamp >= day_ago
        )
        day_messages = (await conn.execute(day_stmt)).scalar_one()

        # Топ-5 активных пользователей
        top_users_stmt = select(
            Message.user_id,
            sql_func.count(Message.id).label('msg_count')
        ).where(Message.chat_id == chat_id).group_by(Message.user_id).order_by(sql_func.count(Message.id).desc()).limit(5)
        
        top_users_result = await conn.execute(top_users_stmt)
        top_users = top_users_result.all()

        return {
            "total": total_messages,
            "last_24h": day_messages,
            "top_users": top_users
        }
        
async def get_user_first_name(user_id: int) -> str:
    """Получает имя пользователя по его ID."""
    async with engine.connect() as conn:
        stmt = select(User.first_name).where(User.user_id == user_id)
        result = await conn.execute(stmt)
        user = result.first()
        return user.first_name if user else f"User {user_id}"

async def count_user_messages(user_id: int, chat_id: int):
    """Считает общее количество сообщений от пользователя в чате."""
    async with engine.connect() as conn:
        stmt = select(sql_func.count(Message.id)).where(
            Message.user_id == user_id,
            Message.chat_id == chat_id
        )
        result = await conn.execute(stmt)
        return result.scalar_one()

async def add_note(chat_id: int, name: str, content: str) -> bool:
    """Добавляет или обновляет заметку."""
    async with engine.connect() as conn:
        stmt_select = select(Note).where(Note.chat_id == chat_id, Note.name == name)
        existing_note = (await conn.execute(stmt_select)).first()
        if existing_note:
            stmt_update = update(Note).where(Note.id == existing_note.id).values(content=content)
            await conn.execute(stmt_update)
        else:
            stmt_insert = pg_insert(Note).values(chat_id=chat_id, name=name, content=content)
            await conn.execute(stmt_insert)
        await conn.commit()
        return not existing_note

async def delete_note(chat_id: int, name: str) -> bool:
    """Удаляет заметку."""
    async with engine.connect() as conn:
        stmt = delete(Note).where(Note.chat_id == chat_id, Note.name == name)
        result = await conn.execute(stmt)
        await conn.commit()
        return result.rowcount > 0

async def get_note(chat_id: int, name: str):
    """Получает одну заметку."""
    async with engine.connect() as conn:
        stmt = select(Note.content).where(Note.chat_id == chat_id, Note.name == name)
        return (await conn.execute(stmt)).scalar_one_or_none()

async def get_all_notes(chat_id: int):
    """Получает все заметки в чате."""
    async with engine.connect() as conn:
        stmt = select(Note.name).where(Note.chat_id == chat_id).order_by(Note.name)
        return [row.name for row in (await conn.execute(stmt)).all()]

# --- Функции для Триггеров (Triggers) ---

async def add_trigger(chat_id: int, keyword: str, response: str) -> bool:
    """Добавляет или обновляет триггер."""
    async with engine.connect() as conn:
        stmt_select = select(Trigger).where(Trigger.chat_id == chat_id, Trigger.keyword == keyword)
        existing = (await conn.execute(stmt_select)).first()
        if existing:
            await conn.execute(update(Trigger).where(Trigger.id == existing.id).values(response=response))
        else:
            await conn.execute(pg_insert(Trigger).values(chat_id=chat_id, keyword=keyword, response=response))
        await conn.commit()
        return not existing

async def delete_trigger(chat_id: int, keyword: str) -> bool:
    """Удаляет триггер."""
    async with engine.connect() as conn:
        stmt = delete(Trigger).where(Trigger.chat_id == chat_id, Trigger.keyword == keyword)
        result = await conn.execute(stmt)
        await conn.commit()
        return result.rowcount > 0

async def get_all_triggers(chat_id: int) -> dict:
    """Получает все триггеры в чате в виде словаря."""
    async with engine.connect() as conn:
        stmt = select(Trigger.keyword, Trigger.response).where(Trigger.chat_id == chat_id)
        result = await conn.execute(stmt)
        return {row.keyword: row.response for row in result.all()}

async def get_chat_settings(chat_id: int):
    """Получает все настройки для чата."""
    async with engine.connect() as conn:
        stmt = select(Chat.settings).where(Chat.chat_id == chat_id)
        result = await conn.execute(stmt)
        settings = result.scalar_one_or_none()
        return settings if settings else {}