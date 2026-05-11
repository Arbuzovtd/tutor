"""Tests for callback authorization in app.bot.routers.review.

We stub aiogram's CallbackQuery / Bot to verify the auth check rejects
cross-tenant attempts without actually hitting Telegram.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from app.bot.routers.review import _resolve
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


async def _seed_pending_message(
    db_session, *, tutor_tg_id: int, conn_id: str = "conn_rev"
):
    """Returns (tutor, student, inbound_chat_msg)."""
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tutor_tg_id)
    tutor.is_registered = True
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id=conn_id,
        user_chat_id=999,
        is_enabled=True,
        can_reply=True,
    )
    student, _ = await StudentRepository(
        db_session
    ).get_or_create_by_telegram_id(
        tutor_id=tutor.id, telegram_user_id=55555, telegram_chat_id=55555
    )
    inbound = await ChatMessageRepository(db_session).record_inbound(
        tutor_id=tutor.id,
        business_connection_id=conn_id,
        telegram_message_id=999,
        text="перенеси на четверг",
        student_id=student.id,
    )
    await db_session.flush()
    return tutor, student, inbound


async def test_resolve_rejects_unknown_clicker(db_session):
    tutor, _, inbound = await _seed_pending_message(db_session, tutor_tg_id=11001)
    # Clicker has no tutor row at all
    query = _FakeQuery(data=f"approve:{inbound.id}", from_user_tg_id=999_999)
    await _resolve(query, db_session, action="approved", reply_text="ok")
    assert query.answers == ["Нет доступа."]
    assert query.bot.sent == []


async def test_resolve_rejects_cross_tenant_clicker(db_session):
    """Tutor B tries to approve Tutor A's review — must be blocked."""
    tutor_a, _, inbound = await _seed_pending_message(
        db_session, tutor_tg_id=11002, conn_id="conn_a"
    )
    tutor_b, _ = await TutorRepository(db_session).get_or_create(tg_user_id=11003)
    tutor_b.is_registered = True
    await db_session.flush()

    query = _FakeQuery(data=f"approve:{inbound.id}", from_user_tg_id=11003)
    await _resolve(query, db_session, action="approved", reply_text="ok")
    assert query.answers == ["Это не ваша задача."]
    assert query.bot.sent == []

    # Unauthorized attempt must be audit-logged
    from sqlalchemy import select

    from app.db.models import AuditLog

    audits = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "unauthorized_review_attempt")
        )
    ).scalars().all()
    assert len(audits) == 1
    assert audits[0].tutor_id == tutor_b.id
    assert audits[0].payload_json["reason"] == "cross_tenant"


async def test_resolve_happy_path_sends_reply(db_session):
    tutor, student, inbound = await _seed_pending_message(
        db_session, tutor_tg_id=11004, conn_id="conn_ok"
    )
    query = _FakeQuery(data=f"approve:{inbound.id}", from_user_tg_id=11004)
    await _resolve(query, db_session, action="approved", reply_text="OK сделаю")

    assert len(query.bot.sent) == 1
    sent = query.bot.sent[0]
    assert sent["chat_id"] == student.telegram_chat_id
    assert sent["bc"] == "conn_ok"
    assert sent["text"] == "OK сделаю"


async def test_resolve_rejects_garbage_callback_data(db_session):
    await _seed_pending_message(db_session, tutor_tg_id=11005)
    query = _FakeQuery(data="approve:abc", from_user_tg_id=11005)
    await _resolve(query, db_session, action="approved", reply_text="ok")
    assert query.answers == ["Некорректный идентификатор."]


async def test_resolve_rejects_huge_id(db_session):
    await _seed_pending_message(db_session, tutor_tg_id=11006)
    query = _FakeQuery(data="approve:999999999999", from_user_tg_id=11006)
    await _resolve(query, db_session, action="approved", reply_text="ok")
    assert query.answers == ["Некорректный идентификатор."]
