"""Writing to the audit log.

``record`` is deliberately the only operation. Reading the log is an administrator feature with its
own permission check (``admin.audit_logs.view``) and belongs with that work, not here; and there is
no update or delete because the table refuses both (see ``database/models/audit.py``).

Like every repository here it never commits (R9). That is the property that matters most: the audit
entry is written in the *same transaction* as the change it describes, so the two exist together or
not at all. A status change with no record, or a record of a change that rolled back, are both
impossible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from asebe_infrastructure.database.models.audit import ACTOR_SYSTEM, ACTOR_USER, AuditLog


@dataclass(frozen=True, slots=True)
class Actor:
    """Who did it: a signed-in person, or the system acting on its own."""

    type: str
    user_id: uuid.UUID | None = None

    @classmethod
    def system(cls) -> Actor:
        return cls(ACTOR_SYSTEM, None)

    @classmethod
    def user(cls, user_id: uuid.UUID) -> Actor:
        return cls(ACTOR_USER, user_id)


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        actor: Actor,
        action: str,
        resource_type: str,
        resource_id: str,
        previous_state: dict[str, Any] | None,
        new_state: dict[str, Any] | None,
        now: datetime,
        detail: dict[str, Any] | None = None,
    ) -> AuditLog:
        if now.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (use UTC)")
        entry = AuditLog(
            occurred_at=now,
            actor_type=actor.type,
            actor_user_id=actor.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            previous_state=previous_state,
            new_state=new_state,
            detail=detail or {},
        )
        self._session.add(entry)
        await self._session.flush()
        return entry


__all__ = ["Actor", "AuditLogRepository"]
