"""Asking the platform what happened to a post we are not sure about.

A post is in STATUS_UNKNOWN when we asked a platform to publish and never learned the answer. This
module asks the platform again — not to publish, only to *look* — using ``verify_post``. It never
calls ``publish_post``, so it can never create a second copy (R3).

WHAT A VERIFICATION DECIDES (ADR 0003, accepted)
``VerificationResult.resolves_status`` is the single source of truth. A confirmed-published result
settles the post as PUBLISHED, with the platform's own id (R1). A confirmed-absent result settles
it as FAILED: the platform said the content was never created. Anything less than a confirmation
-- inconclusive, or a platform that cannot be asked -- changes nothing about what we know, so the
post goes to REQUIRES_USER_REVIEW for a human, exactly as before. None of these is a retry (R3): a
FAILED reached this way is still only retried by the creator, deliberately.

The state machine cannot see the evidence, so this module is the one that must hold it: it moves a
post out of STATUS_UNKNOWN only because a ``VerificationResult`` says so.

Like publishing, verification is split so the network call holds no database transaction:
``prepare`` (read), ask the platform, ``apply`` (write, re-checking the status first because
another worker may have acted while we waited).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, assert_never

from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.adapters.protocol import VerificationOutcome, VerificationResult
from asebe_domain.publishing.state_machine import transition
from asebe_domain.publishing.status import PublishingStatus
from asebe_infrastructure.database.models import PlatformPost
from asebe_infrastructure.publishing.orchestrator import (
    Clock,
    TransactionFactory,
    _utc_now,
    load_post_locked,
)
from asebe_infrastructure.repositories import PlatformPostNotFoundError


class Verifier(Protocol):
    """The one thing verification needs from a platform adapter: to look, never to publish."""

    async def verify_post(
        self, *, platform_post_key: str, idempotency_key: str
    ) -> VerificationResult: ...


class NotAwaitingVerificationError(RuntimeError):
    """Only a STATUS_UNKNOWN post can be verified; this one is in some other state."""


class NoVerifierError(LookupError):
    """No adapter is registered for this post's platform."""


# What the creator is told. Fixed sentences, never the adapter's free text: an adapter's detail
# string could echo something it should not, and R14 keeps credentials out of anything shown.
MESSAGE_LIVE = "Confirmed: the platform shows this post is live (id {post_id})."
MESSAGE_ABSENT = "The platform confirms this post was not created. It is safe to try again."
MESSAGE_INCONCLUSIVE = (
    "We could not tell whether this post went live. "
    "Please check your account on the platform before trying again."
)
MESSAGE_UNSUPPORTED = (
    "This platform cannot confirm whether the post went live. "
    "Please check your account on the platform before trying again."
)


@dataclass(frozen=True, slots=True)
class VerificationLookup:
    platform_post_id: uuid.UUID
    platform: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class VerificationReport:
    outcome: VerificationOutcome
    status: PublishingStatus
    message: str
    remote_post_id: str | None


class PostVerifier:
    def __init__(
        self,
        transaction: TransactionFactory,
        verifiers: Mapping[str, Verifier],
        clock: Clock = _utc_now,
    ) -> None:
        self._transaction = transaction
        self._verifiers = verifiers
        self._clock = clock

    async def verify(self, platform_post_id: uuid.UUID) -> VerificationReport:
        async with self._transaction() as session:
            lookup = await self.prepare(session, platform_post_id)

        result = await self._ask_platform(lookup)

        async with self._transaction() as session:
            return await self.apply(session, lookup, result)

    async def prepare(
        self, session: AsyncSession, platform_post_id: uuid.UUID
    ) -> VerificationLookup:
        """Read-only. Refuses anything that is not a STATUS_UNKNOWN post, before any network."""
        post = await session.get(PlatformPost, platform_post_id)
        if post is None:
            raise PlatformPostNotFoundError(str(platform_post_id))
        if PublishingStatus(post.status) is not PublishingStatus.STATUS_UNKNOWN:
            raise NotAwaitingVerificationError(f"{post.id} is {post.status}")
        if post.idempotency_key is None:  # pragma: no cover - begin() always issues one
            raise NotAwaitingVerificationError(f"{post.id} has no idempotency key to look up")
        if post.platform not in self._verifiers:
            raise NoVerifierError(post.platform)
        return VerificationLookup(post.id, post.platform, post.idempotency_key)

    async def _ask_platform(self, lookup: VerificationLookup) -> VerificationResult:
        verifier = self._verifiers[lookup.platform]
        try:
            return await verifier.verify_post(
                platform_post_key=str(lookup.platform_post_id),
                idempotency_key=lookup.idempotency_key,
            )
        except Exception as exc:
            # Not being able to look is not evidence of anything: inconclusive, never "absent".
            # Only the exception type is kept, for the same reason as in the orchestrator (R14).
            return VerificationResult.inconclusive(
                detail=f"verifier raised {type(exc).__name__}", checked_at=self._clock()
            )

    async def apply(
        self, session: AsyncSession, lookup: VerificationLookup, result: VerificationResult
    ) -> VerificationReport:
        post = await load_post_locked(session, lookup.platform_post_id)
        # We waited on the network without holding a lock, so look again before writing.
        if PublishingStatus(post.status) is not PublishingStatus.STATUS_UNKNOWN:
            raise NotAwaitingVerificationError(f"{post.id} is now {post.status}")

        # R8: the state machine still judges legality; resolves_status only chooses the target.
        target = result.resolves_status or PublishingStatus.REQUIRES_USER_REVIEW

        remote_id: str | None = None
        match result.outcome:
            case VerificationOutcome.CONFIRMED_PUBLISHED:
                remote_id = result.platform_post_id
                if remote_id is None:  # pragma: no cover - the constructor forbids this (R1)
                    raise ValueError("a confirmed-published result must carry a platform id")
                post.platform_post_id = remote_id  # R1: PUBLISHED always has the remote id
                # The earliest moment we can prove the post existed. Not the moment it went live,
                # which an unknown publish never told us.
                post.published_at = result.checked_at
                message = MESSAGE_LIVE.format(post_id=remote_id)
                post.last_error = None
            case VerificationOutcome.CONFIRMED_ABSENT:
                message = MESSAGE_ABSENT
                post.last_error = message
            case VerificationOutcome.INCONCLUSIVE:
                message = MESSAGE_INCONCLUSIVE
                post.last_error = message
            case VerificationOutcome.UNSUPPORTED:
                message = MESSAGE_UNSUPPORTED
                post.last_error = message
            case _:
                assert_never(result.outcome)

        post.status = transition(PublishingStatus.STATUS_UNKNOWN, target)
        await session.flush()
        return VerificationReport(
            outcome=result.outcome,
            status=PublishingStatus(post.status),
            message=message,
            remote_post_id=remote_id,
        )


__all__ = [
    "MESSAGE_ABSENT",
    "MESSAGE_INCONCLUSIVE",
    "MESSAGE_LIVE",
    "MESSAGE_UNSUPPORTED",
    "NoVerifierError",
    "NotAwaitingVerificationError",
    "PostVerifier",
    "VerificationLookup",
    "VerificationReport",
    "Verifier",
]
