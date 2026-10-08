"""The audit log against a real PostgreSQL: complete entries, honest actors, and no rewriting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_infrastructure.database.models import AuditLog
from asebe_infrastructure.repositories import Actor, AuditLogRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 8, 9, 0, tzinfo=UTC)


async def _record(session: AsyncSession, **overrides: object) -> AuditLog:
    fields: dict[str, object] = {
        "actor": Actor.system(),
        "action": "test.changed",
        "resource_type": "thing",
        "resource_id": str(uuid.uuid4()),
        "previous_state": {"status": "A"},
        "new_state": {"status": "B"},
        "now": NOW,
    }
    fields.update(overrides)
    return await AuditLogRepository(session).record(**fields)  # type: ignore[arg-type]


async def test_an_entry_records_who_what_and_the_before_and_after(session: AsyncSession) -> None:
    admin = uuid.uuid4()
    entry = await _record(
        session,
        actor=Actor.user(admin),
        previous_state={"role": "customer"},
        new_state={"role": "moderator"},
        detail={"reason": "promoted"},
    )

    stored = await session.scalar(select(AuditLog).where(AuditLog.id == entry.id))
    assert stored is not None
    assert (stored.actor_type, stored.actor_user_id) == ("user", admin)
    assert stored.previous_state == {"role": "customer"}
    assert stored.new_state == {"role": "moderator"}
    assert stored.detail == {"reason": "promoted"}
    assert stored.occurred_at == NOW


async def test_the_system_actor_carries_no_user_id(session: AsyncSession) -> None:
    entry = await _record(session)

    assert (entry.actor_type, entry.actor_user_id) == ("system", None)
    assert entry.detail == {}


async def test_an_entry_does_not_need_a_previous_or_new_state(session: AsyncSession) -> None:
    entry = await _record(session, previous_state=None, new_state=None, action="user.created")

    assert entry.previous_state is None
    assert entry.new_state is None


async def test_naive_timestamps_are_rejected(session: AsyncSession) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await _record(session, now=datetime(2026, 10, 8, 9, 0))


async def test_the_database_refuses_a_user_actor_with_no_user(session: AsyncSession) -> None:
    async with session.begin_nested():
        session.add(
            AuditLog(
                occurred_at=NOW,
                actor_type="user",
                actor_user_id=None,
                action="x",
                resource_type="thing",
                resource_id="1",
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_the_database_refuses_a_system_actor_that_names_a_user(session: AsyncSession) -> None:
    async with session.begin_nested():
        session.add(
            AuditLog(
                occurred_at=NOW,
                actor_type="system",
                actor_user_id=uuid.uuid4(),
                action="x",
                resource_type="thing",
                resource_id="1",
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_an_entry_cannot_be_updated(session: AsyncSession) -> None:
    entry = await _record(session)

    with pytest.raises(DBAPIError, match="append-only"):
        async with session.begin_nested():
            await session.execute(
                text("UPDATE audit_logs SET action = 'tampered' WHERE id = :id"), {"id": entry.id}
            )


async def test_an_entry_cannot_be_deleted(session: AsyncSession) -> None:
    entry = await _record(session)

    with pytest.raises(DBAPIError, match="append-only"):
        async with session.begin_nested():
            await session.execute(text("DELETE FROM audit_logs WHERE id = :id"), {"id": entry.id})


async def test_the_table_cannot_be_emptied_with_truncate(session: AsyncSession) -> None:
    await _record(session)

    with pytest.raises(DBAPIError, match="append-only"):
        async with session.begin_nested():
            await session.execute(text("TRUNCATE audit_logs"))
