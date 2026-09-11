"""The platform adapter contract, and the value types crossing it.

README specifies this interface in TypeScript. Per AGENTS.md §4 the backend is Python and per
architecture.md §8 the README's structural sections are superseded, so this is the Python
``Protocol`` form of the same contract: ``get_capabilities``, ``connect``, ``refresh_connection``,
``validate_post``, ``publish_post``, ``verify_post``, ``get_analytics``.

Two AGENTS.md rules are worth stating at the top, because they are the ones an adapter author
breaks by accident:

* §7.3 — "Declare ``get_capabilities()`` honestly. **Overstating a capability is a defect**, because
  the UI uses it to decide what to hide, block, and warn about." A platform that cannot set alt
  text but claims it can produces a publish the user was told would work.
* §7.5 — "Implement ``verify_post()``. If the platform offers no way to verify, return
  ``VerificationResult.unsupported()`` — do not fake a verification." architecture.md §5 adds why:
  faking it "converts a genuine unknown into a false certainty, which is the one thing this system
  must not do."

This module defines the *contract*. ``packages/domain`` must not implement it for any real platform
— adapters live here but their HTTP clients live in ``packages/infrastructure``, which is why
nothing in this file imports an HTTP library.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from asebe_domain.publishing.results import PublishResult
from asebe_domain.publishing.status import PublishingStatus

# ======================================================================================
# Capabilities
# ======================================================================================


class PlatformCapabilities(BaseModel):
    """What a platform can actually do.

    Field names follow Python conventions, unlike README's camelCase matrix, for the reason given in
    architecture.md §8. Every field is required: a capability that was not considered must be stated
    explicitly rather than defaulting to a value that might overstate it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    can_publish: bool
    can_schedule: bool
    can_upload_image: bool
    can_upload_video: bool
    can_set_thumbnail: bool
    can_set_alt_text: bool
    can_set_visibility: bool
    can_read_analytics: bool
    supports_caption_editing: bool

    maximum_file_size_bytes: int = Field(gt=0)
    supported_formats: frozenset[str] = Field(min_length=1)
    maximum_caption_length: int = Field(gt=0)
    maximum_duration_seconds: int | None = None
    """``None`` where the platform imposes no duration limit, or where the concept does not apply
    because it accepts no video."""

    @model_validator(mode="after")
    def _reject_internally_inconsistent_capabilities(self) -> Self:
        """Catch the mechanical forms of overstatement.

        This cannot detect a capability claimed but not implemented — only a human review or a
        contract test per platform can do that. It does catch combinations that are logically
        impossible, which are the ones most likely to be a copy-paste error between adapters.
        """
        if self.can_schedule and not self.can_publish:
            raise ValueError("can_schedule implies can_publish: scheduling is deferred publishing")
        if self.can_upload_video and self.maximum_duration_seconds is None:
            raise ValueError("can_upload_video requires maximum_duration_seconds to be declared")
        if not self.can_upload_video and self.maximum_duration_seconds is not None:
            raise ValueError(
                "maximum_duration_seconds is meaningless when can_upload_video is false; "
                "declaring it overstates what the platform accepts"
            )
        if self.can_set_alt_text and not self.can_upload_image:
            raise ValueError("can_set_alt_text implies can_upload_image")
        return self


# ======================================================================================
# Connection
# ======================================================================================


class ConnectInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authorization_code: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1)


class RefreshInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    refresh_token_ciphertext: str = Field(min_length=1)


class ConnectionResult(BaseModel):
    """The outcome of connecting or refreshing a platform account.

    R14: "Access or refresh tokens never reach the browser, a log line, or an error message."
    These fields carry **ciphertext** and are named accordingly. The domain never sees a plaintext
    token and has no field in which one could be stored — the encryption boundary is the
    infrastructure layer, and the naming makes a mistake visible at the call site.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str = Field(min_length=1)
    account_name: str = Field(min_length=1)
    access_token_ciphertext: str = Field(min_length=1)
    refresh_token_ciphertext: str | None = None
    granted_permissions: frozenset[str] = Field(default_factory=frozenset)
    expires_at: datetime | None = None


# ======================================================================================
# Validation
# ======================================================================================


class ValidationSeverity(StrEnum):
    """README's three validation outcomes, which are not interchangeable.

    ``ERROR`` blocks publishing. ``WARNING`` may proceed after review. ``INFO`` requires no action.
    An adapter that reports a blocking problem as a warning silently converts a blocked publish
    into a failed one on the platform.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationMessage(BaseModel):
    """One validation finding.

    Carries a ``message_key`` and parameters rather than prose, because R13 forbids hardcoded
    visible strings and the interface is localized (README "Localization"). The API layer resolves
    the key against ``packages/contracts``; the domain never emits user-visible text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    severity: ValidationSeverity
    message_key: str = Field(min_length=1)
    field: str | None = None
    params: Mapping[str, object] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """The outcome of validating content against one platform's rules.

    R10: "User content is never silently truncated, translated, or altered. Validation reports; it
    never rewrites." Accordingly this type has no field capable of carrying modified content — a
    validator physically cannot return an adjusted caption. Any adaptation must be surfaced to the
    user for approval, which happens as a ``WARNING`` describing the required change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    messages: tuple[ValidationMessage, ...] = ()

    @property
    def blocking_errors(self) -> tuple[ValidationMessage, ...]:
        return tuple(m for m in self.messages if m.severity is ValidationSeverity.ERROR)

    @property
    def can_publish(self) -> bool:
        """Whether publishing may proceed. Warnings and info do not block; errors do."""
        return not self.blocking_errors


# ======================================================================================
# Publishing
# ======================================================================================


class PublishPostInput(BaseModel):
    """Everything one publish attempt needs.

    ``idempotency_key`` is required and has no default (R6): a publish that reaches an adapter
    without a key cannot have been generated through the sanctioned path, and a default would hide
    that.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_post_key: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    caption: str
    media_url: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    scheduled_at_utc: datetime | None = None


# ======================================================================================
# Verification
# ======================================================================================


class VerificationOutcome(StrEnum):
    """What a verification attempt established.

    ``INCONCLUSIVE`` and ``UNSUPPORTED`` are distinct on purpose. The first means the platform
    could have told us and did not; the second means it has no mechanism to tell us. They lead to
    the same user-facing status (the post stays ``STATUS_UNKNOWN``) but different diagnostics for
    platform-health monitoring (README "Platform-health monitoring").
    """

    CONFIRMED_PUBLISHED = "CONFIRMED_PUBLISHED"
    CONFIRMED_ABSENT = "CONFIRMED_ABSENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNSUPPORTED = "UNSUPPORTED"


class VerificationResult(BaseModel):
    """The outcome of asking a platform whether a post exists.

    Construction goes through the classmethods below so that illegal combinations cannot be built:
    ``CONFIRMED_PUBLISHED`` without a post id would be exactly the unproven success R1 forbids, and
    ``UNSUPPORTED`` carrying a post id would imply a lookup that never happened.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: VerificationOutcome
    platform_post_id: str | None = None
    detail: str | None = None
    checked_at: datetime | None = None

    @classmethod
    def unsupported(cls) -> Self:
        """The platform offers no way to verify. Never a claim that the post does not exist.

        architecture.md §5: an adapter returning anything stronger than this for a platform without
        a lookup mechanism is faking verification.
        """
        return cls(outcome=VerificationOutcome.UNSUPPORTED)

    @classmethod
    def confirmed_published(cls, *, platform_post_id: str, checked_at: datetime) -> Self:
        if not platform_post_id:
            raise ValueError("confirmed_published requires a platform_post_id (R1)")
        return cls(
            outcome=VerificationOutcome.CONFIRMED_PUBLISHED,
            platform_post_id=platform_post_id,
            checked_at=checked_at,
        )

    @classmethod
    def confirmed_absent(cls, *, detail: str, checked_at: datetime) -> Self:
        """The platform positively confirmed the post does not exist.

        Only reachable via lookup by idempotency key or client reference. A platform simply not
        listing the post is ``inconclusive``, not this.
        """
        return cls(
            outcome=VerificationOutcome.CONFIRMED_ABSENT, detail=detail, checked_at=checked_at
        )

    @classmethod
    def inconclusive(cls, *, detail: str, checked_at: datetime) -> Self:
        return cls(outcome=VerificationOutcome.INCONCLUSIVE, detail=detail, checked_at=checked_at)

    @property
    def resolves_status(self) -> PublishingStatus | None:
        """The status this verification justifies moving to, or ``None`` if it settles nothing.

        Returning ``None`` — rather than defaulting to a status — keeps the caller from treating an
        unresolved verification as progress. The post stays ``STATUS_UNKNOWN``.
        """
        match self.outcome:
            case VerificationOutcome.CONFIRMED_PUBLISHED:
                return PublishingStatus.PUBLISHED
            case VerificationOutcome.CONFIRMED_ABSENT:
                return PublishingStatus.FAILED
            case VerificationOutcome.INCONCLUSIVE | VerificationOutcome.UNSUPPORTED:
                return None


# ======================================================================================
# Analytics
# ======================================================================================


class AnalyticsResult(BaseModel):
    """Per-platform metrics, with the provenance README requires for every metric.

    README: every metric must show source platform, measurement period, last-updated time,
    definition, whether it is direct or estimated, and whether it is unavailable. ``estimated``
    and ``unavailable`` are explicit rather than implied by a missing value, because README forbids
    comparing metrics across platforms as though the definitions were identical.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    collected_at: datetime
    metrics: Mapping[str, int]
    estimated: frozenset[str] = Field(default_factory=frozenset)
    unavailable: frozenset[str] = Field(default_factory=frozenset)


# ======================================================================================
# The protocol
# ======================================================================================


@runtime_checkable
class PlatformAdapter(Protocol):
    """The contract every platform integration satisfies — README's interface, in Python.

    AGENTS.md §7.2: "Implement the ``PlatformAdapter`` protocol exactly. Do not widen it — adding a
    method to the protocol is a change to all eight adapters."

    Methods are ``async`` because every implementation performs network I/O; a synchronous protocol
    would force a thread pool on all eight adapters to satisfy one that happens to block.
    """

    @property
    def name(self) -> str:
        """Stable identifier used in URLs, capability lookups, audit rows and error messages."""
        ...

    def get_capabilities(self) -> PlatformCapabilities:
        """Declared capabilities. Must be honest — see the module docstring (§7.3)."""
        ...

    async def connect(self, *, input: ConnectInput) -> ConnectionResult: ...

    async def refresh_connection(self, *, input: RefreshInput) -> ConnectionResult: ...

    async def validate_post(
        self,
        *,
        caption: str,
        media_type: str,
        media_size_bytes: int,
        duration_seconds: int | None = None,
    ) -> ValidationResult: ...

    async def publish_post(self, *, input: PublishPostInput) -> PublishResult:
        """Perform one publish attempt.

        Must return ``Unknown`` for any outcome it did not fully understand, and must never raise
        for a platform-reported failure — R2 routes failures through the union, and an escaping
        exception at the call site is the shape of bug AGENTS.md §8 forbids ("Never ``try/except``
        around a platform call and swallow the error").
        """
        ...

    async def verify_post(
        self,
        *,
        platform_post_key: str,
        idempotency_key: str,
    ) -> VerificationResult:
        """Ask the platform whether the post exists. See ``VerificationResult`` for the rules."""
        ...

    async def get_analytics(self, *, platform_post_id: str) -> AnalyticsResult: ...


__all__ = [
    "AnalyticsResult",
    "ConnectInput",
    "ConnectionResult",
    "PlatformAdapter",
    "PlatformCapabilities",
    "PublishPostInput",
    "RefreshInput",
    "ValidationMessage",
    "ValidationResult",
    "ValidationSeverity",
    "VerificationOutcome",
    "VerificationResult",
]
