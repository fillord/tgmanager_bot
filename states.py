# states.py
from aiogram.fsm.state import State, StatesGroup

class SettingsStates(StatesGroup):
    # Состояния для настроек
    waiting_for_warn_limit = State()
    waiting_for_captcha_timeout = State()
    
    # Состояния для контента
    waiting_for_welcome_message = State()
    waiting_for_rules_text = State()
    waiting_for_goodbye_message = State()

    # Состояния для стоп-слов
    waiting_for_stop_word_to_add = State()
    waiting_for_stop_word_to_delete = State()
    
    # Состояния для триггеров
    waiting_for_trigger_keyword_to_add = State()
    waiting_for_trigger_response = State()
    waiting_for_trigger_keyword_to_delete = State()

    # Состояния для заметок
    waiting_for_note_name_to_add = State()
    waiting_for_note_content = State()
    waiting_for_note_name_to_delete = State()
