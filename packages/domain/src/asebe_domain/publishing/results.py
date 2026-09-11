"""The closed publish-result union — where the prime invariant is enforced by the type system.

AGENTS.md §2 states the invariant this module exists to make unfakeable:

    Never report a publish as successful unless it is proven.
    Never retry an ambiguous result.

architecture.md §2 puts it precisely: "Rules that depend on developer discipline decay. Rules
enforced by the compiler do not."

Mechanically:

* ``Published`` is a frozen model with a **required** ``platform_post_id``. There is no default,
  there is no ``Optional``, and there is no ``success: bool`` anywhere in this file. An adapter
  author who has not figured out how to obtain a post ID *cannot* claim success — the only value
  they can construct is ``Unknown``, which is the correct answer (R1).
* The union is closed. ``PublishResult`` has exactly four members, so every consumer that matches
  on it must handle all four or fail the exhaustiveness check. ``Unknown`` is a first-class
  outcome, not an error case bolted onto a boolean (R2).

Nothing in this module performs I/O, and nothing here may be imported by the infrastructure layer's
dependencies. See packages/domain/pyproject.toml for why that is enforced rather than requested.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------------------
# The raw response payload
# --------------------------------------------------------------------------------------
# AGENTS.md §6 forbids typing a *platform response* as `dict` or `Any` at a trust boundary.
# The reconciliation, made explicit so it is not mistaken for a violation:
#
#   The trust boundary is the adapter edge, which strictly parses the platform's wire format
#   into `ParsedPlatformResponse` (see error_classifier.py). `RawPlatformResponse` is what
#   remains *after* that parse — an audit blob retained because R7 requires the raw response
#   be persisted.
#
# It is typed `Mapping[str, object]` rather than `dict[str, Any]` so that no caller can index
# into it and casually assume a shape. It is NEVER consulted for control flow: the decision of
# what a response means is made by error_classifier.py from parsed fields only. A test asserts
# the classifier never reads this value.
type RawPlatformResponse = Mapping[str, object]


class ErrorClass(StrEnum):
    """Why a publish definitively failed.

    Exhaustive by construction. ``retry_policy.decide`` matches on this enum with no ``default``
    arm, so adding a member forces a decision about its retry behaviour (R5).

    The split that matters: only ``TEMPORARY`` may ever be retried, and then at most once (R4).
    ``VALIDATION`` and ``PERMISSION`` are separated from ``PERMANENT`` not because their retry
    behaviour differs — it does not — but because the user-facing explanation differs, and
    README's "Error messages" section requires explaining *what the user should do next*.
    """

    TEMPORARY = "TEMPORARY"
    PERMANENT = "PERMANENT"
    VALIDATION = "VALIDATION"
    PERMISSION = "PERMISSION"


# --------------------------------------------------------------------------------------
# The four members of the closed union
# --------------------------------------------------------------------------------------


class Published(BaseModel):
    """A publish we can prove happened.

    R1: ``platform_post_id`` is required, with no default and no ``Optional``. This is the whole
    design in one field — a caller holding a ``Published`` has, by construction, the platform's
    own identifier for the post. ``Field(min_length=1)`` closes the gap left by a caller passing
    an empty string to satisfy the type checker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_post_id: str = Field(min_length=1)
    published_at: datetime
    raw_response: RawPlatformResponse


class Failed(BaseModel):
    """The platform definitively rejected this. It did not publish.

    "Definitively" is load-bearing. A timeout is not a ``Failed``; neither is an unparseable
    body. Those are ``Unknown``. Reaching this class means we understood the platform's rejection
    well enough to be certain the content is not on the destination account.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_class: ErrorClass
    message: str = Field(min_length=1)


class Unknown(BaseModel):
    """We do not know whether the platform published this.

    This is a correct answer, not a failure to produce one. AGENTS.md §2's target bug is a
    creator whose post published, whose response was lost, and who then retried and posted twice —
    ``Unknown`` is the state that prevents the double post.

    ``raw_response`` is ``None`` where there was no response at all (timeout, connection reset).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1)
    raw_response: RawPlatformResponse | None = None


class RequiresAuthentication(BaseModel):
    """The platform rejected our credentials. It did not publish.

    Distinct from ``Failed`` because the remedy is different: the user must reconnect the account
    before anything else can happen (R5 — never automatically retried).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: str = Field(min_length=1)


type PublishResult = Published | Failed | Unknown | RequiresAuthentication
"""The closed union. Exactly four members — nothing more may be added without an ADR.

Type-checking note: ``assert_never`` in retry_policy.decide turns "someone added a fifth member
and forgot to decide its retry behaviour" into a static error rather than a silent default.
"""

__all__ = [
    "ErrorClass",
    "Failed",
    "PublishResult",
    "Published",
    "RawPlatformResponse",
    "RequiresAuthentication",
    "Unknown",
]
