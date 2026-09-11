"""Tests for the adapter contract — capabilities honesty, verification, and R6 at the boundary.

AGENTS.md §7's adapter recipe names the failure modes these tests guard:

* §7.3 — "Declare ``get_capabilities()`` honestly. **Overstating a capability is a defect**, because
  the UI uses it to decide what to hide, block, and warn about."
* §7.5 — "Implement ``verify_post()``. If the platform offers no way to verify, return
  ``VerificationResult.unsupported()`` — do not fake a verification."

Capabilities cannot be tested for truth — only the platform knows. What can be tested is that a
*copy-paste error between adapters* is caught, and that the value types make the forbidden claims
unconstructible.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from asebe_domain.adapters.protocol import (
    AnalyticsResult,
    ConnectInput,
    ConnectionResult,
    PlatformAdapter,
    PlatformCapabilities,
    PublishPostInput,
    RefreshInput,
    ValidationMessage,
    ValidationResult,
    ValidationSeverity,
    VerificationOutcome,
    VerificationResult,
)
from asebe_domain.publishing.results import Unknown
from pydantic import ValidationError

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


def capabilities(**overrides: object) -> PlatformCapabilities:
    """A coherent baseline an adapter would plausibly declare, for tests to perturb."""
    base: dict[str, object] = {
        "can_publish": True,
        "can_schedule": True,
        "can_upload_image": True,
        "can_upload_video": True,
        "can_set_thumbnail": True,
        "can_set_alt_text": True,
        "can_set_visibility": True,
        "can_read_analytics": True,
        "supports_caption_editing": True,
        "maximum_file_size_bytes": 100_000_000,
        "supported_formats": frozenset({"image/jpeg", "video/mp4"}),
        "maximum_caption_length": 2200,
        "maximum_duration_seconds": 600,
    }
    base.update(overrides)
    # model_validate rather than the constructor: the tests deliberately pass wrong *types* and
    # forbidden combinations, which the typed constructor signature describes as impossible.
    # Going through validation is what the runtime actually does, so it is both what we want to
    # exercise and immune to the mypy plugin's constructor checking. Suppressing that check would
    # instead need a ``type: ignore`` whose error code is easy to get wrong -- and spelling the
    # directive literally in a comment makes mypy reject this file outright, which it did.
    return PlatformCapabilities.model_validate(base)


# ======================================================================================
# Capabilities
# ======================================================================================


def test_coherent_capabilities_are_accepted() -> None:
    assert capabilities().can_publish is True


def test_capabilities_are_immutable() -> None:
    """Capabilities drive UI decisions; mutating them mid-request makes those racy."""
    with pytest.raises(ValidationError):
        capabilities().can_publish = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_file_size_bytes", 0),
        ("maximum_file_size_bytes", -1),
        ("maximum_caption_length", 0),
        ("supported_formats", frozenset()),
    ],
)
def test_nonsensical_capability_values_are_rejected(field: str, value: object) -> None:
    """A zero limit or an empty format set blocks every publish while claiming to support it."""
    with pytest.raises(ValidationError):
        capabilities(**{field: value})


def test_scheduling_without_publishing_is_rejected() -> None:
    """Scheduling is deferred publishing — claiming it without publishing is incoherent."""
    with pytest.raises(ValidationError, match="can_schedule implies can_publish"):
        capabilities(can_publish=False, can_schedule=True)


def test_video_capability_requires_a_declared_duration_limit() -> None:
    """§7.3: overstating here means the UI hides no warning for an over-long video."""
    with pytest.raises(ValidationError, match="can_upload_video requires maximum_duration_seconds"):
        capabilities(can_upload_video=True, maximum_duration_seconds=None)


def test_declaring_a_duration_limit_without_video_is_rejected() -> None:
    """The converse overstatement: advertising a video constraint for a platform taking no video."""
    with pytest.raises(ValidationError, match="maximum_duration_seconds is meaningless"):
        capabilities(can_upload_video=False, maximum_duration_seconds=600)


def test_alt_text_without_image_upload_is_rejected() -> None:
    with pytest.raises(ValidationError, match="can_set_alt_text implies can_upload_image"):
        capabilities(can_upload_image=False, can_set_alt_text=True)


def test_image_only_platform_is_representable() -> None:
    """The validator must not reject an honest, limited platform — only dishonest ones."""
    caps = capabilities(
        can_upload_video=False, maximum_duration_seconds=None, can_set_thumbnail=False
    )
    assert caps.can_upload_video is False
    assert caps.maximum_duration_seconds is None


def test_publish_only_platform_is_representable() -> None:
    caps = capabilities(can_schedule=False)
    assert caps.can_publish is True


# ======================================================================================
# Verification — §7.5, "do not fake a verification"
# ======================================================================================


def test_unsupported_verification_claims_nothing() -> None:
    result = VerificationResult.unsupported()
    assert result.outcome is VerificationOutcome.UNSUPPORTED
    assert result.platform_post_id is None


def test_unsupported_verification_resolves_no_status() -> None:
    """architecture.md §5: the post stays Unknown and goes to REQUIRES_USER_REVIEW.

    Returning a status here would convert an honest "we cannot check" into a false certainty.
    """
    assert VerificationResult.unsupported().resolves_status is None


def test_confirmed_published_requires_a_post_id() -> None:
    with pytest.raises(ValueError, match="requires a platform_post_id"):
        VerificationResult.confirmed_published(platform_post_id="", checked_at=NOW)


def test_confirmed_published_resolves_to_published() -> None:
    result = VerificationResult.confirmed_published(platform_post_id="p-1", checked_at=NOW)
    assert result.resolves_status is not None
    assert result.resolves_status.value == "PUBLISHED"


def test_confirmed_absent_resolves_to_failed() -> None:
    """Only a positive lookup result — by idempotency key or reference — may reach this."""
    result = VerificationResult.confirmed_absent(detail="no such post", checked_at=NOW)
    assert result.resolves_status is not None
    assert result.resolves_status.value == "FAILED"


def test_inconclusive_resolves_no_status() -> None:
    """The platform could have told us and did not. That is not evidence of absence."""
    result = VerificationResult.inconclusive(detail="lookup unavailable", checked_at=NOW)
    assert result.resolves_status is None
    assert result.outcome is not VerificationOutcome.CONFIRMED_ABSENT


def test_verification_result_is_immutable() -> None:
    """Frozen for the same reason publish results are: an adapter must not be able to turn an
    honest "unsupported" into a claimed confirmation after the fact."""
    result = VerificationResult.unsupported()
    with pytest.raises(ValidationError):
        result.outcome = VerificationOutcome.CONFIRMED_PUBLISHED  # type: ignore[misc]


# ======================================================================================
# Validation — R10, and the three severities
# ======================================================================================


def test_validation_result_has_no_field_for_modified_content() -> None:
    """R10: "Validation reports; it never rewrites."

    A validator must not be able to hand back an adjusted caption. The absence of such a field is
    the enforcement — there is nowhere to put rewritten content.
    """
    fields = set(ValidationResult.model_fields)
    assert fields == {"messages"}
    for suspicious in ("caption", "rewritten_caption", "adjusted", "modified", "truncated"):
        assert suspicious not in fields


def test_blocking_error_prevents_publishing() -> None:
    result = ValidationResult(
        messages=(
            ValidationMessage(
                severity=ValidationSeverity.ERROR,
                message_key="validation.caption.too_long",
            ),
        )
    )
    assert result.can_publish is False
    assert len(result.blocking_errors) == 1


def test_warnings_do_not_block_publishing() -> None:
    """README: warnings may proceed after review. Reporting one as blocking is its own bug."""
    result = ValidationResult(
        messages=(
            ValidationMessage(
                severity=ValidationSeverity.WARNING,
                message_key="validation.preview.approximation",
            ),
        )
    )
    assert result.can_publish is True
    assert result.blocking_errors == ()


def test_info_does_not_block_publishing() -> None:
    result = ValidationResult(
        messages=(
            ValidationMessage(severity=ValidationSeverity.INFO, message_key="info.scheduled_utc"),
        )
    )
    assert result.can_publish is True


def test_empty_validation_result_permits_publishing() -> None:
    assert ValidationResult().can_publish is True


def test_validation_messages_carry_keys_not_prose() -> None:
    """R13: no hardcoded visible strings — the interface is localized (README "Localization")."""
    message = ValidationMessage(
        severity=ValidationSeverity.ERROR,
        message_key="validation.media.too_large",
        field="media",
        params={"max_bytes": 100_000_000},
    )
    assert message.message_key == "validation.media.too_large"
    assert " " not in message.message_key


# ======================================================================================
# Publish input — R6 at the adapter boundary
# ======================================================================================


def test_publish_input_requires_an_idempotency_key() -> None:
    """R6 with no default: a publish reaching an adapter without a key did not come from the
    sanctioned path, and a default would hide that."""
    with pytest.raises(ValidationError):
        PublishPostInput(  # type: ignore[call-arg]
            platform_post_key="post-1",
            attempt_number=1,
            caption="hello",
            media_url="s3://bucket/key",
            media_type="image/jpeg",
        )


@pytest.mark.parametrize("attempt_number", (0, -1))
def test_publish_input_rejects_non_positive_attempt_number(attempt_number: int) -> None:
    with pytest.raises(ValidationError):
        PublishPostInput(
            platform_post_key="post-1",
            idempotency_key="k",
            attempt_number=attempt_number,
            caption="hello",
            media_url="s3://bucket/key",
            media_type="image/jpeg",
        )


def test_publish_input_accepts_a_complete_request() -> None:
    request = PublishPostInput(
        platform_post_key="post-1",
        idempotency_key="k-1",
        attempt_number=1,
        caption="hello",
        media_url="s3://bucket/key",
        media_type="image/jpeg",
    )
    assert request.scheduled_at_utc is None


# ======================================================================================
# R14 — tokens are ciphertext, and there is no plaintext field to misuse
# ======================================================================================


def test_connection_result_exposes_no_plaintext_token_fields() -> None:
    """R14: tokens never reach the browser or a log line.

    The domain carries ciphertext only. Naming the fields ``*_ciphertext`` means a developer who
    has not read R14 still cannot store a plaintext token — there is no field for one.
    """
    fields = set(ConnectionResult.model_fields)
    assert "access_token_ciphertext" in fields
    assert "access_token" not in fields
    assert "refresh_token" not in fields
    assert "password" not in fields
    assert not any(f.endswith(("_secret", "_plaintext")) for f in fields)


# ======================================================================================
# The protocol itself
# ======================================================================================


class _FakeAdapter:
    """A structurally conforming adapter. Nothing here talks to a network."""

    @property
    def name(self) -> str:
        return "fake"

    def get_capabilities(self) -> PlatformCapabilities:
        return capabilities()

    async def connect(self, *, input: ConnectInput) -> ConnectionResult:
        raise NotImplementedError

    async def refresh_connection(self, *, input: RefreshInput) -> ConnectionResult:
        raise NotImplementedError

    async def validate_post(
        self,
        *,
        caption: str,
        media_type: str,
        media_size_bytes: int,
        duration_seconds: int | None = None,
    ) -> ValidationResult:
        return ValidationResult()

    async def publish_post(self, *, input: PublishPostInput):  # type: ignore[no-untyped-def]
        return Unknown(reason="not implemented in the fake")

    async def verify_post(
        self, *, platform_post_key: str, idempotency_key: str
    ) -> VerificationResult:
        return VerificationResult.unsupported()

    async def get_analytics(self, *, platform_post_id: str) -> AnalyticsResult:
        raise NotImplementedError


def test_a_conforming_adapter_satisfies_the_protocol() -> None:
    """Structural conformance, not inheritance — adapters need not import the domain's Protocol."""
    assert isinstance(_FakeAdapter(), PlatformAdapter)


def test_an_incomplete_adapter_does_not_satisfy_the_protocol() -> None:
    """The check must be able to fail, or the previous test proves nothing."""

    class _Incomplete:
        @property
        def name(self) -> str:
            return "incomplete"

        def get_capabilities(self) -> PlatformCapabilities:
            return capabilities()

    assert not isinstance(_Incomplete(), PlatformAdapter)


@pytest.mark.asyncio
async def test_a_fake_adapter_can_return_unknown_without_raising() -> None:
    """An adapter reporting it does not know is a valid, non-exceptional outcome (R2)."""
    adapter = _FakeAdapter()
    result = await adapter.publish_post(
        input=PublishPostInput(
            platform_post_key="post-1",
            idempotency_key="k-1",
            attempt_number=1,
            caption="hi",
            media_url="s3://bucket/key",
            media_type="image/jpeg",
        )
    )
    assert isinstance(result, Unknown)


def test_protocol_covers_every_method_readme_specifies() -> None:
    """README's interface: getCapabilities, connect, refreshConnection, validatePost, publishPost,
    verifyPost, getAnalytics. Missing one would be discovered only when the first adapter is
    written against it."""
    expected = {
        "name",
        "get_capabilities",
        "connect",
        "refresh_connection",
        "validate_post",
        "publish_post",
        "verify_post",
        "get_analytics",
    }
    assert expected <= set(dir(PlatformAdapter))
