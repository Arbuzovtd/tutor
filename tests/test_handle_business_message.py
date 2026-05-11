"""TDD tests for handle_business_message service — Phase 5 entry point.

Cycle 1: idempotency + connection-not-found guard. No parser/calendar yet.
Subsequent cycles will layer in student identification, handoff detection,
intent routing, and calendar actions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.chat_message import ChatMessageRepository
from app.db.repositories.tutor import TutorRepository
from app.services.reschedule import HandleResult, handle_business_message


NOW = datetime(2026, 5, 11, 12, 0, tzinfo=timezone.utc)


async def _make_connected_tutor(db_session, *, tg_id: int, conn_id: str, chat_id: int = 999):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=tg_id)
    tutor.is_registered = True
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id=conn_id,
        user_chat_id=chat_id,
        is_enabled=True,
        can_reply=True,
    )
    await db_session.flush()
    return tutor


async def test_unknown_connection_returns_silent_ignore(db_session):
    """If business_connection isn't in DB, service stays silent (no crash)."""
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_never_seen",
        telegram_message_id=1,
        from_user_id=555,
        chat_id=555,
        text="привет",
        now=NOW,
    )
    assert result == HandleResult(action="unknown_connection", reply_text=None)


async def test_unregistered_tutor_is_silent(db_session):
    """Bot must not reply while tutor is mid-onboarding (is_registered=False)."""
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=7001)
    # Note: is_registered stays default False
    await BusinessConnectionRepository(db_session).upsert(
        tutor_id=tutor.id,
        connection_id="conn_unreg",
        user_chat_id=42,
        is_enabled=True,
        can_reply=True,
    )
    await db_session.flush()

    result = await handle_business_message(
        session=db_session,
        connection_id="conn_unreg",
        telegram_message_id=2,
        from_user_id=42,
        chat_id=42,
        text="hi",
        now=NOW,
    )
    assert result.reply_text is None
    assert result.action == "unregistered_tutor"


async def test_duplicate_message_is_idempotent(db_session):
    """Second delivery of same Telegram message returns silent ignore, no new row."""
    tutor = await _make_connected_tutor(db_session, tg_id=7002, conn_id="conn_dup")
    msg_repo = ChatMessageRepository(db_session)
    # Simulate the first delivery already persisted.
    await msg_repo.record_inbound(
        tutor_id=tutor.id,
        business_connection_id="conn_dup",
        telegram_message_id=77,
        text="перенеси на завтра",
    )

    result = await handle_business_message(
        session=db_session,
        connection_id="conn_dup",
        telegram_message_id=77,
        from_user_id=12345,
        chat_id=12345,
        text="перенеси на завтра",
        now=NOW,
    )
    assert result == HandleResult(action="duplicate_ignored", reply_text=None)


async def test_first_message_persists_inbound_record(db_session):
    """A fresh message must be persisted as direction='inbound' before any other branching."""
    tutor = await _make_connected_tutor(db_session, tg_id=7003, conn_id="conn_fresh")
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_fresh",
        telegram_message_id=88,
        from_user_id=22222,
        chat_id=22222,
        text="привет",
        now=NOW,
    )
    # Action is "received" for cycle 1; later cycles will branch to reschedule/cancel/etc.
    assert result.action == "received"
    # The inbound record must exist now.
    assert (
        await ChatMessageRepository(db_session).exists_by_telegram_msg("conn_fresh", 88)
        is True
    )


async def test_first_message_creates_student_and_links_chat_message(db_session):
    """Cycle 2: fresh from_user_id materializes a Student, ChatMessage.student_id links it."""
    from sqlalchemy import select

    from app.db.models import ChatMessage, Student

    tutor = await _make_connected_tutor(db_session, tg_id=7004, conn_id="conn_stu")
    await handle_business_message(
        session=db_session,
        connection_id="conn_stu",
        telegram_message_id=100,
        from_user_id=33333,
        chat_id=33333,
        text="hello",
        now=NOW,
    )
    student = (
        await db_session.execute(
            select(Student).where(Student.telegram_user_id == 33333)
        )
    ).scalar_one()
    assert student.tutor_id == tutor.id

    chat_msg = (
        await db_session.execute(
            select(ChatMessage).where(
                ChatMessage.business_connection_id == "conn_stu",
                ChatMessage.telegram_message_id == 100,
            )
        )
    ).scalar_one()
    assert chat_msg.student_id == student.id


async def test_tutor_self_message_recorded_as_outbound_tutor(db_session):
    """Cycle 3: if from_user_id == tutor.telegram_user_id, the tutor typed it themselves."""
    from sqlalchemy import select

    from app.db.models import ChatMessage

    tutor = await _make_connected_tutor(db_session, tg_id=8001, conn_id="conn_self")
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_self",
        telegram_message_id=300,
        from_user_id=8001,
        chat_id=12345,
        text="спасибо, разберусь сам",
        now=NOW,
    )
    assert result.action == "tutor_outbound"
    assert result.reply_text is None
    msg = (
        await db_session.execute(
            select(ChatMessage).where(ChatMessage.business_connection_id == "conn_self")
        )
    ).scalar_one()
    assert msg.direction == "outbound_tutor"


async def _seed_outbound_at(
    db_session, *, tutor_id: int, connection_id: str, direction: str, at: datetime
):
    """Helper: insert an outbound row with a specific received_at."""
    msg = await ChatMessageRepository(db_session).record_outbound(
        tutor_id=tutor_id,
        business_connection_id=connection_id,
        text="seeded",
        direction=direction,
    )
    msg.received_at = at
    await db_session.flush()


async def test_inbound_silent_after_recent_tutor_outbound(db_session):
    """Cycle 3: within 60-min window of tutor typing, bot must stay silent."""
    tutor = await _make_connected_tutor(db_session, tg_id=8002, conn_id="conn_ho1")
    await _seed_outbound_at(
        db_session,
        tutor_id=tutor.id,
        connection_id="conn_ho1",
        direction="outbound_tutor",
        at=NOW - timedelta(minutes=30),
    )
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_ho1",
        telegram_message_id=301,
        from_user_id=55555,
        chat_id=55555,
        text="ок, спасибо",
        now=NOW,
    )
    assert result.action == "tutor_handoff"
    assert result.reply_text is None


async def test_inbound_proceeds_after_old_tutor_outbound(db_session):
    """Cycle 3: past 60-min window, bot resumes normal handling."""
    tutor = await _make_connected_tutor(db_session, tg_id=8003, conn_id="conn_ho2")
    await _seed_outbound_at(
        db_session,
        tutor_id=tutor.id,
        connection_id="conn_ho2",
        direction="outbound_tutor",
        at=NOW - timedelta(minutes=90),
    )
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_ho2",
        telegram_message_id=302,
        from_user_id=66666,
        chat_id=66666,
        text="вопрос",
        now=NOW,
    )
    assert result.action == "received"


async def test_recent_bot_outbound_does_not_trigger_handoff(db_session):
    """Cycle 3: only outbound_tutor counts as handoff; bot's own outbound is irrelevant."""
    tutor = await _make_connected_tutor(db_session, tg_id=8004, conn_id="conn_ho3")
    await _seed_outbound_at(
        db_session,
        tutor_id=tutor.id,
        connection_id="conn_ho3",
        direction="outbound_bot",
        at=NOW - timedelta(minutes=5),
    )
    result = await handle_business_message(
        session=db_session,
        connection_id="conn_ho3",
        telegram_message_id=303,
        from_user_id=77777,
        chat_id=77777,
        text="ок",
        now=NOW,
    )
    assert result.action == "received"


async def test_second_message_from_same_user_reuses_student(db_session):
    """Cycle 2: don't duplicate Student for the same (tutor_id, telegram_user_id)."""
    from sqlalchemy import func, select

    from app.db.models import Student

    tutor = await _make_connected_tutor(db_session, tg_id=7005, conn_id="conn_stu2")
    for msg_id in (200, 201):
        await handle_business_message(
            session=db_session,
            connection_id="conn_stu2",
            telegram_message_id=msg_id,
            from_user_id=44444,
            chat_id=44444,
            text=f"msg{msg_id}",
            now=NOW,
        )
    count = (
        await db_session.execute(
            select(func.count(Student.id)).where(
                Student.tutor_id == tutor.id, Student.telegram_user_id == 44444
            )
        )
    ).scalar_one()
    assert count == 1
