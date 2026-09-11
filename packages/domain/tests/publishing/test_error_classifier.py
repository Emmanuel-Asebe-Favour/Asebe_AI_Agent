"""Tests for the error classifier — R2, and the asymmetry that makes it safe.

architecture.md §3: "anything we did not fully understand is ``Unknown``, because ``Unknown`` is
safe and ``Temporary`` is not. A mistaken ``Temporary`` causes a duplicate post; a mistaken
``Unknown`` causes a user to check their account."

The cases below walk architecture.md §3's table row by row. The ones that matter most are the
*negative* ones — the rows where a naive implementation would reach for ``Temporary`` and where
this one must not.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from asebe_domain.publishing.error_classifier import (
    ParsedPlatformResponse,
    PlatformErrorBody,
    TransportOutcome,
    classify,
)
from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    RequiresAuthentication,
    Unknown,
)

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
PLATFORM = "platform-1"
SOME_ERROR = PlatformErrorBody(code="E_BAD", message="something went wrong")


def parsed(
    status_code: int,
    *,
    platform_post_id: str | None = None,
    error: PlatformErrorBody | None = None,
    raw: dict[str, object] | None = None,
    published_at: datetime | None = None,
) -> ParsedPlatformResponse:
    return ParsedPlatformResponse(
        status_code=status_code,
        platform_post_id=platform_post_id,
        error=error,
        published_at=published_at,
        raw=raw if raw is not None else {"status": status_code},
    )


def run(outcome: TransportOutcome, response: ParsedPlatformResponse | None = None):  # type: ignore[no-untyped-def]
    return classify(platform=PLATFORM, outcome=outcome, observed_at=NOW, response=response)


# ======================================================================================
# Transport-level outcomes — no response at all
# ======================================================================================


def test_timeout_yields_unknown() -> None:
    """The founding hazard: the platform may have accepted the post and the reply was lost."""
    result = run(TransportOutcome.TIMEOUT)
    assert isinstance(result, Unknown)
    assert result.raw_response is None


def test_connection_error_yields_unknown() -> None:
    result = run(TransportOutcome.CONNECTION_ERROR)
    assert isinstance(result, Unknown)


@pytest.mark.parametrize(
    "outcome", [TransportOutcome.TIMEOUT, TransportOutcome.CONNECTION_ERROR]
)
def test_transport_failures_are_never_temporary(outcome: TransportOutcome) -> None:
    """A transport failure must never be classified as retryable — it might already have landed."""
    result = run(outcome)
    assert not (isinstance(result, Failed) and result.error_class is ErrorClass.TEMPORARY)


def test_unparseable_response_yields_unknown() -> None:
    """A response arrived but we could not understand it — the case the module exists for."""
    result = run(TransportOutcome.RESPONSE, None)
    assert isinstance(result, Unknown)
    assert "could not be parsed" in result.reason


# ======================================================================================
# 2xx — the only path to Published
# ======================================================================================


@pytest.mark.parametrize("status_code", (200, 201, 202, 204))
def test_success_status_with_post_id_publishes(status_code: int) -> None:
    result = run(TransportOutcome.RESPONSE, parsed(status_code, platform_post_id="p-9"))
    assert isinstance(result, Published)
    assert result.platform_post_id == "p-9"


def test_published_uses_the_platforms_own_timestamp_when_supplied() -> None:
    """The platform's record of when it published beats our observation time."""
    platform_time = datetime(2026, 9, 10, 11, 30, tzinfo=UTC)
    result = run(
        TransportOutcome.RESPONSE,
        parsed(200, platform_post_id="p-9", published_at=platform_time),
    )
    assert isinstance(result, Published)
    assert result.published_at == platform_time


def test_published_falls_back_to_observed_at() -> None:
    result = run(TransportOutcome.RESPONSE, parsed(200, platform_post_id="p-9"))
    assert isinstance(result, Published)
    assert result.published_at == NOW


def test_published_carries_the_raw_response_for_audit() -> None:
    """R7: the raw response is persisted. Here it must survive classification."""
    result = run(
        TransportOutcome.RESPONSE,
        parsed(200, platform_post_id="p-9", raw={"id": "p-9", "ok": True}),
    )
    assert isinstance(result, Published)
    assert result.raw_response == {"id": "p-9", "ok": True}


def test_200_with_error_body_is_a_permanent_failure() -> None:
    """architecture.md §3: "HTTP 200, body says error -> Failed(PERMANENT)"."""
    result = run(TransportOutcome.RESPONSE, parsed(200, error=SOME_ERROR))
    assert isinstance(result, Failed)
    assert result.error_class is ErrorClass.PERMANENT


def test_200_without_post_id_or_error_is_unknown_not_success() -> None:
    """A 2xx we cannot interpret is NOT a publish — we hold no proof (R1).

    This is the row where an optimistic implementation returns success and creates the phantom
    publish the whole design exists to prevent.
    """
    result = run(TransportOutcome.RESPONSE, parsed(200))
    assert isinstance(result, Unknown)
    assert not isinstance(result, Published)


# ======================================================================================
# 4xx
# ======================================================================================


@pytest.mark.parametrize("status_code", (401, 403))
def test_auth_failures_require_reconnection(status_code: int) -> None:
    result = run(TransportOutcome.RESPONSE, parsed(status_code))
    assert isinstance(result, RequiresAuthentication)
    assert result.platform == PLATFORM


@pytest.mark.parametrize("status_code", (400, 422))
def test_content_rejections_are_validation_failures(status_code: int) -> None:
    result = run(TransportOutcome.RESPONSE, parsed(status_code))
    assert isinstance(result, Failed)
    assert result.error_class is ErrorClass.VALIDATION


def test_validation_failure_uses_the_platforms_message_when_present() -> None:
    result = run(TransportOutcome.RESPONSE, parsed(400, error=SOME_ERROR))
    assert isinstance(result, Failed)
    assert SOME_ERROR.message in result.message


def test_rate_limit_is_temporary() -> None:
    """architecture.md §3: "HTTP 429 -> Temporary, once, after backoff"."""
    result = run(TransportOutcome.RESPONSE, parsed(429))
    assert isinstance(result, Failed)
    assert result.error_class is ErrorClass.TEMPORARY


@pytest.mark.parametrize("status_code", (404, 405, 409, 410, 418, 451))
def test_other_client_errors_are_unknown(status_code: int) -> None:
    """Unanticipated 4xx codes are Unknown, never Temporary — we do not know what they mean."""
    result = run(TransportOutcome.RESPONSE, parsed(status_code))
    assert isinstance(result, Unknown)


# ======================================================================================
# 5xx — where the asymmetry is least obvious and most important
# ======================================================================================


@pytest.mark.parametrize("status_code", (500, 502, 503, 504))
def test_bare_5xx_is_unknown(status_code: int) -> None:
    """A 5xx from an intermediary tells us nothing about whether the origin accepted the post.

    Treating this as retryable is precisely the duplicate-post bug: the gateway timed out, but the
    platform may have published successfully.
    """
    result = run(TransportOutcome.RESPONSE, parsed(status_code))
    assert isinstance(result, Unknown)


def test_5xx_with_explicit_terminal_body_is_temporary() -> None:
    """architecture.md §3: "HTTP 5xx with explicit terminal body -> Temporary, once".

    Only when the platform itself told us the request failed do we know it did not land.
    """
    result = run(TransportOutcome.RESPONSE, parsed(503, error=SOME_ERROR))
    assert isinstance(result, Failed)
    assert result.error_class is ErrorClass.TEMPORARY


# ======================================================================================
# The asymmetry as a property over the whole status range
# ======================================================================================


@pytest.mark.parametrize("status_code", range(100, 600))
def test_temporary_is_reachable_only_from_the_two_sanctioned_rows(status_code: int) -> None:
    """Sweeps every valid status code and asserts the asymmetry holds universally.

    ``TEMPORARY`` may be produced only by 429, or by a 5xx carrying an explicit error body. Any
    other path to a retryable classification is a bug that would eventually duplicate a post.
    """
    for error in (None, SOME_ERROR):
        result = run(TransportOutcome.RESPONSE, parsed(status_code, error=error))
        if isinstance(result, Failed) and result.error_class is ErrorClass.TEMPORARY:
            assert status_code == 429 or (
                500 <= status_code < 600 and error is not None
            ), f"status {status_code} (error={error is not None}) must not be retryable"


@pytest.mark.parametrize("status_code", range(100, 600))
def test_no_status_code_yields_published_without_a_post_id(status_code: int) -> None:
    """R1 sweeping the entire status range: without a post id, Published is unreachable."""
    result = run(TransportOutcome.RESPONSE, parsed(status_code))
    assert not isinstance(result, Published)


# ======================================================================================
# The raw payload is never consulted
# ======================================================================================


def test_raw_payload_claiming_success_does_not_override_a_server_error() -> None:
    """The raw body is an audit blob, not evidence.

    Here the raw payload insists the post succeeded while the status code says 500 with no
    parseable failure. If the classifier read ``raw``, it would return an unproven success —
    R1's exact violation.
    """
    misleading = parsed(500, raw={"status": "success", "id": "p-999", "published": True})
    result = run(TransportOutcome.RESPONSE, misleading)
    assert isinstance(result, Unknown)
    assert not isinstance(result, Published)


def test_raw_payload_claiming_failure_does_not_override_a_valid_publish() -> None:
    """And the converse: raw must not downgrade a genuine, proven publish."""
    misleading = parsed(
        200, platform_post_id="p-9", raw={"error": "failed", "ok": False}
    )
    result = run(TransportOutcome.RESPONSE, misleading)
    assert isinstance(result, Published)
