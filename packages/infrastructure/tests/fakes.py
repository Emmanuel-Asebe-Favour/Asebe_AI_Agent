"""Test doubles shared by the publishing tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.adapters.protocol import PublishPostInput
from asebe_domain.publishing.results import PublishResult

START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


class FakePublisher:
    """Returns (or raises) the scripted outcomes in order, and remembers every request."""

    def __init__(self, *outcomes: PublishResult | Exception) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[PublishPostInput] = []

    async def publish_post(self, *, input: PublishPostInput) -> PublishResult:
        self.calls.append(input)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def ticking_clock() -> Iterator[datetime]:
    """An endless clock that advances one second per reading, so every timestamp is distinct."""
    moment = START
    while True:
        yield moment
        moment += timedelta(seconds=1)


def clock_from(source: Iterator[datetime]):  # type: ignore[no-untyped-def]
    return lambda: next(source)


def same_session(session: AsyncSession):  # type: ignore[no-untyped-def]
    """A 'transaction' that just hands back the test's already-open, auto-rolled-back session."""

    @asynccontextmanager
    async def _tx() -> AsyncIterator[AsyncSession]:
        yield session

    return _tx
