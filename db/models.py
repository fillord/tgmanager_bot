from sqlalchemy import Column, BigInteger, String, DateTime, JSON, ForeignKey, Integer
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Chat(Base):
    __tablename__ = "chats"
    chat_id = Column(BigInteger, primary_key=True, index=True)
    settings = Column(JSON, nullable=False, default={
        'welcome_message': 'Приветствуем в чате!',
        'warn_limit': 3,
        'antilink_enabled': False,
        'log_channel_id': None  # <-- НОВАЯ НАСТРОЙКА
    }) 
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class StopWord(Base):
    __tablename__ = "stop_words"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False)
    word = Column(String, nullable=False)

class Warning(Base):
    __tablename__ = "warnings"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False) # Кому выдали
    chat_id = Column(BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class User(Base):
    __tablename__ = "users"
    user_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    chat_id = Column(BigInteger, ForeignKey("chats.chat_id", ondelete="CASCADE"), nullable=False)
    reputation = Column(Integer, default=0, nullable=False)