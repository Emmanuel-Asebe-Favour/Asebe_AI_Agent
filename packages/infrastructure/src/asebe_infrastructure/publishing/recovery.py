"""What to do about a publish that was interrupted halfway.

Picture the worst moment: the app asked a platform to publish, and the power died before the answer
could be written down. The database says PUBLISHING and the latest attempt has a start time but no
finish time. Nobody knows whether the post went live.

The only honest status for that is STATUS_UNKNOWN (R2), and the only honest next step is a human
checking the account (R3). So this function does exactly one thing to each such post: it records
the attempt as ``Unknown`` and moves the post to STATUS_UNKNOWN. It never retries and never marks
anything FAILED — "failed" would be a claim that the content is not on the platform, which we
cannot know.

``older_than`` is a grace period. A publish that began a few seconds ago is probably still in
flight in another worker; touching it would corrupt a healthy attempt. Pick a value comfortably
longer than the slowest legitimate platform request.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from asebe_domain.publishing.results import Unknown
from asebe_domain.publishing.state_machine import transition
from asebe_domain.publishing.status import PublishingStatus
from asebe_infrastructure.database.models import PlatformPost, PublishingAttempt
from asebe_infrastructure.repositories import PublishingAttemptRepository

INTERRUPTED_REASON = "publish was interrupted before an outcome was recorded"


async def recover_interrupted_publishes(
    session: AsyncSession, *, now: datetime, older_than: timedelta
) -> int:
    """Move stuck PUBLISHING posts to STATUS_UNKNOWN. Returns how many were recovered."""
    cutoff = now - older_than
    repo = PublishingAttemptRepository(session)

    # SKIP LOCKED: if another worker holds a post right now, it is by definition not stuck, and
    # waiting for it would stall recovery behind a healthy publish.
    stuck = (
        await session.scalars(
            select(PlatformPost)
            .where(PlatformPost.status == PublishingStatus.PUBLISHING.value)
            .with_for_update(skip_locked=True)
        )
    ).all()

    recovered = 0
    for post in stuck:
        attempt = await session.scalar(
            select(PublishingAttempt)
            .where(
                PublishingAttempt.platform_post_id == post.id,
                PublishingAttempt.request_finished_at.is_(None),
                PublishingAttempt.request_started_at < cutoff,
            )
            .order_by(PublishingAttempt.attempt_number.desc())
            .limit(1)
        )
        if attempt is None:
            continue
        await repo.finish(attempt, Unknown(reason=INTERRUPTED_REASON), now=now)
        post.status = transition(PublishingStatus(post.status), PublishingStatus.STATUS_UNKNOWN)
        post.last_error = INTERRUPTED_REASON
        recovered += 1

    await session.flush()
    return recovered


__all__ = ["INTERRUPTED_REASON", "recover_interrupted_publishes"]
