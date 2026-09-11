"""Tests for the closed publish-result union — R1 and R2 at the type level.

AGENTS.md R1: "A ``PUBLISHED`` result **must** carry a ``platform_post_id``. It is impossible to
construct one without it." The word *impossible* is the claim under test here. If these tests pass,
the rule holds against a developer who has not read AGENTS.md.

architecture.md §2: "``Published`` cannot be constructed without a ``platform_post_id``. There is no
``success: bool``. An adapter author who has not figured out how to obtain a post ID *cannot* claim
success — the only thing they can build is ``Unknown``, which is the correct answer."
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    RequiresAuthentication,
    Unknown,
)
from pydantic import BaseModel, ValidationError

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
UNION_MEMBERS = (Published, Failed, Unknown, RequiresAuthentication)


# ======================================================================================
# R1 — a Published result cannot exist without proof
# ======================================================================================


def test_published_requires_platform_post_id() -> None:
    """Omitting the post id must fail. This is R1's mechanical guarantee."""
    with pytest.raises(ValidationError):
        Published(published_at=NOW, raw_response={})  # type: ignore[call-arg]


def test_published_rejects_empty_platform_post_id() -> None:
    """An empty string satisfies the type checker but is not proof of anything.

    ``Field(min_length=1)`` closes the loophole a caller would otherwise use to construct a
    ``Published`` while holding no real identifier.
    """
    with pytest.raises(ValidationError):
        Published(platform_post_id="", published_at=NOW, raw_response={})


def test_published_requires_published_at() -> None:
    with pytest.raises(ValidationError):
        Published(platform_post_id="p-1", raw_response={})  # type: ignore[call-arg]


def test_published_requires_raw_response() -> None:
    """R7 wants the raw response retained; making it required keeps the audit trail unskippable."""
    with pytest.raises(ValidationError):
        Published(platform_post_id="p-1", published_at=NOW)  # type: ignore[call-arg]


def test_published_can_be_constructed_with_proof() -> None:
    result = Published(platform_post_id="p-1", published_at=NOW, raw_response={"id": "p-1"})
    assert result.platform_post_id == "p-1"
    assert result.published_at == NOW


def test_published_is_immutable() -> None:
    """Frozen, so a result cannot be mutated into a different claim after the fact.

    Mutable results would let code rewrite an ``Unknown`` into a ``Published`` — the exact
    conversion architecture.md §5 forbids an adapter from performing.
    """
    result = Published(platform_post_id="p-1", published_at=NOW, raw_response={})
    with pytest.raises(ValidationError):
        result.platform_post_id = "p-2"  # type: ignore[misc]


@pytest.mark.parametrize("member", UNION_MEMBERS, ids=lambda m: m.__name__)
def test_no_union_member_exposes_a_success_flag(member: type[BaseModel]) -> None:
    """There is no boolean anywhere that could stand in for proof.

    A ``success: bool`` would reintroduce exactly the ambiguity the union removes: a caller could
    set it true without holding a post id.
    """
    assert "success" not in member.model_fields
    assert "is_success" not in member.model_fields


@pytest.mark.parametrize("member", UNION_MEMBERS, ids=lambda m: m.__name__)
def test_union_members_reject_unknown_fields(member: type[BaseModel]) -> None:
    """``extra="forbid"`` keeps a typo'd field name from being silently ignored."""
    with pytest.raises(ValidationError):
        member(**{"not_a_real_field": "x"})


@pytest.mark.parametrize("member", UNION_MEMBERS, ids=lambda m: m.__name__)
def test_union_members_are_frozen(member: type[BaseModel]) -> None:
    assert member.model_config.get("frozen") is True


# ======================================================================================
# The union is closed and its members are distinguishable
# ======================================================================================


def test_members_are_distinct_types() -> None:
    """``match`` arms rely on these being four different classes, not one class with a flag."""
    instances = [
        Published(platform_post_id="p-1", published_at=NOW, raw_response={}),
        Failed(error_class=ErrorClass.PERMANENT, message="no"),
        Unknown(reason="timeout"),
        RequiresAuthentication(platform="platform-1"),
    ]
    assert len({type(i) for i in instances}) == 4
    for instance in instances:
        assert sum(isinstance(instance, member) for member in UNION_MEMBERS) == 1


def test_unknown_is_constructible_with_no_response_at_all() -> None:
    """A timeout produces no raw response; demanding one would force a caller to invent it."""
    result = Unknown(reason="Request timed out")
    assert result.raw_response is None


def test_unknown_rejects_empty_reason() -> None:
    """The reason is what a support agent reads when the user asks what happened."""
    with pytest.raises(ValidationError):
        Unknown(reason="")


def test_failed_requires_error_class_and_message() -> None:
    with pytest.raises(ValidationError):
        Failed(message="no class")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Failed(error_class=ErrorClass.PERMANENT)  # type: ignore[call-arg]


def test_failed_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        Failed(error_class=ErrorClass.PERMANENT, message="")


def test_requires_authentication_names_the_platform() -> None:
    """README's error guidance requires telling the user which platform was affected."""
    result = RequiresAuthentication(platform="platform-1")
    assert result.platform == "platform-1"
    with pytest.raises(ValidationError):
        RequiresAuthentication(platform="")


def test_error_class_is_exhaustive_over_the_declared_members() -> None:
    """Pins the enum. ``retry_policy`` matches on it with no default, so growth is deliberate."""
    assert {c.value for c in ErrorClass} == {
        "TEMPORARY",
        "PERMANENT",
        "VALIDATION",
        "PERMISSION",
    }
