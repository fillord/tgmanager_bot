from aiogram.fsm.state import State, StatesGroup

class Settings(StatesGroup):
    waiting_for_warn_limit = State()