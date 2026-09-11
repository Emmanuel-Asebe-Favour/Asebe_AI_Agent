"""Tests for the retry policy — R3, R4 and R5.

AGENTS.md §9: "For anything touching publishing status, retry, or idempotency, failure tests are
mandatory." This is where the module's most important rule (R3 — an ambiguous result is never
automatically retried) is proven rather than asserted in a comment.

The parametrised tables below enumerate every union member rather than testing a representative
sample, because the whole design claim of architecture.md §3 is that this function is *exhaustively*
testable as a pure function of its arguments.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    PublishResult,
    RequiresAuthentication,
    Unknown,
)
from asebe_domain.publishing.retry_policy import MAX_ATTEMPTS, RetryDecision, decide

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)

PUBLISHED = Published(platform_post_id="p-1", published_at=NOW, raw_response={})
UNKNOWN = Unknown(reason="timeout")
REQUIRES_AUTH = RequiresAuthentication(platform="platform-1")
FAILED_TEMPORARY = Failed(error_class=ErrorClass.TEMPORARY, message="rate limited")
FAILED_PERMANENT = Failed(error_class=ErrorClass.PERMANENT, message="rejected")
FAILED_VALIDATION = Failed(error_class=ErrorClass.VALIDATION, message="caption too long")
FAILED_PERMISSION = Failed(error_class=ErrorClass.PERMISSION, message="scope missing")

ATTEMPT_COUNTS = (1, 2, 3, 10)

NEVER_RETRIED: tuple[PublishResult, ...] = (
    PUBLISHED,
    REQUIRES_AUTH,
    FAILED_PERMANENT,
    FAILED_VALIDATION,
    FAILED_PERMISSION,
)


def test_max_attempts_encodes_exactly_one_retry() -> None:
    """R4 is "at most one automatic retry" — the original attempt plus one, expressed as a cap."""
    assert MAX_ATTEMPTS == 2


# ======================================================================================
# R3 — the single most important rule in the system
# ======================================================================================


@pytest.mark.parametrize("attempt_count", ATTEMPT_COUNTS)
def test_unknown_is_never_retried_at_any_attempt_count(attempt_count: int) -> None:
    """R3: "STATUS_UNKNOWN is never automatically retried. Ever."

    Parametrised over several attempt counts on purpose: the rule is unconditional, so there must
    be no value of ``attempt_count`` that unlocks a retry.
    """
    assert decide(UNKNOWN, attempt_count=attempt_count) is RetryDecision.REQUIRE_REVIEW


def test_unknown_never_yields_retry_once() -> None:
    """Stated separately from the equality above, so the failure names the actual hazard.

    The dangerous outcome is specifically RETRY_ONCE: it would republish content that may already
    be on the platform, producing the duplicate post AGENTS.md §2 exists to prevent.
    """
    for attempt_count in ATTEMPT_COUNTS:
        assert decide(UNKNOWN, attempt_count=attempt_count) is not RetryDecision.RETRY_ONCE


def test_unknown_ignores_attempt_count_entirely() -> None:
    """The decision for an ambiguous result is constant across attempt counts."""
    decisions = {decide(UNKNOWN, attempt_count=n) for n in range(1, 20)}
    assert decisions == {RetryDecision.REQUIRE_REVIEW}


# ======================================================================================
# R4 — at most one automatic retry
# ======================================================================================


def test_temporary_failure_retries_once_on_first_attempt() -> None:
    assert decide(FAILED_TEMPORARY, attempt_count=1) is RetryDecision.RETRY_ONCE


def test_temporary_failure_does_not_retry_again_after_the_retry() -> None:
    """The retry is spent at attempt 2; a third attempt must not be automatic."""
    assert decide(FAILED_TEMPORARY, attempt_count=MAX_ATTEMPTS) is not RetryDecision.RETRY_ONCE


@pytest.mark.parametrize("attempt_count", (2, 3, 10))
def test_temporary_failure_stops_automatic_retry_past_the_cap(attempt_count: int) -> None:
    assert decide(FAILED_TEMPORARY, attempt_count=attempt_count) is RetryDecision.REQUIRE_REVIEW


@pytest.mark.parametrize(
    "result",
    [PUBLISHED, UNKNOWN, REQUIRES_AUTH, FAILED_TEMPORARY, FAILED_PERMANENT],
    ids=lambda r: type(r).__name__,
)
def test_at_most_one_retry_decision_across_all_attempt_counts(result: PublishResult) -> None:
    """R4 as a counted property rather than an example.

    For any result, the number of attempt counts that produce RETRY_ONCE must never exceed one.
    This is the assertion that would catch a future edit making every attempt retryable — an
    example-based test at a single attempt count would not.
    """
    retryable = [
        n
        for n in range(1, 50)
        if decide(result, attempt_count=n) is RetryDecision.RETRY_ONCE
    ]
    assert len(retryable) <= 1


# ======================================================================================
# R5 — auth, validation and permission failures are never retried
# ======================================================================================


@pytest.mark.parametrize("result", NEVER_RETRIED, ids=lambda r: type(r).__name__)
@pytest.mark.parametrize("attempt_count", ATTEMPT_COUNTS)
def test_never_retried_results_always_return_none(
    result: PublishResult, attempt_count: int
) -> None:
    """R5, plus "a proven publish has nothing to retry".

    ``RequiresAuthentication`` is included because its remedy is reconnection, not another request.
    """
    assert decide(result, attempt_count=attempt_count) is RetryDecision.NONE


@pytest.mark.parametrize(
    "error_class",
    [ErrorClass.PERMANENT, ErrorClass.VALIDATION, ErrorClass.PERMISSION],
)
def test_every_non_temporary_error_class_is_never_retried(error_class: ErrorClass) -> None:
    """Exhaustive over ErrorClass — a new non-retryable class must not become retryable by default.

    Mirrors the policy's own ``case Failed():`` arm, which absorbs everything except TEMPORARY.
    """
    result = Failed(error_class=error_class, message="nope")
    for attempt_count in ATTEMPT_COUNTS:
        assert decide(result, attempt_count=attempt_count) is RetryDecision.NONE


# ======================================================================================
# Exhaustiveness over the closed union
# ======================================================================================


@pytest.mark.parametrize(
    "result",
    [PUBLISHED, UNKNOWN, REQUIRES_AUTH, FAILED_TEMPORARY, FAILED_PERMANENT],
    ids=lambda r: type(r).__name__,
)
@pytest.mark.parametrize("attempt_count", (1, 2, 3))
def test_every_union_member_produces_a_decision(
    result: PublishResult, attempt_count: int
) -> None:
    """Every member of the closed union is handled — nothing falls through ``assert_never``."""
    assert decide(result, attempt_count=attempt_count) in set(RetryDecision)


def test_only_a_confirmed_temporary_failure_can_ever_retry() -> None:
    """The single positive permission in the whole policy, stated as a property.

    Sweeps every union member: RETRY_ONCE may be produced only by Failed(TEMPORARY).
    """
    every_result = (
        PUBLISHED,
        UNKNOWN,
        REQUIRES_AUTH,
        FAILED_TEMPORARY,
        FAILED_PERMANENT,
        FAILED_VALIDATION,
        FAILED_PERMISSION,
    )
    for result in every_result:
        for attempt_count in (1, 2, 3):
            if decide(result, attempt_count=attempt_count) is RetryDecision.RETRY_ONCE:
                assert isinstance(result, Failed)
                assert result.error_class is ErrorClass.TEMPORARY


# ======================================================================================
# Input validation
# ======================================================================================


@pytest.mark.parametrize("attempt_count", (0, -1, -100))
def test_non_positive_attempt_count_is_rejected(attempt_count: int) -> None:
    """``attempt_count`` counts attempts already made, so zero is not a meaningful value.

    Accepting it would let a caller retry a first attempt twice by passing a nonsense count.
    """
    with pytest.raises(ValueError, match="attempt_count must be >= 1"):
        decide(PUBLISHED, attempt_count=attempt_count)


def test_attempt_count_is_keyword_only() -> None:
    """Prevents transposing it with the result at a call site — a silent, dangerous swap."""
    with pytest.raises(TypeError):
        decide(PUBLISHED, 1)  # type: ignore[call-arg]
