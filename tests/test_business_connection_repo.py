"""TDD tests for BusinessConnectionRepository — written BEFORE implementation.

Why upsert is the primary method: Telegram emits a fresh business_connection
update every time the tutor toggles permissions or disconnects/reconnects.
The connection_id stays stable as long as the connection is active.
"""
from __future__ import annotations

from app.db.repositories.business_connection import BusinessConnectionRepository
from app.db.repositories.tutor import TutorRepository


async def test_upsert_creates_new(db_session):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=42)
    bc_repo = BusinessConnectionRepository(db_session)
    bc = await bc_repo.upsert(
        tutor_id=tutor.id,
        connection_id="conn_abc",
        user_chat_id=42,
        is_enabled=True,
        can_reply=True,
    )
    assert bc.id is not None
    assert bc.connection_id == "conn_abc"
    assert bc.is_enabled is True
    assert bc.can_reply is True


async def test_upsert_updates_existing_in_place(db_session):
    tutor, _ = await TutorRepository(db_session).get_or_create(tg_user_id=99)
    bc_repo = BusinessConnectionRepository(db_session)
    first = await bc_repo.upsert(
        tutor_id=tutor.id,
        connection_id="conn_xyz",
        user_chat_id=99,
        is_enabled=True,
        can_reply=True,
    )
    second = await bc_repo.upsert(
        tutor_id=tutor.id,
        connection_id="conn_xyz",
        user_chat_id=99,
        is_enabled=False,
        can_reply=False,
    )
    assert second.id == first.id
    assert second.is_enabled is False
    assert second.can_reply is False


async def test_get_by_connection_id_returns_none_when_missing(db_session):
    bc_repo = BusinessConnectionRepository(db_session)
    result = await bc_repo.get_by_connection_id("nope")
    assert result is None
