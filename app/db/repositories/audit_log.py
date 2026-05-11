"""Repository for AuditLog — append-only record of bot actions and decisions."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        tutor_id: int,
        action: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(tutor_id=tutor_id, action=action, payload_json=payload)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def count_for_tutor_by_action(self, *, tutor_id: int, action: str) -> int:
        from sqlalchemy import func

        stmt = select(func.count(AuditLog.id)).where(
            AuditLog.tutor_id == tutor_id, AuditLog.action == action
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_for_tutor(
        self, tutor_id: int, limit: int = 50
    ) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.tutor_id == tutor_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
