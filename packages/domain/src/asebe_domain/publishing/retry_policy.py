"""The retry policy — R3, R4 and R5 as a single pure function.

architecture.md §3: "The retry policy is a pure function over the classified error. It has no I/O,
which makes it exhaustively testable." That is why it lives in the domain and why the tests can
enumerate every (result, attempt_count) combination in milliseconds.

The rules, restated so a reader does not have to hold AGENTS.md open:

* R3 — ``STATUS_UNKNOWN``/``Unknown`` is **never** automatically retried. Ever. This is the
  unconditional arm below, and the single most important line in this file. A duplicate post is
  a visible, unrecoverable error for a creator; making a user check their account is not.
* R4 — at most **one** automatic retry, and only for a confirmed temporary technical failure.
* R5 — auth, validation and permission failures are **never** automatically retried.

AGENTS.md §8: "Never add a ``default:`` branch to an exhaustive match over a status or error type.
The compiler is telling you that you have not handled a case." The ``match`` at the bottom of this
file therefore has an explicit arm per union member and terminates in ``assert_never`` rather than
``case _``. The difference matters: ``case _: return REQUIRE_REVIEW`` would silently absorb a fifth
``PublishResult`` member added in a future increment, whereas ``assert_never`` makes that addition a
static error until someone decides its retry behaviour on purpose.
"""

from __future__ import annotations

from enum import StrEnum
from typing import assert_never

from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    PublishResult,
    RequiresAuthentication,
    Unknown,
)


class RetryDecision(StrEnum):
    """What the caller should do next. The policy returns a decision; it performs nothing.

    ``REQUIRE_REVIEW`` is not a synonym for "give up". It means the automatic system must stop and
    a human must determine whether the content landed — README's "Failure workflow".
    """

    NONE = "NONE"
    RETRY_ONCE = "RETRY_ONCE"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"


MAX_ATTEMPTS = 2
"""Total attempts permitted for a confirmed-temporary failure: the original, plus one retry.

R4's "at most one automatic retry" expressed as a cap rather than a boolean, because
``publishing_attempts.attempt_number`` (R7) counts attempts and the two must agree.
"""


def decide(result: PublishResult, *, attempt_count: int) -> RetryDecision:
    """Decide whether ``result`` may be retried, given how many attempts have already been made.

    ``attempt_count`` is the number of attempts made *so far*, inclusive of the one this result
    came from — matching the column defined in README's publishing-attempt data model. It is
    keyword-only so a call site cannot pass it positionally and transpose it with the result.
    """
    if attempt_count < 1:
        raise ValueError(f"attempt_count must be >= 1, got {attempt_count}")

    match result:
        # A proven publish has nothing to retry, and neither has a credential problem: the
        # remedy for the latter is reconnection, not another request (R5).
        case Published() | RequiresAuthentication():
            return RetryDecision.NONE

        # R4's only retryable case. Checked before the bare `Failed()` arm below, which would
        # otherwise absorb it.
        case Failed(error_class=ErrorClass.TEMPORARY):
            if attempt_count < MAX_ATTEMPTS:
                return RetryDecision.RETRY_ONCE
            # The single automatic retry is spent. Stopping is not the same as declaring
            # failure — a human decides whether another attempt is safe.
            return RetryDecision.REQUIRE_REVIEW

        # ErrorClass.PERMANENT, VALIDATION and PERMISSION all land here. Enumerated as a bare
        # `Failed()` rather than three separate arms so that a new non-retryable ErrorClass is
        # non-retryable by default, which is the safe direction to fail.
        case Failed():
            return RetryDecision.NONE

        # R3 — unconditional. This arm carries no attempt_count guard on purpose: no number of
        # prior attempts makes an ambiguous result safe to repeat.
        case Unknown():
            return RetryDecision.REQUIRE_REVIEW

        case _:  # pragma: no cover - unreachable while the union has four members
            assert_never(result)


__all__ = ["MAX_ATTEMPTS", "RetryDecision", "decide"]
