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

    async def count_pending_review_unresolved(self, *, tutor_id: int) -> int:
        """Count 'pending_review' audit rows whose chat_message_id has no later
        'approved' or 'rejected' row. This is the live backlog the tutor still
        needs to act on.
        """
        from sqlalchemy import and_, func, not_, or_

        pending = AuditLog.__table__.alias("pending")
        resolution = AuditLog.__table__.alias("res")

        # Subquery: chat_message_ids that have been resolved for this tutor.
        resolved_msg_ids = (
            select(resolution.c.payload_json["chat_message_id"].astext)
            .where(
                resolution.c.tutor_id == tutor_id,
                resolution.c.action.in_(("approved", "rejected")),
            )
        ).scalar_subquery()

        stmt = select(func.count(pending.c.id)).where(
            pending.c.tutor_id == tutor_id,
            pending.c.action == "pending_review",
            not_(pending.c.payload_json["chat_message_id"].astext.in_(resolved_msg_ids)),
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def get_latest_pending_review(
        self, *, tutor_id: int, chat_message_id: int
    ) -> AuditLog | None:
        """Return the most recent pending_review audit row for this inbound
        message, if any. Used by the approve handler to recover the parsed
        intent and datetimes captured at the moment we pinged the tutor.
        """
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.tutor_id == tutor_id,
                AuditLog.action == "pending_review",
                AuditLog.payload_json["chat_message_id"].astext == str(chat_message_id),
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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
