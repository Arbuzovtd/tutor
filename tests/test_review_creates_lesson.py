"""Approve callback must land a Lesson row when the original intent was a
reschedule with a concrete new datetime. Without this /today never reflects
what the tutor approved.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from app.bot.routers.review import on_approve, on_reject
from app.db.models import Lesson
from app.db.repositories.audit_log import AuditLogRepository
from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.student import StudentRepository
from app.db.repositories.tutor import TutorRepository


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, *, chat_id, business_connection_id, text):
        self.sent.append({"chat_id": chat_id, "bc": business_connection_id, "text": text})


class _FakeMessage:
    def __init__(self) -> None:
        self.text = "ping"
        self.edits: list[str] = []

    async def edit_text(self, text, reply_markup=None):  # noqa: ARG002
        self.edits.append(text)


class _FakeQuery:
    def __init__(self, data: str, from_user_tg_id: int) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=from_user_tg_id)
        self.bot = _FakeBot()
        self.message = _FakeMessage()
        self.answers: list[str] = []

    async def answer(self, text: str = "") -> None:
        self.answers.append(text)


async def _seed(
    db_session,
    *,
    intent: str,
    new_datetime: datetime | None,
    target_datetime: datetime | None = None,
):
    """Seed a tutor → student → inbound message → pending_review audit row.

    Returns (tutor, student, inbound_id).
    """
    tutor_tg_id = 700_001
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tutor_tg_id)
    tutor.is_registered = True
    conn_id = "conn_lesson_test"
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id=conn_id,
        user_chat_id=12345,
        is_enabled=True,
        can_reply=True,
    )
    student, _ = await StudentRepository(db_session).get_or_create_by_telegram_id(
        tutor_id=tutor.id, telegram_user_id=88_001, telegram_chat_id=88_001
    )
    inbound = await ChatMessageRepository(db_session).record_inbound(
        tutor_id=tutor.id,
        business_connection_id=conn_id,
        telegram_message_id=12001,
        text="перенеси на четверг",
        student_id=student.id,
    )
    await db_session.flush()

    await AuditLogRepository(db_session).log(
        tutor_id=tutor.id,
        action="pending_review",
        payload={
            "chat_message_id": inbound.id,
            "student_id": student.id,
            "intent": intent,
            "confidence": 0.9,
            "target_datetime": target_datetime.isoformat() if target_datetime else None,
            "new_datetime": new_datetime.isoformat() if new_datetime else None,
        },
    )
    await db_session.flush()
    return tutor, student, inbound.id


@pytest.mark.asyncio
async def test_approve_reschedule_with_new_dt_creates_lesson(db_session):
    new_dt = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    tutor, student, inbound_id = await _seed(
        db_session, intent="reschedule", new_datetime=new_dt
    )

    q = _FakeQuery(data=f"approve:{inbound_id}", from_user_tg_id=tutor.telegram_user_id)
    await on_approve(q, db_session)

    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    assert len(lessons) == 1
    lesson = lessons[0]
    assert lesson.tutor_id == tutor.id
    assert lesson.student_id == student.id
    assert lesson.scheduled_at == new_dt
    assert lesson.status == "scheduled"


@pytest.mark.asyncio
async def test_approve_cancel_does_not_create_lesson(db_session):
    new_dt = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    tutor, _, inbound_id = await _seed(
        db_session, intent="cancel", new_datetime=None, target_datetime=new_dt
    )

    q = _FakeQuery(data=f"approve:{inbound_id}", from_user_tg_id=tutor.telegram_user_id)
    await on_approve(q, db_session)

    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    assert lessons == [], "cancel approval must not create a Lesson row"


@pytest.mark.asyncio
async def test_approve_reschedule_without_new_dt_skips_lesson(db_session):
    tutor, _, inbound_id = await _seed(
        db_session, intent="reschedule", new_datetime=None
    )

    q = _FakeQuery(data=f"approve:{inbound_id}", from_user_tg_id=tutor.telegram_user_id)
    await on_approve(q, db_session)

    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    assert lessons == []


@pytest.mark.asyncio
async def test_reject_reschedule_does_not_create_lesson(db_session):
    new_dt = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    tutor, _, inbound_id = await _seed(
        db_session, intent="reschedule", new_datetime=new_dt
    )

    q = _FakeQuery(data=f"reject:{inbound_id}", from_user_tg_id=tutor.telegram_user_id)
    await on_reject(q, db_session)

    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    assert lessons == [], "reject path must never create a Lesson"


@pytest.mark.asyncio
async def test_approve_with_naive_datetime_falls_back_to_utc(db_session):
    """If the audit payload somehow stored a tz-naive ISO string, the approve
    path must coerce to UTC before writing to lessons.scheduled_at (which is
    TIMESTAMP WITH TIME ZONE)."""
    naive = datetime(2026, 5, 16, 15, 0)  # no tzinfo
    tutor, student, inbound_id = await _seed(
        db_session, intent="reschedule", new_datetime=naive
    )

    q = _FakeQuery(data=f"approve:{inbound_id}", from_user_tg_id=tutor.telegram_user_id)
    await on_approve(q, db_session)

    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    assert len(lessons) == 1
    assert lessons[0].scheduled_at == naive.replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_approve_picks_most_recent_pending_review(db_session):
    """If a chat_message_id ended up with multiple pending_review rows for any
    reason, the latest one wins — that's the state the tutor was looking at."""
    earlier_dt = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
    later_dt = datetime(2026, 5, 17, 18, 0, tzinfo=timezone.utc)

    tutor, student, inbound_id = await _seed(
        db_session, intent="reschedule", new_datetime=earlier_dt
    )
    # second pending_review for same chat_message_id, different new_dt
    await AuditLogRepository(db_session).log(
        tutor_id=tutor.id,
        action="pending_review",
        payload={
            "chat_message_id": inbound_id,
            "student_id": student.id,
            "intent": "reschedule",
            "confidence": 0.95,
            "new_datetime": later_dt.isoformat(),
        },
    )
    await db_session.flush()

    q = _FakeQuery(data=f"approve:{inbound_id}", from_user_tg_id=tutor.telegram_user_id)
    await on_approve(q, db_session)

    lessons = (await db_session.execute(select(Lesson))).scalars().all()
    assert len(lessons) == 1
    assert lessons[0].scheduled_at == later_dt
