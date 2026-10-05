"""Fixtures for tests that need a real PostgreSQL.

Every test runs inside a transaction that is **rolled back at the end**, so nothing a test writes
ever survives — it is safe to run against the real Supabase database. A test that needs to prove
a commit-or-rollback boundary does so with its own throwaway session (see test_session.py).

These tests are skipped, not failed, when no ``DATABASE_URL`` is available, so a machine or CI job
without a database stays green.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from asebe_infrastructure.database.models import ContentItem, PlatformPost, User
from asebe_infrastructure.database.session import create_engine
from asebe_infrastructure.database.settings import get_database_url


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    try:
        get_database_url()
    except RuntimeError:
        pytest.skip("DATABASE_URL is not set")
    engine = create_engine()
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session whose whole transaction is rolled back when the test ends."""
    async with engine.connect() as connection:
        outer = await connection.begin()
        # create_savepoint: even if code under test calls commit(), it only releases a savepoint;
        # the outer transaction is still ours to roll back.
        async with AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        await outer.rollback()


@pytest.fixture
async def platform_post(session: AsyncSession) -> PlatformPost:
    user = User(email=f"test-{uuid.uuid4()}@example.invalid")
    session.add(user)
    await session.flush()
    item = ContentItem(user_id=user.id, title="A test post")
    session.add(item)
    await session.flush()
    post = PlatformPost(content_item_id=item.id, user_id=user.id, platform="platform-1")
    session.add(post)
    await session.flush()
    return post
