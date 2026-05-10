"""Cheap regex pre-filter — decides if a message is worth sending to GPT.

Generous by design: false positives cost ~$0.005/msg, false negatives miss
a reschedule. When in doubt, pass through.
"""
from __future__ import annotations

# Stems chosen to match conjugated forms ("перенести", "перенос", "переноса", etc.).
_SCHEDULING_STEMS = (
    "перенес", "перенос", "пересен", "передвин",
    "отмен", "замен", "поменя",
    "не смог", "не получ", "не приду", "не буду", "не успе",
    "опазд", "болен", "болею", "заболе",
    "урок", "занят",
)

_DAY_STEMS = (
    "понедельник", "вторник", "сред", "четверг", "пятниц",
    "суббот", "воскрес",
    "пн ", "вт ", "ср ", "чт ", "пт ", "сб ", "вс ",
)

_TIME_TOKENS = (":", "час", "утра", "вечер", " дня", " ночи", "00", "30", "15", "45")

_RELATIVE = ("завтра", "послезавтра", "сегодня", "следующ", "ближайш", "через")


def is_scheduling_message(text: str) -> bool:
    """True if the message is plausibly about scheduling and worth GPT-parsing.

    Conservative: anything with a time/day/scheduling stem passes. Pure greetings
    and topic-irrelevant chatter return False so the engine can skip GPT entirely.
    """
    if not text or not text.strip():
        return False
    lo = text.lower()
    return (
        any(s in lo for s in _SCHEDULING_STEMS)
        or any(s in lo for s in _DAY_STEMS)
        or any(s in lo for s in _RELATIVE)
        or any(s in lo for s in _TIME_TOKENS)
    )
