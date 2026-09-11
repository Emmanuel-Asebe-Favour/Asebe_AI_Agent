"""Maps an observed platform outcome onto the closed union — R2 in mechanical form.

architecture.md §3 gives the table this module implements, and states the principle behind it:

    "The asymmetry is deliberate: **anything we did not fully understand is `Unknown`**, because
     `Unknown` is safe and `Temporary` is not. A mistaken `Temporary` causes a duplicate post; a
     mistaken `Unknown` causes a user to check their account."

That asymmetry is the entire reason this module exists as its own responsibility rather than as a
few conditionals inside each adapter. Every default in the ``if``/``elif`` chain below falls to
``Unknown``; there is no path that reaches ``TEMPORARY`` without the platform having explicitly
said something retryable.

The trust boundary lives here too (AGENTS.md §6). The adapter strictly parses the platform's wire
format into ``ParsedPlatformResponse``; a body that cannot be parsed is represented by ``None``,
never by a half-populated object. "Unparseable" and "empty" are therefore indistinguishable to the
caller — which is correct, because we cannot tell them apart either, and both mean we do not know.

The domain does not own the clock. ``observed_at`` is supplied by the caller (the infrastructure
layer, which has a clock), so this function stays a pure function of its arguments and its tests
are deterministic rather than time-dependent.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    PublishResult,
    RawPlatformResponse,
    RequiresAuthentication,
    Unknown,
)


class TransportOutcome(StrEnum):
    """What happened at the transport layer, before any interpretation.

    Kept distinct from the HTTP status because a timeout and a 500 are different facts even
    though both leave us ignorant: the first may mean the platform never saw the request, or may
    mean it saw it and the reply was lost; the second at least means a server responded.
    """

    RESPONSE = "RESPONSE"
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"


class PlatformErrorBody(BaseModel):
    """An error the platform reported in a body we successfully parsed.

    Its presence *is* the evidence that the platform explicitly told us the request failed — the
    "explicit terminal body" of architecture.md §3. No separate boolean is offered, because a flag
    would let a caller assert explicitness the parse did not actually establish.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class ParsedPlatformResponse(BaseModel):
    """A platform response the adapter successfully understood.

    Constructing this at all is the claim "we parsed this". An unparseable body must be passed to
    ``classify`` as ``None`` instead — there is deliberately no ``parse_failed=True`` variant to
    reach for, so an adapter author cannot accidentally assert understanding they do not have.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status_code: int = Field(ge=100, le=599)
    platform_post_id: str | None = None
    error: PlatformErrorBody | None = None
    published_at: datetime | None = None
    """The platform's own timestamp for the post, when it supplies one. Preferred over
    ``observed_at`` because it is the platform's record rather than ours."""
    raw: RawPlatformResponse


def classify(
    *,
    platform: str,
    outcome: TransportOutcome,
    observed_at: datetime,
    response: ParsedPlatformResponse | None = None,
) -> PublishResult:
    """Interpret one publishing attempt.

    ``platform`` is required only so a ``RequiresAuthentication`` result can name which connection
    needs reconnecting — README's error guidance requires telling the user which platform was
    affected. ``observed_at`` is the caller's clock reading for this attempt.

    Reads only parsed fields. ``response.raw`` is attached to results for auditing (R7) and is
    never consulted to reach a decision; tests/publishing/test_error_classifier.py asserts that by
    passing raw payloads deliberately contradicting their own status codes.
    """
    match outcome:
        case TransportOutcome.TIMEOUT:
            return Unknown(reason="Request timed out; the platform may have received the post.")

        case TransportOutcome.CONNECTION_ERROR:
            return Unknown(
                reason="Connection failed before a response was received; "
                "the platform may have received the post."
            )

        case TransportOutcome.RESPONSE:
            if response is None:
                # A response arrived but we could not parse it. Treating this as anything other
                # than Unknown is the exact mistake this module exists to prevent.
                return Unknown(
                    reason="Response received but could not be parsed; "
                    "the platform may have received the post."
                )
            return _classify_parsed(platform=platform, observed_at=observed_at, response=response)


def _classify_parsed(
    *,
    platform: str,
    observed_at: datetime,
    response: ParsedPlatformResponse,
) -> PublishResult:
    """Interpret a response we successfully parsed, by status code.

    Ordered most-specific-first. The final ``return`` is ``Unknown``, so a status code nobody
    anticipated is safe by default rather than optimistically retryable.
    """
    status = response.status_code

    if 200 <= status < 300:
        if response.platform_post_id is not None:
            # The only path to Published, and it requires the platform's own post identifier (R1).
            return Published(
                platform_post_id=response.platform_post_id,
                published_at=response.published_at or observed_at,
                raw_response=response.raw,
            )
        if response.error is not None:
            # A 200 that reports a business error. The platform is telling us it did not publish,
            # and telling it again will not change its mind.
            return Failed(
                error_class=ErrorClass.PERMANENT,
                message=f"Platform reported an error: {response.error.message}",
            )
        # 2xx, parsed, but no post id and no error. We do not know what this means, which makes it
        # Unknown — NOT a success, because we have no proof (R1).
        return Unknown(
            reason="Platform returned a success status with no post identifier; "
            "cannot confirm the post exists.",
            raw_response=response.raw,
        )

    if status in (401, 403):
        return RequiresAuthentication(platform=platform)

    if status in (400, 422):
        return Failed(
            error_class=ErrorClass.VALIDATION,
            message=(
                response.error.message
                if response.error is not None
                else "Platform rejected the content as invalid."
            ),
        )

    if status == 429:
        return Failed(
            error_class=ErrorClass.TEMPORARY,
            message="Platform rate limit reached.",
        )

    if 500 <= status < 600:
        # Temporary ONLY when the platform explicitly reported a failure in a body we parsed.
        # A bare 5xx from an intermediary means we cannot tell whether the origin accepted the
        # post, so it is Unknown and must not be retried.
        if response.error is not None:
            return Failed(
                error_class=ErrorClass.TEMPORARY,
                message=f"Platform reported a temporary server failure: {response.error.message}",
            )
        return Unknown(
            reason=f"Server error ({status}) with no interpretable body; "
            "cannot determine whether the post was accepted.",
            raw_response=response.raw,
        )

    return Unknown(
        reason=f"Unrecognised response status {status}; cannot determine the outcome.",
        raw_response=response.raw,
    )


__all__ = [
    "ParsedPlatformResponse",
    "PlatformErrorBody",
    "TransportOutcome",
    "classify",
]
