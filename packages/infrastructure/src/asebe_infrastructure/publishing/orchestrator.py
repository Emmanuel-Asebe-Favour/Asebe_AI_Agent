"""One publish, in three steps — and the reason there are three.

    1. BEGIN     transaction A, committed.   Post becomes PUBLISHING, an idempotency key is
                                             issued, and an attempt row is written.
    2. PUBLISH   no transaction held.         The platform is called.
    3. COMPLETE  transaction B, committed.   The attempt's outcome and the post's new status are
                                             written together.

Why not one transaction around all of it? Because step 2 is a network call to someone else's
server, and it can succeed even if our database then fails. If everything were one transaction, a
crash after the platform said "published" would roll back the record that we ever asked — and the
creator's next click would post the same thing twice, the exact bug AGENTS.md §2 exists to
prevent. Committing BEGIN first means that however the process dies after step 1, the database
still says "a request may have gone out".

The crash windows, and what each leaves behind:

* before BEGIN commits      nothing changed; safe to start again.
* between BEGIN and COMPLETE  post is PUBLISHING, the latest attempt has no finish time. This is
                            "we asked and do not know the answer". ``recover_interrupted_publishes``
                            turns that into STATUS_UNKNOWN for a human — never into a retry (R3).
* after COMPLETE commits    done.

R9 is only partly delivered here. The status change, the idempotency key and the attempt row do
commit together in step 1. Deferring a *follow-up job* in that same transaction (for the one
automatic retry R4 allows) needs the job queue, which is not wired yet; until then the decision is
returned to the caller in ``PublishOutcome.retry_decision`` rather than enqueued.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, assert_never

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from asebe_domain.adapters.protocol import PublishPostInput
from asebe_domain.publishing.idempotency import generate as generate_idempotency_key
from asebe_domain.publishing.results import (
    Failed,
    Published,
    PublishResult,
    RequiresAuthentication,
    Unknown,
)
from asebe_domain.publishing.retry_policy import RetryDecision, decide
from asebe_domain.publishing.state_machine import transition
from asebe_domain.publishing.status import PublishingStatus
from asebe_infrastructure.database.models import PlatformPost, PublishingAttempt
from asebe_infrastructure.repositories import (
    PlatformPostNotFoundError,
    PublishingAttemptRepository,
)

TransactionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
Clock = Callable[[], datetime]


class Publisher(Protocol):
    """The one thing the orchestrator needs from a platform adapter.

    Deliberately narrower than the full ``PlatformAdapter``: the orchestrator never connects,
    validates or reads analytics, so it should not be able to. Every real adapter satisfies this.
    """

    async def publish_post(self, *, input: PublishPostInput) -> PublishResult: ...


class DemoContentBlockedError(RuntimeError):
    """R11: demo content must never reach a real platform adapter."""


class ContentNotPublishableError(ValueError):
    """The content item is missing something every publish needs (media)."""


class NoPublisherError(LookupError):
    """No adapter is registered for this post's platform."""


@dataclass(frozen=True, slots=True)
class BeginResult:
    attempt_id: uuid.UUID
    publish_input: PublishPostInput
    platform: str


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    """What happened, for the caller (an API route or a worker) to act on."""

    status: PublishingStatus
    result: PublishResult
    retry_decision: RetryDecision
    attempt_number: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PublishOrchestrator:
    def __init__(
        self,
        transaction: TransactionFactory,
        publishers: Mapping[str, Publisher],
        clock: Clock = _utc_now,
    ) -> None:
        self._transaction = transaction
        self._publishers = publishers
        self._clock = clock

    async def publish(self, platform_post_id: uuid.UUID) -> PublishOutcome:
        async with self._transaction() as session:
            begun = await self.begin(session, platform_post_id)

        result = await self._call_platform(begun)

        async with self._transaction() as session:
            return await self.complete(session, begun, result)

    async def begin(self, session: AsyncSession, platform_post_id: uuid.UUID) -> BeginResult:
        """Step 1. Every check runs before any write, so a refusal leaves no trace."""
        post = await self._load_locked(session, platform_post_id)
        content = post.content_item

        if content.is_demo:
            raise DemoContentBlockedError(str(post.id))  # R11
        if not content.media_url or not content.media_type:
            raise ContentNotPublishableError("content item has no media to publish")
        if post.platform not in self._publishers:
            raise NoPublisherError(post.platform)

        # R8: the state machine is the only judge of legality. This raises IllegalTransitionError
        # for, among others, STATUS_UNKNOWN -> PUBLISHING — R3, "never retry an unknown".
        new_status = transition(PublishingStatus(post.status), PublishingStatus.PUBLISHING)

        now = self._clock()
        attempt = await PublishingAttemptRepository(session).start(post.id, now=now)

        # R6 + R9: key, status and attempt row are all written in this one transaction.
        post.idempotency_key = generate_idempotency_key(str(post.id), attempt.attempt_number)
        post.status = new_status

        publish_input = PublishPostInput(
            platform_post_key=str(post.id),
            idempotency_key=post.idempotency_key,
            attempt_number=attempt.attempt_number,
            # R10: the user's words, exactly. The platform-specific caption wins when the user
            # wrote one; otherwise the shared caption. Nothing is trimmed, translated or fixed.
            caption=post.platform_caption
            if post.platform_caption is not None
            else (content.caption or ""),
            media_url=content.media_url,
            media_type=content.media_type,
            scheduled_at_utc=post.scheduled_at_utc,
        )
        await session.flush()
        return BeginResult(attempt.id, publish_input, post.platform)

    async def _call_platform(self, begun: BeginResult) -> PublishResult:
        publisher = self._publishers[begun.platform]
        try:
            return await publisher.publish_post(input=begun.publish_input)
        except Exception as exc:
            # An adapter must never raise (see PlatformAdapter.publish_post), so this is a
            # defect — but a defect must not become a false "failed". R2: a connection-level
            # surprise is Unknown. Only the exception's *type* is kept: its message could carry
            # a URL or header, and R14 forbids credentials reaching an error message.
            return Unknown(reason=f"adapter raised {type(exc).__name__} before returning a result")

    async def complete(
        self, session: AsyncSession, begun: BeginResult, result: PublishResult
    ) -> PublishOutcome:
        """Step 3. Record the attempt's outcome and move the post, in one transaction."""
        post = await self._load_locked(session, uuid.UUID(begun.publish_input.platform_post_key))
        attempt = await session.get(PublishingAttempt, begun.attempt_id)
        if attempt is None:  # pragma: no cover - begin() just wrote it
            raise LookupError(str(begun.attempt_id))

        now = self._clock()
        await PublishingAttemptRepository(session).finish(attempt, result, now=now)

        current = PublishingStatus(post.status)
        # No default arm: a fifth PublishResult member is a type error here, not a silent branch.
        match result:
            case Published(platform_post_id=remote_id, published_at=published_at):
                post.status = transition(current, PublishingStatus.PUBLISHED)
                post.platform_post_id = remote_id  # R1: PUBLISHED always has the remote id
                post.published_at = published_at
                post.last_error = None
            case Failed(message=message):
                post.status = transition(current, PublishingStatus.FAILED)
                post.last_error = message
            case Unknown(reason=reason):
                post.status = transition(current, PublishingStatus.STATUS_UNKNOWN)  # R2
                post.last_error = reason
            case RequiresAuthentication(platform=platform):
                post.status = transition(current, PublishingStatus.REQUIRES_AUTHENTICATION)
                post.last_error = f"Credentials rejected by {platform}"
            case _:
                assert_never(result)

        await session.flush()
        return PublishOutcome(
            status=PublishingStatus(post.status),
            result=result,
            # R3/R4/R5 live in the domain; this only asks it.
            retry_decision=decide(result, attempt_count=attempt.attempt_number),
            attempt_number=attempt.attempt_number,
        )

    @staticmethod
    async def _load_locked(session: AsyncSession, platform_post_id: uuid.UUID) -> PlatformPost:
        # FOR UPDATE: a second worker asking to publish the same post waits here, then finds the
        # status already PUBLISHING and is refused by the state machine — one request, not two.
        post = await session.scalar(
            select(PlatformPost)
            .where(PlatformPost.id == platform_post_id)
            .options(selectinload(PlatformPost.content_item))
            .with_for_update(of=PlatformPost)
        )
        if post is None:
            raise PlatformPostNotFoundError(str(platform_post_id))
        return post


__all__ = [
    "BeginResult",
    "Clock",
    "ContentNotPublishableError",
    "DemoContentBlockedError",
    "NoPublisherError",
    "PublishOrchestrator",
    "PublishOutcome",
    "Publisher",
    "TransactionFactory",
]
