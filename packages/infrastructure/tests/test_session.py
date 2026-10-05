"""R9's foundation: a transaction rolls back completely when its block raises."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from asebe_infrastructure.database.models import User
from asebe_infrastructure.database.session import create_session_factory, transaction

pytestmark = pytest.mark.integration


async def test_an_exception_inside_a_transaction_rolls_everything_back(
    engine: AsyncEngine,
) -> None:
    factory = create_session_factory(engine)
    email = f"rollback-{uuid.uuid4()}@example.invalid"

    with pytest.raises(RuntimeError, match="boom"):
        async with transaction(factory) as session:
            session.add(User(email=email))
            await session.flush()  # written inside the transaction...
            raise RuntimeError("boom")  # ...then the block fails

    async with factory() as check:
        count = await check.scalar(
            select(func.count()).select_from(User).where(User.email == email)
        )
    assert count == 0
