"""The scheduled-publish task.

The shape of this task is dictated by architecture.md §4's transactional boundary: the job is
deferred on the *same connection* that writes ``PUBLISHING`` (R9), so a post cannot claim to be
scheduled with no job behind it, and a job cannot exist for a post that was never marked.

**Not executed.** Requires PostgreSQL and a running worker; neither is available here. The
orchestration below is a skeleton: the repository calls it references do not exist yet.

What it deliberately does NOT do — each omission is a rule:

* It does not retry. Retries go through ``retry_policy.decide`` and create a new attempt row
  (AGENTS.md §8: "Never retry by calling the adapter again").
* It does not convert an exception from ``publish_post`` into ``FAILED``. Exceptions route through
  the error classifier, because most surprises are ``Unknown`` (§8).
* It does not write a status directly. Every transition goes through ``state_machine.transition``
  (R8).
* It does not decide retry eligibility from anything but ``retry_policy``.
"""

from __future__ import annotations

from asebe_worker.main import app


@app.task(name="publishing.publish_scheduled_post")
async def publish_scheduled_post(*, platform_post_id: str) -> None:
    """Publish one scheduled post and record the outcome.

    Steps, in the order the rules require:

    1. Load the post and confirm it is still ``SCHEDULED`` — it may have been cancelled between
       scheduling and the job firing.
    2. Move to ``PUBLISHING``, generating the idempotency key in the same transaction (R6, R9).
    3. Open an attempt row *before* the request (R7).
    4. Call the adapter's ``publish_post``. Any exception is classified, never converted (§8).
    5. Classify the result and apply the resulting status through the state machine (R8).
    6. Verify where the platform supports it; an unresolved post stays ``STATUS_UNKNOWN`` and is
       routed to ``REQUIRES_USER_REVIEW`` for a human (R3).
    """
    raise NotImplementedError(
        "Requires the repository layer and a running Postgres/Procrastinate instance. "
        "See packages/infrastructure/__init__.py for the verification status of the data layer."
    )


__all__ = ["publish_scheduled_post"]
