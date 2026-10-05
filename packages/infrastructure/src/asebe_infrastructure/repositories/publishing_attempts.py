"""R7: every publishing attempt, and what came back, is persisted.

Two calls, because an attempt has two moments:

* ``start`` — written *before* the platform is contacted. If the process dies mid-request, the row
  still exists with no ``request_finished_at``, which is exactly the evidence the reconciler needs
  to see that a request went out and its outcome was never recorded.
* ``finish`` — written once, when the outcome is known. Never again: the audit trail's value is
  that it records what we believed at the time, so a finished attempt cannot be rewritten.

Neither call commits. The caller owns the transaction (R9); see ``database/session.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import assert_never

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.publishing.results import (
    Failed,
    Published,
    PublishResult,
    RequiresAuthentication,
    Unknown,
)
from asebe_infrastructure.database.models.publishing import PlatformPost, PublishingAttempt


class PlatformPostNotFoundError(LookupError):
    """There is no platform post with this id, so there is nothing to attempt."""


class AttemptAlreadyFinishedError(RuntimeError):
    """This attempt already has a recorded outcome, and outcomes are never rewritten."""


def _require_aware(moment: datetime) -> None:
    # A naive timestamp has no offset, so it cannot be stored as a correct UTC instant.
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware (use UTC)")


class PublishingAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, platform_post_id: uuid.UUID, *, now: datetime) -> PublishingAttempt:
        """Record that an attempt is beginning, and number it.

        The parent post row is locked first (``FOR UPDATE``), so two workers starting attempts
        for the same post at the same moment queue up instead of both choosing the same number.
        """
        _require_aware(now)
        post = await self._session.scalar(
            select(PlatformPost).where(PlatformPost.id == platform_post_id).with_for_update()
        )
        if post is None:
            raise PlatformPostNotFoundError(str(platform_post_id))

        highest = await self._session.scalar(
            select(func.coalesce(func.max(PublishingAttempt.attempt_number), 0)).where(
                PublishingAttempt.platform_post_id == platform_post_id
            )
        )
        attempt_number = (highest or 0) + 1

        attempt = PublishingAttempt(
            platform_post_id=platform_post_id,
            attempt_number=attempt_number,
            request_started_at=now,
            created_at=now,
        )
        self._session.add(attempt)
        # Keep the post's own counter in step with the attempts table, in the same transaction,
        # so the retry policy (which reads attempt_count) can never disagree with the audit trail.
        post.attempt_count = attempt_number
        await self._session.flush()
        return attempt

    async def finish(
        self, attempt: PublishingAttempt, result: PublishResult, *, now: datetime
    ) -> None:
        """Record the outcome of an attempt, exactly once."""
        _require_aware(now)
        if attempt.request_finished_at is not None:
            raise AttemptAlreadyFinishedError(str(attempt.id))

        attempt.request_finished_at = now
        # No default arm: a fifth member of the union is a type error here, not a silent fallback.
        match result:
            case Published(raw_response=raw):
                attempt.result = "Published"
                attempt.response_payload = dict(raw)
            case Failed(error_class=error_class, message=message):
                attempt.result = "Failed"
                attempt.error_type = error_class.value
                attempt.error_message = message
            case Unknown(reason=reason, raw_response=raw):
                attempt.result = "Unknown"
                attempt.error_type = "Unknown"
                attempt.error_message = reason
                attempt.response_payload = None if raw is None else dict(raw)
            case RequiresAuthentication(platform=platform):
                attempt.result = "RequiresAuthentication"
                attempt.error_type = "RequiresAuthentication"
                attempt.error_message = f"Credentials rejected by {platform}"
            case _:
                assert_never(result)
        await self._session.flush()


__all__ = [
    "AttemptAlreadyFinishedError",
    "PlatformPostNotFoundError",
    "PublishingAttemptRepository",
]
