"""The crash-recovery answer: an interrupted publish becomes STATUS_UNKNOWN, never a retry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.publishing.results import Unknown
from asebe_domain.publishing.status import PublishingStatus
from asebe_infrastructure.database.models import PlatformPost, PublishingAttempt
from asebe_infrastructure.publishing import PublishOrchestrator, recover_interrupted_publishes

from .fakes import START, FakePublisher, clock_from, same_session, ticking_clock

pytestmark = pytest.mark.integration

MakePost = Callable[..., Awaitable[PlatformPost]]
GRACE = timedelta(minutes=10)


async def _crash_after_begin(session: AsyncSession, post: PlatformPost) -> PublishingAttempt:
    """Run step 1 only, as if the process died right after the platform call was sent."""
    orchestrator = PublishOrchestrator(
        same_session(session), {"platform-1": FakePublisher()}, clock=clock_from(ticking_clock())
    )
    begun = await orchestrator.begin(session, post.id)
    attempt = await session.get(PublishingAttempt, begun.attempt_id)
    assert attempt is not None
    return attempt


async def test_a_stuck_publish_becomes_status_unknown_with_an_unknown_attempt(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    attempt = await _crash_after_begin(session, post)

    recovered = await recover_interrupted_publishes(
        session, now=START + timedelta(hours=1), older_than=GRACE
    )

    assert recovered >= 1
    assert post.status == PublishingStatus.STATUS_UNKNOWN  # not FAILED, not PUBLISHING
    assert attempt.result == "Unknown"
    assert attempt.request_finished_at is not None
    assert post.last_error is not None


async def test_a_recent_publish_is_left_alone_because_it_may_still_be_running(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    attempt = await _crash_after_begin(session, post)

    await recover_interrupted_publishes(session, now=START + timedelta(minutes=2), older_than=GRACE)

    assert post.status == PublishingStatus.PUBLISHING
    assert attempt.request_finished_at is None


async def test_a_finished_publish_is_never_touched(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    orchestrator = PublishOrchestrator(
        same_session(session),
        {"platform-1": FakePublisher(Unknown(reason="timed out"))},
        clock=clock_from(ticking_clock()),
    )
    await orchestrator.publish(post.id)
    reason_before = post.last_error

    await recover_interrupted_publishes(session, now=START + timedelta(days=1), older_than=GRACE)

    assert post.status == PublishingStatus.STATUS_UNKNOWN
    assert post.last_error == reason_before  # recovery did not rewrite the real outcome
