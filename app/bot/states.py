"""FSM state groups for tutor onboarding."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    waiting_subjects = State()
    waiting_grades = State()
    waiting_working_hours = State()
    waiting_price = State()
