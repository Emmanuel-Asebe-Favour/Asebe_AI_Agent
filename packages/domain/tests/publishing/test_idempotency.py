"""Tests for idempotency key generation — R6.

AGENTS.md R6: "Every publishing attempt carries an idempotency key, generated before the request."

**Scope of these tests.** They prove the *derivation* is correct and deterministic. They cannot
prove *when* the key is written — that is R9, the transactional boundary in architecture.md §4, and
it needs a database. Nothing here should be read as evidence that R9 holds.
"""

from __future__ import annotations

import uuid

import pytest
from asebe_domain.publishing.idempotency import generate


def test_same_inputs_produce_the_same_key() -> None:
    """Determinism is the point: recomputation after a crash must not invent a second key."""
    assert generate("post-1", 1) == generate("post-1", 1)


def test_key_is_a_valid_uuid() -> None:
    """The key travels to a platform in a header or body, so its format must be predictable."""
    key = generate("post-1", 1)
    assert uuid.UUID(key)
    assert key == str(uuid.UUID(key))


def test_different_posts_get_different_keys() -> None:
    """Two platforms publishing the same content must never share a key."""
    assert generate("post-1", 1) != generate("post-2", 1)


def test_different_attempts_get_different_keys() -> None:
    """A genuine retry after a confirmed failure presents a new key.

    Retrying an ambiguous result is forbidden by R3 and never reaches this function, so
    distinguishing attempts cannot enable the duplicate-post hazard.
    """
    assert generate("post-1", 1) != generate("post-1", 2)


@pytest.mark.parametrize("attempt_number", range(1, 50))
def test_every_attempt_number_yields_a_distinct_key(attempt_number: int) -> None:
    """Collisions across attempts would make the platform treat a retry as the original."""
    others = {generate("post-1", n) for n in range(1, 50)}
    assert len(others) == 49


def test_key_derivation_is_pinned_to_the_namespace_literal() -> None:
    """Recomputes the expected key from the namespace constant, independently of the module.

    This is the test that makes the namespace load-bearing. Changing ``_IDEMPOTENCY_NAMESPACE``
    changes every key the system has ever issued, which would let a retry present a key the
    platform has never seen and post the content twice. Pinning the derivation here means such a
    change cannot be made accidentally — it fails, loudly, in a test whose name says why.
    """
    namespace = uuid.UUID("6f1c4a2e-0d3b-4f7a-9c58-2b8e5d1a7f30")
    assert generate("post-1", 1) == str(uuid.uuid5(namespace, "post-1:1"))


def test_namespace_constant_has_not_changed() -> None:
    """The literal itself, asserted directly so the previous test cannot drift with it."""
    from asebe_domain.publishing import idempotency

    assert uuid.UUID(
        "6f1c4a2e-0d3b-4f7a-9c58-2b8e5d1a7f30"
    ) == idempotency._IDEMPOTENCY_NAMESPACE


def test_empty_post_key_is_rejected() -> None:
    """An empty identity would make every post collide onto the same key."""
    with pytest.raises(ValueError, match="platform_post_key must not be empty"):
        generate("", 1)


@pytest.mark.parametrize("attempt_number", (0, -1))
def test_non_positive_attempt_number_is_rejected(attempt_number: int) -> None:
    with pytest.raises(ValueError, match="attempt_number must be >= 1"):
        generate("post-1", attempt_number)


def test_generate_satisfies_the_protocol_shape() -> None:
    """``generate`` is usable wherever an ``IdempotencyKeyGenerator`` is expected (AGENTS.md §5)."""
    from asebe_domain.publishing.idempotency import IdempotencyKeyGenerator

    generator: IdempotencyKeyGenerator = generate
    assert generator("post-1", 1) == generate("post-1", 1)
