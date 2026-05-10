"""Test fixtures: schema-managed test DB + per-test rollback transactions."""
from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base
# Importing models registers them on Base.metadata for create_all/drop_all.
from app.db import models  # noqa: F401


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    eng = create_async_engine(get_settings().test_database_url, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    """Each test runs in a transaction that gets rolled back."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        SessionFactory = async_sessionmaker(
            bind=conn, expire_on_commit=False, class_=AsyncSession
        )
        async with SessionFactory() as session:
            try:
                yield session
            finally:
                await session.close()
        await trans.rollback()
