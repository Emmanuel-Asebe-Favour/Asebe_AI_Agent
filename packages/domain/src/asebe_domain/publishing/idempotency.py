"""Idempotency key generation — R6.

AGENTS.md R6: "Every publishing attempt carries an idempotency key, generated before the request."
architecture.md §4 places generation inside the transaction that sets ``PUBLISHING``:

    post.status = PublishingStatus.PUBLISHING
    post.idempotency_key = idempotency_service.generate(post)   # R6

**What this module does and does not enforce.** It generates keys. It cannot enforce *when* the key
is written — that ordering is R9, and it belongs to the transactional boundary in
``packages/infrastructure``, which does not exist yet. Do not read this module as satisfying R9.

The derivation is deterministic — a UUIDv5 over a fixed namespace — rather than random, for two
reasons:

1. Determinism makes the function testable. A random key can only be asserted to have a shape.
2. If a crash occurs between generating the key and committing it, recomputing from the same inputs
   yields the same key rather than a second, conflicting one. A random key would leave the platform
   holding a value we no longer know.

Determinism also means the key is *derived from* the post's identity, so the same logical publish
attempt always presents the same key to the platform — which is what lets a platform deduplicate a
request whose response we lost.
"""

from __future__ import annotations

import uuid
from typing import Protocol

# A fixed, versioned namespace. Changing this value changes every key the system has ever issued,
# which would let a retry present a key the platform has not seen and post content twice. It is a
# constant for that reason, not a configuration value — do not make it configurable.
_IDEMPOTENCY_NAMESPACE = uuid.UUID("6f1c4a2e-0d3b-4f7a-9c58-2b8e5d1a7f30")


class IdempotencyKeyGenerator(Protocol):
    """The domain's requirement, in protocol form.

    ``packages/infrastructure`` may substitute a persisted or database-sequenced implementation.
    The domain states what it needs and does not know how it is provided — AGENTS.md §5.
    """

    def __call__(self, platform_post_key: str, attempt_number: int) -> str: ...


def generate(platform_post_key: str, attempt_number: int) -> str:
    """Derive the idempotency key for one publishing attempt.

    ``platform_post_key`` is the stable identity of the *post on a platform* — not the content item
    and not the user — so that two platforms publishing the same content never share a key, while
    two attempts at the same platform post always do.

    ``attempt_number`` is included so that a genuine retry after a *confirmed* failure presents a
    distinct key. Retrying an *ambiguous* result is forbidden (R3) and never reaches this function,
    so the key can safely distinguish attempts without enabling the double-post hazard.
    """
    if not platform_post_key:
        raise ValueError("platform_post_key must not be empty")
    if attempt_number < 1:
        raise ValueError(f"attempt_number must be >= 1, got {attempt_number}")

    return str(uuid.uuid5(_IDEMPOTENCY_NAMESPACE, f"{platform_post_key}:{attempt_number}"))


__all__ = ["IdempotencyKeyGenerator", "generate"]
