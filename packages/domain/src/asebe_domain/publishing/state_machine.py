"""The one and only place publishing transition rules exist (R8).

AGENTS.md §8 forbids writing a status transition anywhere else, and README's "Allowed state
transitions" block is the spec. The table below is a literal transcription of that block — no
transition is present here that is absent there, and none is missing.

The two gaps in the spec are transcribed faithfully rather than quietly fixed. AGENTS.md §11 is
explicit that a rule believed wrong must be raised via an ADR, not silently deviated from:

1. ``REQUIRES_AUTHENTICATION`` is a declared status with **no transition into it**, even though
   architecture.md §2 defines a ``RequiresAuthentication`` publish *result* and maps HTTP 401/403
   to it. The classifier can therefore produce an outcome the state machine cannot record.
   See docs/adr/0001.

2. ``REQUIRES_USER_REVIEW`` has **no transition out of it**, which makes README's own
   "Failure workflow" (review, then retry) unreachable in the state machine.
   See docs/adr/0002.

Both are asserted as-is by tests/publishing/test_state_machine.py, so the gap exists in executable
form rather than only in prose, and closing it will require changing a test as well as a table.

This module is pure: it decides legality and returns the resulting status. Persisting the change is
the infrastructure layer's job — see the transactional boundary in architecture.md §4.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from asebe_domain.publishing.status import PublishingStatus

# Transcribed from README "Allowed state transitions":
#
#   DRAFT → SCHEDULED
#   DRAFT → PUBLISHING
#   SCHEDULED → PUBLISHING
#   SCHEDULED → CANCELLED
#   PUBLISHING → PUBLISHED
#   PUBLISHING → FAILED
#   PUBLISHING → STATUS_UNKNOWN
#   FAILED → PUBLISHING
#   STATUS_UNKNOWN → REQUIRES_USER_REVIEW
#
# MappingProxyType makes this read-only at runtime: a caller cannot add a transition by mutating
# the table, which would be the one way to bypass the "only place transition rules exist" rule.
ALLOWED_TRANSITIONS: Mapping[PublishingStatus, frozenset[PublishingStatus]] = MappingProxyType(
    {
        PublishingStatus.DRAFT: frozenset(
            {PublishingStatus.SCHEDULED, PublishingStatus.PUBLISHING}
        ),
        PublishingStatus.SCHEDULED: frozenset(
            {PublishingStatus.PUBLISHING, PublishingStatus.CANCELLED}
        ),
        PublishingStatus.PUBLISHING: frozenset(
            {
                PublishingStatus.PUBLISHED,
                PublishingStatus.FAILED,
                PublishingStatus.STATUS_UNKNOWN,
            }
        ),
        PublishingStatus.FAILED: frozenset({PublishingStatus.PUBLISHING}),
        PublishingStatus.STATUS_UNKNOWN: frozenset({PublishingStatus.REQUIRES_USER_REVIEW}),
        # Terminals, and the two spec gaps. Listed explicitly rather than omitted, so that
        # "this status appears in the table" and "this status has somewhere to go" are
        # distinguishable at a glance.
        PublishingStatus.PUBLISHED: frozenset(),
        PublishingStatus.CANCELLED: frozenset(),
        PublishingStatus.REQUIRES_AUTHENTICATION: frozenset(),  # gap: nothing leads here
        PublishingStatus.REQUIRES_USER_REVIEW: frozenset(),  # gap: nothing leads out
    }
)

def _derive_terminal_statuses() -> frozenset[PublishingStatus]:
    """Statuses from which no transition is permitted. Derived, never hand-maintained.

    Written as an explicit loop over the enum rather than a generator over
    ``ALLOWED_TRANSITIONS.items()``. The generator form type-checked as ``frozenset[object]`` at
    its use sites: mypy reported ``Argument "key" to "sorted" has incompatible type
    Callable[[PublishingStatus], str]; expected Callable[[object], ...]`` in the state-machine
    tests, because a tuple-unpacking target inside a comprehension does not reliably inherit the
    mapping's key type. Iterating the enum directly makes every step's type explicit.
    """
    terminal: set[PublishingStatus] = set()
    for status in PublishingStatus:
        if not ALLOWED_TRANSITIONS[status]:
            terminal.add(status)
    return frozenset(terminal)


TERMINAL_STATUSES: frozenset[PublishingStatus] = _derive_terminal_statuses()


class IllegalTransitionError(Exception):
    """Raised when a transition is attempted that the table does not permit.

    Deliberately not caught anywhere in the domain. A caller that catches this is either
    branching on a status it should have branched on earlier, or is about to write a status
    the spec forbids — both of which are bugs this exception exists to surface.
    """

    def __init__(self, current: PublishingStatus, target: PublishingStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Illegal publishing transition {current.value} -> {target.value}. "
            f"Permitted from {current.value}: "
            f"{sorted(s.value for s in ALLOWED_TRANSITIONS[current]) or ['none']}."
        )


def allowed_targets(current: PublishingStatus) -> frozenset[PublishingStatus]:
    """Every status reachable from ``current`` in a single legal transition."""
    return ALLOWED_TRANSITIONS[current]


def can_transition(current: PublishingStatus, target: PublishingStatus) -> bool:
    """Whether ``current -> target`` is legal. The query half of the table."""
    return target in ALLOWED_TRANSITIONS[current]


def transition(current: PublishingStatus, target: PublishingStatus) -> PublishingStatus:
    """Return ``target`` if ``current -> target`` is legal, else raise.

    Returning the target rather than mutating anything keeps this usable from both the API
    (immediate publish) and the worker (scheduled publish) without either having to adopt the
    other's persistence model — architecture.md §6's reason for keeping the domain framework-free.
    """
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
    return target


__all__ = [
    "ALLOWED_TRANSITIONS",
    "TERMINAL_STATUSES",
    "IllegalTransitionError",
    "allowed_targets",
    "can_transition",
    "transition",
]
