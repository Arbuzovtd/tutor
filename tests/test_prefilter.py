"""Pre-filter unit tests — each example is a real-world phrasing we want to (or not) GPT-parse."""
from __future__ import annotations

import pytest

from app.ai.prefilter import is_scheduling_message


@pytest.mark.parametrize(
    "text",
    [
        "можно перенести среду 17:00 на пятницу?",
        "Не смогу завтра в 17, давайте на четверг",
        "перенесите урок пожалуйста",
        "болею, отменим занятие",
        "опаздываю на 10 минут",
        "хочу поменять время с понедельника на вторник",
        "пятница 18:00 удобно?",
        "сегодня в 19 не получится",
        "следующая неделя свободна?",
    ],
)
def test_passes_scheduling_messages(text: str):
    assert is_scheduling_message(text)


@pytest.mark.parametrize(
    "text",
    [
        "привет",
        "спасибо большое",
        "ок",
        "hi",
        "",
        "   ",
    ],
)
def test_filters_non_scheduling(text: str):
    assert not is_scheduling_message(text)
