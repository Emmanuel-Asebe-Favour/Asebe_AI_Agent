"""Asking the platform what happened to a post we are not sure about.

A post is in STATUS_UNKNOWN when we asked a platform to publish and never learned the answer. This
module asks the platform again — not to publish, only to *look* — using ``verify_post``. It never
calls ``publish_post``, so it can never create a second copy (R3).

THE GAP THIS MODULE WORKS AROUND — read docs/adr/0003 before changing it.
The domain says a confirmed answer should settle the status: ``VerificationResult.resolves_status``
maps CONFIRMED_PUBLISHED to PUBLISHED and CONFIRMED_ABSENT to FAILED, and architecture.md §5 says
verification resolves Unknown "to Published or Failed". But the state machine, transcribed from
README, only lets STATUS_UNKNOWN move to REQUIRES_USER_REVIEW. Both statements cannot be honoured.
AGENTS.md §11 forbids quietly picking one, so until ADR 0003 is decided this module takes the only
legal route for every outcome: the post goes to REQUIRES_USER_REVIEW, and the evidence is attached
so the creator can act without guessing. ``resolves_status`` is deliberately not consulted here.
When ADR 0003 is accepted, the change is confined to ``PostVerifier.apply``.

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
MESSAGE_LIVE = "The platform shows this post is live (id {post_id}). Do not post it again."
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

        remote_id: str | None = None
        match result.outcome:
            case VerificationOutcome.CONFIRMED_PUBLISHED:
                remote_id = result.platform_post_id
                if remote_id is None:  # pragma: no cover - the constructor forbids this (R1)
                    raise ValueError("a confirmed-published result must carry a platform id")
                # Stored as evidence only. The status is NOT PUBLISHED: see the module docstring.
                post.platform_post_id = remote_id
                message = MESSAGE_LIVE.format(post_id=remote_id)
            case VerificationOutcome.CONFIRMED_ABSENT:
                message = MESSAGE_ABSENT
            case VerificationOutcome.INCONCLUSIVE:
                message = MESSAGE_INCONCLUSIVE
            case VerificationOutcome.UNSUPPORTED:
                message = MESSAGE_UNSUPPORTED
            case _:
                assert_never(result.outcome)

        post.status = transition(
            PublishingStatus.STATUS_UNKNOWN, PublishingStatus.REQUIRES_USER_REVIEW
        )
        post.last_error = message
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
