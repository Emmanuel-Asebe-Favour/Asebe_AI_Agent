"""Exhaustive tests for the publishing state machine (R8).

AGENTS.md §7 requires, for any change to the state machine:

    "Prove no illegal transition became legal: the exhaustive test iterates all (from, to) pairs
     and asserts against the table."

So the core of this file is a sweep of all 9 x 9 = 81 ordered pairs.

``README_SPEC`` below is transcribed by hand from README's "Allowed state transitions" block. It is
deliberately a *second, independent* encoding of the same rules: if the implementation table in
state_machine.py were edited to match a mistaken reading of the README, a test that compared the
table to itself would still pass. Comparing against a hand-copied literal does not.

The two spec gaps this file used to pin — see docs/adr/0001 and docs/adr/0002 — have since been
accepted and applied. The assertions that recorded them are therefore inverted: they now assert
those transitions exist, and fail if one is removed.
"""

from __future__ import annotations

import itertools

import pytest

from asebe_domain.publishing.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    IllegalTransitionError,
    allowed_targets,
    can_transition,
    transition,
)
from asebe_domain.publishing.status import PublishingStatus

# Transcribed by hand from README "Allowed state transitions". Do not regenerate this from
# ALLOWED_TRANSITIONS — that would make the test tautological.
README_SPEC: frozenset[tuple[str, str]] = frozenset(
    {
        ("DRAFT", "SCHEDULED"),
        ("DRAFT", "PUBLISHING"),
        ("SCHEDULED", "PUBLISHING"),
        ("SCHEDULED", "CANCELLED"),
        ("PUBLISHING", "PUBLISHED"),
        ("PUBLISHING", "FAILED"),
        ("PUBLISHING", "STATUS_UNKNOWN"),
        ("PUBLISHING", "REQUIRES_AUTHENTICATION"),
        ("FAILED", "PUBLISHING"),
        ("STATUS_UNKNOWN", "REQUIRES_USER_REVIEW"),
        ("STATUS_UNKNOWN", "PUBLISHED"),
        ("STATUS_UNKNOWN", "FAILED"),
        ("REQUIRES_USER_REVIEW", "PUBLISHING"),
        ("REQUIRES_USER_REVIEW", "CANCELLED"),
    }
)

ALL_STATUSES = tuple(PublishingStatus)
ALL_PAIRS = tuple(itertools.product(ALL_STATUSES, repeat=2))

# Terminal statuses in enum declaration order, for stable parametrize IDs.
#
# Derived by filtering the enum rather than by sorting TERMINAL_STATUSES.
# ``sorted(TERMINAL_STATUSES,
# key=...)`` does NOT type-check here: mypy reports the key as ``Callable[[PublishingStatus], str]``
# against an expected ``Callable[[object], ...]``, meaning it fails to solve sorted()'s type
# variable from ``frozenset[PublishingStatus]`` and falls back to that variable's ``object`` bound.
# The annotation on TERMINAL_STATUSES is not the cause -- it is explicit in state_machine.py, and
# mypy reports that module clean, with and without --no-incremental. Iterating PublishingStatus
# directly yields the same statuses in declaration order without depending on that inference.
TERMINAL_IN_DECLARATION_ORDER: list[PublishingStatus] = [
    status for status in PublishingStatus if status in TERMINAL_STATUSES
]


def test_status_enum_matches_readme_publishing_statuses() -> None:
    """The nine statuses are exactly those README lists, with no additions."""
    assert {s.value for s in ALL_STATUSES} == {
        "DRAFT",
        "SCHEDULED",
        "PUBLISHING",
        "PUBLISHED",
        "FAILED",
        "STATUS_UNKNOWN",
        "CANCELLED",
        "REQUIRES_AUTHENTICATION",
        "REQUIRES_USER_REVIEW",
    }


def test_table_contains_exactly_the_readme_transitions() -> None:
    """Guards against a transition being added to the table but not to the spec, or vice versa."""
    implemented = {
        (current.value, target.value)
        for current, targets in ALLOWED_TRANSITIONS.items()
        for target in targets
    }
    assert implemented == set(README_SPEC)


def test_every_status_appears_as_a_table_key() -> None:
    """A status missing from the table would raise KeyError instead of refusing a transition."""
    assert set(ALLOWED_TRANSITIONS) == set(ALL_STATUSES)


@pytest.mark.parametrize(("current", "target"), ALL_PAIRS)
def test_all_81_pairs_against_spec(current: PublishingStatus, target: PublishingStatus) -> None:
    """The exhaustive sweep: every ordered pair, legal iff the README says so.

    This is the assertion AGENTS.md §7 asks for. It fails if any transition becomes legal that is
    not in the spec, and equally if one silently becomes illegal.
    """
    expected = (current.value, target.value) in README_SPEC
    assert can_transition(current, target) is expected


@pytest.mark.parametrize(("current", "target"), ALL_PAIRS)
def test_transition_returns_target_or_raises(
    current: PublishingStatus, target: PublishingStatus
) -> None:
    """``transition`` is total: it yields the target status or raises, never a third thing."""
    if (current.value, target.value) in README_SPEC:
        assert transition(current, target) is target
    else:
        with pytest.raises(IllegalTransitionError):
            transition(current, target)


@pytest.mark.parametrize(("current", "target"), ALL_PAIRS)
def test_allowed_targets_agrees_with_can_transition(
    current: PublishingStatus, target: PublishingStatus
) -> None:
    """The two query functions must not disagree — they are the same table read two ways."""
    assert (target in allowed_targets(current)) is can_transition(current, target)


def test_illegal_transition_error_names_both_statuses_and_the_alternatives() -> None:
    """The message must be actionable: what was attempted, and what was permitted instead."""
    with pytest.raises(IllegalTransitionError) as excinfo:
        transition(PublishingStatus.PUBLISHED, PublishingStatus.PUBLISHING)

    error = excinfo.value
    assert error.current is PublishingStatus.PUBLISHED
    assert error.target is PublishingStatus.PUBLISHING
    assert "PUBLISHED" in str(error)
    assert "PUBLISHING" in str(error)


def test_published_cannot_be_republished() -> None:
    """README's explicit example of an invalid transition."""
    assert not can_transition(PublishingStatus.PUBLISHED, PublishingStatus.PUBLISHING)
    with pytest.raises(IllegalTransitionError):
        transition(PublishingStatus.PUBLISHED, PublishingStatus.PUBLISHING)


@pytest.mark.parametrize("status", TERMINAL_IN_DECLARATION_ORDER)
def test_terminal_statuses_are_exactly_the_declared_ones(status: PublishingStatus) -> None:
    """No status may be terminal by accident: the set is derived, and pinned here."""
    assert allowed_targets(status) == frozenset()


def test_terminal_statuses_derivation() -> None:
    """Two terminal by product design, one by ADR 0001.

    PUBLISHED is done, CANCELLED is abandoned, and REQUIRES_AUTHENTICATION is terminal because
    recovery is the connector flow rather than a transition of this post. REQUIRES_USER_REVIEW is
    deliberately absent: ADR 0002 made it escapable, and if it reappears here that ADR has been
    undone without anyone noticing.
    """
    assert (
        frozenset(
            {
                PublishingStatus.PUBLISHED,
                PublishingStatus.CANCELLED,
                PublishingStatus.REQUIRES_AUTHENTICATION,
            }
        )
        == TERMINAL_STATUSES
    )


def test_table_is_immutable() -> None:
    """A caller must not be able to add a transition by mutating the table at runtime."""
    with pytest.raises(TypeError):
        ALLOWED_TRANSITIONS[PublishingStatus.PUBLISHED] = frozenset(  # type: ignore[index]
            {PublishingStatus.PUBLISHING}
        )


# ======================================================================================
# The ADRs, applied — formerly spec gaps, now asserted as required behaviour
#
# These tests used to assert the opposite: that REQUIRES_AUTHENTICATION had no inbound transition
# and REQUIRES_USER_REVIEW had no outbound one. They were written that way so the gap could not be
# forgotten, and so that applying an ADR required changing a test as well as a table. Both ADRs
# have since been accepted and applied, which inverted them.
# ======================================================================================


def test_requires_authentication_is_reachable_from_publishing_only() -> None:
    """ADR 0001: exactly one transition leads to REQUIRES_AUTHENTICATION.

    "From publishing only" is the load-bearing half, and it is why this asserts an exact list
    rather than mere non-emptiness. A second inbound transition — from FAILED, say — would keep a
    weaker test passing while making the status reachable from a state whose meaning is "the
    platform definitively rejected this", which is a different claim entirely.
    """
    inbound = [
        current
        for current, targets in ALLOWED_TRANSITIONS.items()
        if PublishingStatus.REQUIRES_AUTHENTICATION in targets
    ]
    assert inbound == [PublishingStatus.PUBLISHING], (
        f"expected exactly PUBLISHING to lead to REQUIRES_AUTHENTICATION, found {inbound}"
    )


def test_requires_authentication_stays_terminal() -> None:
    """ADR 0001 leaves no exit, deliberately.

    Recovering from an expired connection is the connector flow — the user reconnects the account —
    not a transition of this post. If that judgement is ever reversed it needs its own ADR, and
    this test is where the reversal has to be acknowledged.
    """
    assert allowed_targets(PublishingStatus.REQUIRES_AUTHENTICATION) == frozenset()


def test_requires_user_review_exits_are_exactly_the_two_permitted_ones() -> None:
    """ADR 0002: review is escapable, but only those two ways.

    ``→ PUBLISHING`` is the manual retry README's "Failure workflow" describes; ``→ CANCELLED`` is
    the user abandoning a post they no longer want. An exact set, not a superset: an extra target
    would be a route out of review that nobody decided on.

    Note what this test cannot check. Both transitions are required to be user-initiated, and the
    state machine has no way to express that — it is the caller's obligation, discharged by the
    permission check and audit write on the API route. Nothing here prevents a background job from
    calling them, which is why the transition table carries the warning instead.
    """
    assert allowed_targets(PublishingStatus.REQUIRES_USER_REVIEW) == frozenset(
        {PublishingStatus.PUBLISHING, PublishingStatus.CANCELLED}
    )
