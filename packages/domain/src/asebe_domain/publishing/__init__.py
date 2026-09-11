"""The reliability kernel: state machine, retry policy, idempotency, error classification.

Everything in this subpackage is a pure function over values, with no I/O and no framework. That is
what makes AGENTS.md §3's rules testable exhaustively rather than aspirationally.

Reading order for someone new to the system:

1. ``results.py`` — the closed union. The prime invariant is enforced by the type system here, and
   everything else is plumbing around it.
2. ``status.py`` and ``state_machine.py`` — the lifecycle.
3. ``error_classifier.py`` — how an observed platform outcome becomes a member of the union.
4. ``retry_policy.py`` — what may happen next (R3/R4/R5).
5. ``idempotency.py`` — R6's key derivation.

Not implemented here, and deliberately so — orchestration (the code that would sequence these
steps against a database) belongs in ``packages/infrastructure`` and ``apps/worker``, because it
needs the transactional boundary described in architecture.md §4.
"""

from asebe_domain.publishing.error_classifier import (
    ParsedPlatformResponse,
    PlatformErrorBody,
    TransportOutcome,
    classify,
)
from asebe_domain.publishing.idempotency import IdempotencyKeyGenerator, generate
from asebe_domain.publishing.results import (
    ErrorClass,
    Failed,
    Published,
    PublishResult,
    RequiresAuthentication,
    Unknown,
)
from asebe_domain.publishing.retry_policy import MAX_ATTEMPTS, RetryDecision, decide
from asebe_domain.publishing.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    IllegalTransitionError,
    allowed_targets,
    can_transition,
    transition,
)
from asebe_domain.publishing.status import PublishingStatus

__all__ = [
    "ALLOWED_TRANSITIONS",
    "MAX_ATTEMPTS",
    "TERMINAL_STATUSES",
    "ErrorClass",
    "Failed",
    "IdempotencyKeyGenerator",
    "IllegalTransitionError",
    "ParsedPlatformResponse",
    "PlatformErrorBody",
    "PublishResult",
    "Published",
    "PublishingStatus",
    "RequiresAuthentication",
    "RetryDecision",
    "TransportOutcome",
    "Unknown",
    "allowed_targets",
    "can_transition",
    "classify",
    "decide",
    "generate",
    "transition",
]
