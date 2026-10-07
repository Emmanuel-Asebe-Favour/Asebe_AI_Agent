"""The publish workflow against a real PostgreSQL: every rule from AGENTS.md §3 it touches."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.publishing.idempotency import generate
from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    RequiresAuthentication,
    Unknown,
)
from asebe_domain.publishing.retry_policy import RetryDecision
from asebe_domain.publishing.state_machine import IllegalTransitionError
from asebe_domain.publishing.status import PublishingStatus
from asebe_infrastructure.database.models import PlatformPost, PublishingAttempt
from asebe_infrastructure.publishing import (
    ContentNotPublishableError,
    DemoContentBlockedError,
    NoPublisherError,
    PublishOrchestrator,
)

from .fakes import FakePublisher, clock_from, same_session, ticking_clock

pytestmark = pytest.mark.integration

MakePost = Callable[..., Awaitable[PlatformPost]]
PUBLISHED_AT = datetime(2026, 10, 5, 12, 0, 3, tzinfo=UTC)


def _orchestrator(session: AsyncSession, publisher: FakePublisher) -> PublishOrchestrator:
    return PublishOrchestrator(
        same_session(session),
        {"platform-1": publisher},
        clock=clock_from(ticking_clock()),
    )


async def _attempt_count(session: AsyncSession, post: PlatformPost) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(PublishingAttempt)
        .where(PublishingAttempt.platform_post_id == post.id)
    )
    return count or 0


async def test_a_proven_publish_ends_published_with_the_remote_id(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    publisher = FakePublisher(
        Published(platform_post_id="remote-1", published_at=PUBLISHED_AT, raw_response={"id": "1"})
    )

    outcome = await _orchestrator(session, publisher).publish(post.id)

    assert outcome.status is PublishingStatus.PUBLISHED
    assert outcome.retry_decision is RetryDecision.NONE
    assert post.platform_post_id == "remote-1"  # R1
    assert post.published_at == PUBLISHED_AT
    assert post.idempotency_key is not None  # R6


async def test_begin_writes_status_key_and_attempt_together(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    orchestrator = _orchestrator(session, FakePublisher())

    begun = await orchestrator.begin(session, post.id)

    assert post.status == PublishingStatus.PUBLISHING
    assert post.idempotency_key == generate(str(post.id), 1)
    assert begun.publish_input.idempotency_key == post.idempotency_key
    attempt = await session.get(PublishingAttempt, begun.attempt_id)
    assert attempt is not None
    assert attempt.request_finished_at is None  # asked, not yet answered


async def test_the_platform_receives_the_users_caption_unaltered(
    session: AsyncSession, make_post: MakePost
) -> None:
    messy = "  Café ☕  — two  spaces,\ttab & emoji 🎉  "
    post = await make_post(caption="shared", platform_caption=messy)
    publisher = FakePublisher(Unknown(reason="stop here"))

    await _orchestrator(session, publisher).publish(post.id)

    assert publisher.calls[0].caption == messy  # R10


async def test_the_shared_caption_is_used_when_there_is_no_platform_caption(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post(caption="Shared caption", platform_caption=None)
    publisher = FakePublisher(Unknown(reason="stop here"))

    await _orchestrator(session, publisher).publish(post.id)

    assert publisher.calls[0].caption == "Shared caption"


async def test_an_unknown_result_stops_everything_and_cannot_be_retried(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    publisher = FakePublisher(Unknown(reason="request timed out"))
    orchestrator = _orchestrator(session, publisher)

    outcome = await orchestrator.publish(post.id)

    assert outcome.status is PublishingStatus.STATUS_UNKNOWN  # R2
    assert outcome.retry_decision is RetryDecision.REQUIRE_REVIEW

    with pytest.raises(IllegalTransitionError):  # R3: asking again is refused...
        await orchestrator.publish(post.id)
    assert len(publisher.calls) == 1  # ...and the platform was never contacted a second time
    assert await _attempt_count(session, post) == 1
    assert post.status == PublishingStatus.STATUS_UNKNOWN


async def test_one_temporary_failure_may_be_retried_once_with_a_new_key(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    temporary = Failed(error_class=ErrorClass.TEMPORARY, message="503 from platform")
    publisher = FakePublisher(temporary, temporary)
    orchestrator = _orchestrator(session, publisher)

    first = await orchestrator.publish(post.id)
    assert first.status is PublishingStatus.FAILED
    assert first.retry_decision is RetryDecision.RETRY_ONCE  # R4

    second = await orchestrator.publish(post.id)  # FAILED -> PUBLISHING is legal
    assert second.attempt_number == 2
    assert second.retry_decision is RetryDecision.REQUIRE_REVIEW  # the one retry is spent
    assert publisher.calls[0].idempotency_key != publisher.calls[1].idempotency_key
    assert post.attempt_count == 2


async def test_a_permanent_failure_is_not_retried(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    publisher = FakePublisher(Failed(error_class=ErrorClass.PERMANENT, message="rejected"))

    outcome = await _orchestrator(session, publisher).publish(post.id)

    assert outcome.status is PublishingStatus.FAILED
    assert outcome.retry_decision is RetryDecision.NONE  # R5
    assert post.last_error == "rejected"


async def test_rejected_credentials_end_in_requires_authentication(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    publisher = FakePublisher(RequiresAuthentication(platform="platform-1"))

    outcome = await _orchestrator(session, publisher).publish(post.id)

    assert outcome.status is PublishingStatus.REQUIRES_AUTHENTICATION
    assert outcome.retry_decision is RetryDecision.NONE


async def test_an_adapter_that_raises_is_recorded_as_unknown_not_failed(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post()
    secret_bearing = RuntimeError("GET https://api.invalid/?access_token=SECRET123 failed")
    publisher = FakePublisher(secret_bearing)

    outcome = await _orchestrator(session, publisher).publish(post.id)

    assert outcome.status is PublishingStatus.STATUS_UNKNOWN  # R2: never FAILED
    assert post.last_error is not None
    assert "RuntimeError" in post.last_error
    assert "SECRET123" not in post.last_error  # R14: the message is never kept


async def test_demo_content_never_reaches_an_adapter(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post(is_demo=True)
    publisher = FakePublisher()

    with pytest.raises(DemoContentBlockedError):  # R11
        await _orchestrator(session, publisher).publish(post.id)

    assert publisher.calls == []
    assert post.status == PublishingStatus.DRAFT
    assert await _attempt_count(session, post) == 0


async def test_content_without_media_is_refused_before_anything_changes(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post(media_url=None)
    publisher = FakePublisher()

    with pytest.raises(ContentNotPublishableError):
        await _orchestrator(session, publisher).publish(post.id)

    assert post.status == PublishingStatus.DRAFT
    assert await _attempt_count(session, post) == 0


async def test_a_platform_with_no_adapter_is_refused_before_anything_changes(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post(platform="platform-without-adapter")

    with pytest.raises(NoPublisherError):
        await _orchestrator(session, FakePublisher()).publish(post.id)

    assert post.status == PublishingStatus.DRAFT
    assert await _attempt_count(session, post) == 0


async def test_an_already_published_post_cannot_be_published_again(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await make_post(status=PublishingStatus.PUBLISHED)
    publisher = FakePublisher()

    with pytest.raises(IllegalTransitionError):
        await _orchestrator(session, publisher).publish(post.id)

    assert publisher.calls == []
