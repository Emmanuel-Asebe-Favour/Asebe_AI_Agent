"""Engine and transaction management.

The rule this module exists to uphold is R9: a state change and the job that follows it commit in
**one** transaction. That only works if the transaction belongs to the *caller*, not to the
repository. So repositories in this package never open, commit or roll back anything — they are
handed an open session and write into it. This module is where a transaction begins and ends.

``transaction()`` is the receptionist: it opens a session, starts a transaction, hands the session
to the caller, then commits if the block finished normally or rolls everything back if it raised.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from asebe_infrastructure.database.settings import get_database_url


def create_engine(url: URL | None = None) -> AsyncEngine:
    """Build the connection pool.

    Kept small on purpose: the free Supabase tier limits how many connections the pooler will
    accept, and a creator-publishing app does not need dozens. ``pool_pre_ping`` drops a
    connection that went stale (for example while a free project was paused) instead of failing
    the first query that happens to pick it up.
    """
    return create_async_engine(
        url or get_database_url(),
        pool_size=5,
        max_overflow=2,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: after a commit, objects keep their values instead of silently
    # re-querying on next access, which in async code raises rather than loads.
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def transaction(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One unit of work: commit if the block succeeds, roll everything back if it raises."""
    async with factory() as session, session.begin():
        yield session


__all__ = ["create_engine", "create_session_factory", "transaction"]
