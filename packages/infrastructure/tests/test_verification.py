"""Verification against a real PostgreSQL: look, never publish, and never claim more than proven."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.adapters.protocol import VerificationOutcome, VerificationResult
from asebe_domain.publishing.idempotency import generate
from asebe_domain.publishing.status import PublishingStatus
from asebe_infrastructure.database.models import PlatformPost, PublishingAttempt
from asebe_infrastructure.publishing import (
    NotAwaitingVerificationError,
    NoVerifierError,
    PostVerifier,
)
from asebe_infrastructure.publishing.verification import (
    MESSAGE_ABSENT,
    MESSAGE_INCONCLUSIVE,
    MESSAGE_UNSUPPORTED,
)
from asebe_infrastructure.repositories import PlatformPostNotFoundError

from .fakes import START, FakeVerifier, clock_from, same_session, ticking_clock

pytestmark = pytest.mark.integration

MakePost = Callable[..., Awaitable[PlatformPost]]


def _verifier(session: AsyncSession, fake: FakeVerifier) -> PostVerifier:
    return PostVerifier(
        same_session(session), {"platform-1": fake}, clock=clock_from(ticking_clock())
    )


async def _unknown_post(make_post: MakePost) -> PlatformPost:
    post = await make_post(status=PublishingStatus.STATUS_UNKNOWN)
    post.idempotency_key = generate(str(post.id), 1)
    return post


async def test_inconclusive_sends_the_post_to_review_with_a_plain_instruction(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(VerificationResult.inconclusive(detail="no match", checked_at=START))

    report = await _verifier(session, fake).verify(post.id)

    assert report.status is PublishingStatus.REQUIRES_USER_REVIEW
    assert report.message == MESSAGE_INCONCLUSIVE
    assert post.status == PublishingStatus.REQUIRES_USER_REVIEW
    assert post.last_error == MESSAGE_INCONCLUSIVE
    assert post.platform_post_id is None  # nothing was proven, so nothing is recorded
    assert post.published_at is None


async def test_a_platform_that_cannot_verify_is_honest_about_it(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(VerificationResult.unsupported())

    report = await _verifier(session, fake).verify(post.id)

    assert report.outcome is VerificationOutcome.UNSUPPORTED
    assert report.status is PublishingStatus.REQUIRES_USER_REVIEW
    assert report.message == MESSAGE_UNSUPPORTED


async def test_a_confirmed_live_post_becomes_published_with_the_platforms_own_id(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(
        VerificationResult.confirmed_published(platform_post_id="remote-77", checked_at=START)
    )

    report = await _verifier(session, fake).verify(post.id)

    assert report.status is PublishingStatus.PUBLISHED
    assert report.remote_post_id == "remote-77"
    assert "remote-77" in report.message
    assert post.status == PublishingStatus.PUBLISHED
    assert post.platform_post_id == "remote-77"  # R1
    assert post.published_at == START
    assert post.last_error is None  # the doubt is resolved, so the old error is cleared


async def test_a_confirmed_absent_post_becomes_failed_and_is_not_retried_automatically(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(
        VerificationResult.confirmed_absent(detail="no such request", checked_at=START)
    )

    report = await _verifier(session, fake).verify(post.id)

    assert report.status is PublishingStatus.FAILED
    assert report.message == MESSAGE_ABSENT
    assert post.status == PublishingStatus.FAILED
    assert post.platform_post_id is None
    assert post.last_error == MESSAGE_ABSENT
    assert len(fake.calls) == 1  # one look, and nothing was published


async def test_the_platform_is_asked_once_with_this_posts_own_keys(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(VerificationResult.unsupported())

    await _verifier(session, fake).verify(post.id)

    assert fake.calls == [(str(post.id), generate(str(post.id), 1))]


async def test_verifying_never_creates_or_changes_an_attempt(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(VerificationResult.unsupported())

    await _verifier(session, fake).verify(post.id)

    count = await session.scalar(
        select(func.count())
        .select_from(PublishingAttempt)
        .where(PublishingAttempt.platform_post_id == post.id)
    )
    assert count == 0  # looking is not publishing


async def test_a_verifier_that_raises_is_inconclusive_and_its_message_is_dropped(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    fake = FakeVerifier(RuntimeError("GET https://api.invalid/?access_token=SECRET123 failed"))

    report = await _verifier(session, fake).verify(post.id)

    assert report.outcome is VerificationOutcome.INCONCLUSIVE
    assert report.status is PublishingStatus.REQUIRES_USER_REVIEW
    assert post.last_error is not None
    assert "SECRET123" not in post.last_error  # R14


@pytest.mark.parametrize(
    "status",
    [PublishingStatus.DRAFT, PublishingStatus.PUBLISHED, PublishingStatus.REQUIRES_USER_REVIEW],
)
async def test_only_a_status_unknown_post_can_be_verified(
    session: AsyncSession, make_post: MakePost, status: PublishingStatus
) -> None:
    post = await make_post(status=status)
    fake = FakeVerifier()

    with pytest.raises(NotAwaitingVerificationError):
        await _verifier(session, fake).verify(post.id)

    assert fake.calls == []  # refused before any network traffic
    assert post.status == status


async def test_a_post_that_changed_while_we_waited_is_not_overwritten(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    verifier = _verifier(session, FakeVerifier())

    lookup = await verifier.prepare(session, post.id)
    post.status = PublishingStatus.REQUIRES_USER_REVIEW  # someone else got there first

    with pytest.raises(NotAwaitingVerificationError):
        await verifier.apply(session, lookup, VerificationResult.unsupported())


async def test_a_platform_with_no_verifier_is_refused_before_anything_changes(
    session: AsyncSession, make_post: MakePost
) -> None:
    post = await _unknown_post(make_post)
    post.platform = "platform-without-adapter"

    with pytest.raises(NoVerifierError):
        await _verifier(session, FakeVerifier()).verify(post.id)

    assert post.status == PublishingStatus.STATUS_UNKNOWN


async def test_a_missing_post_is_reported_as_missing(session: AsyncSession) -> None:
    with pytest.raises(PlatformPostNotFoundError):
        await _verifier(session, FakeVerifier()).verify(uuid.uuid4())
