"""R7 against a real PostgreSQL: attempts are numbered, recorded, and never rewritten."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    RequiresAuthentication,
    Unknown,
)
from asebe_infrastructure.database.models import PlatformPost
from asebe_infrastructure.repositories import (
    AttemptAlreadyFinishedError,
    PlatformPostNotFoundError,
    PublishingAttemptRepository,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 2, 12, 0, 5, tzinfo=UTC)


async def test_attempts_are_numbered_from_one_and_counted_on_the_post(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    repo = PublishingAttemptRepository(session)

    first = await repo.start(platform_post.id, now=T0)
    second = await repo.start(platform_post.id, now=T1)

    assert (first.attempt_number, second.attempt_number) == (1, 2)
    assert platform_post.attempt_count == 2


async def test_a_started_attempt_has_no_outcome_yet(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    attempt = await PublishingAttemptRepository(session).start(platform_post.id, now=T0)

    assert attempt.request_started_at == T0
    assert attempt.request_finished_at is None
    assert attempt.result is None


async def test_published_records_the_raw_response(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    repo = PublishingAttemptRepository(session)
    attempt = await repo.start(platform_post.id, now=T0)

    await repo.finish(
        attempt,
        Published(
            platform_post_id="remote-123", published_at=T1, raw_response={"id": "remote-123"}
        ),
        now=T1,
    )

    assert attempt.result == "Published"
    assert attempt.response_payload == {"id": "remote-123"}
    assert attempt.error_type is None
    assert attempt.request_finished_at == T1


async def test_failed_records_the_error_class_and_message(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    repo = PublishingAttemptRepository(session)
    attempt = await repo.start(platform_post.id, now=T0)

    await repo.finish(
        attempt, Failed(error_class=ErrorClass.TEMPORARY, message="rate limited"), now=T1
    )

    assert attempt.result == "Failed"
    assert attempt.error_type == "TEMPORARY"
    assert attempt.error_message == "rate limited"


async def test_unknown_without_any_response_stores_no_payload(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    repo = PublishingAttemptRepository(session)
    attempt = await repo.start(platform_post.id, now=T0)

    await repo.finish(attempt, Unknown(reason="request timed out"), now=T1)

    assert attempt.result == "Unknown"
    assert attempt.error_message == "request timed out"
    assert attempt.response_payload is None


async def test_requires_authentication_is_recorded_as_such(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    repo = PublishingAttemptRepository(session)
    attempt = await repo.start(platform_post.id, now=T0)

    await repo.finish(attempt, RequiresAuthentication(platform="platform-1"), now=T1)

    assert attempt.result == "RequiresAuthentication"
    assert attempt.error_type == "RequiresAuthentication"


async def test_an_outcome_cannot_be_rewritten(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    repo = PublishingAttemptRepository(session)
    attempt = await repo.start(platform_post.id, now=T0)
    await repo.finish(attempt, Unknown(reason="timed out"), now=T1)

    with pytest.raises(AttemptAlreadyFinishedError):
        await repo.finish(
            attempt,
            Published(platform_post_id="remote-9", published_at=T1, raw_response={}),
            now=T1,
        )

    assert attempt.result == "Unknown"


async def test_starting_an_attempt_for_a_missing_post_fails(session: AsyncSession) -> None:
    with pytest.raises(PlatformPostNotFoundError):
        await PublishingAttemptRepository(session).start(uuid.uuid4(), now=T0)


async def test_naive_timestamps_are_rejected(
    session: AsyncSession, platform_post: PlatformPost
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await PublishingAttemptRepository(session).start(
            platform_post.id, now=datetime(2026, 10, 2, 12, 0)
        )
