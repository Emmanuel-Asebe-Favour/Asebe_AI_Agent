"""Publishing status values.

The nine statuses are transcribed verbatim from README's "Publishing statuses" block, which
AGENTS.md §7 designates as the spec. This module holds the *values* only; the rules governing
movement between them live exclusively in state_machine.py (R8).
"""

from __future__ import annotations

from enum import StrEnum


class PublishingStatus(StrEnum):
    """The lifecycle of a single platform post.

    ``STATUS_UNKNOWN`` is deliberately named with the prefix rather than ``UNKNOWN``: it is the
    persisted status of a post whose publish outcome we could not determine, and the prefix keeps
    it visibly distinct from the ``Unknown`` *result* in results.py at every call site.

    ``REQUIRES_AUTHENTICATION`` and ``REQUIRES_USER_REVIEW`` began as spec gaps — no inbound and no
    outbound transition respectively. ADRs 0001 and 0002 resolved both and have since been applied,
    so each now has exactly the transitions its ADR added, asserted in
    tests/publishing/test_state_machine.py.
    """

    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    STATUS_UNKNOWN = "STATUS_UNKNOWN"
    CANCELLED = "CANCELLED"
    REQUIRES_AUTHENTICATION = "REQUIRES_AUTHENTICATION"
    REQUIRES_USER_REVIEW = "REQUIRES_USER_REVIEW"


__all__ = ["PublishingStatus"]
