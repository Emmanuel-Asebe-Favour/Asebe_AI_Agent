# ADR 0002 — Allow `REQUIRES_USER_REVIEW` to leave review

- **Status:** Proposed — not accepted. No code depends on this yet.
- **Date:** 2026-09-10
- **Supersedes:** nothing
- **Affects:** README "Allowed state transitions", `packages/domain/publishing/state_machine.py`

## Context

README's flow for an uncertain publish is:

```text
Publishing attempt
→ Receive response
→ Verify using platform ID or status endpoint
→ Mark Published, Failed, or Status Unknown
→ Notify user
→ Retry only when safe
```

and its state machine sends an uncertain post to human review:

```text
STATUS_UNKNOWN → REQUIRES_USER_REVIEW
```

`REQUIRES_USER_REVIEW` is then a **dead end**. No transition leaves it, so a post that reaches
review can never proceed, regardless of what the user decides.

The status is reachable and terminal, which makes the documented workflow unsatisfiable: step five
of the flow above — "Retry only when safe" — cannot be expressed as a transition. The only statuses
from which `PUBLISHING` is reachable are `DRAFT` and `FAILED`. So a user who checks their
destination account, finds the post absent, and decides to retry has no legal move: the post is
stuck in `REQUIRES_USER_REVIEW` forever.

README's own rule 10 makes the user's decision the deciding factor — "Require user review for
further retries" — and the transition table gives that decision nowhere to land.

The gap is currently pinned by a test rather than fixed, per §11 of `AGENTS.md`:

```
tests/publishing/test_state_machine.py::test_known_gap_requires_user_review_is_a_dead_end
```

## Decision

Allow two transitions out of review, both user-initiated:

```text
REQUIRES_USER_REVIEW → PUBLISHING
REQUIRES_USER_REVIEW → CANCELLED
```

- `→ PUBLISHING` is the user having checked the destination account, confirmed the content is not
  there, and chosen to publish. This is the manual retry README's flow describes.
- `→ CANCELLED` is the user abandoning the post — which must be possible, or a post the user no
  longer wants accumulates in review indefinitely and gives "Cancel scheduled posts" no meaning
  for this state.

## Alternatives considered

**1. `REQUIRES_USER_REVIEW → FAILED → PUBLISHING`.** Rejected: it routes through a status whose
meaning is "the platform definitively rejected this". The platform did nothing of the kind — it may
still hold the post. Writing `FAILED` to reach the retry path would record a false claim in the
audit log, which is the class of lie this system exists to prevent.

**2. Leave it a dead end and require the user to duplicate the content.** Rejected: it makes the
system's safe path the most laborious one, which is a strong incentive for users to avoid it. The
cautious behaviour must be usable or it will be worked around.

**3. Automate the retry after review.** Rejected, and worth stating explicitly: any automatic
retry from this state reintroduces the duplicate-post hazard R3 forbids. Both proposed transitions
are user-initiated and must stay that way. The state machine cannot enforce "a human decided this"
— that is the caller's obligation, discharged by the permission check and audit write on the API
route, and it is the reason these two transitions should not be reachable from any background job.

**4. Apply the change without an ADR.** Forbidden by `AGENTS.md` §11.

## Consequence accepted

- Two new rows in the transition table; README's spec block updated in the same commit (§7).
- `REQUIRES_USER_REVIEW` stops being terminal. `TERMINAL_STATUSES` shrinks to three:
  `PUBLISHED`, `CANCELLED`, `REQUIRES_AUTHENTICATION`.
- `test_known_gap_requires_user_review_is_a_dead_end` must be inverted to assert the two permitted
  targets and no others.
- The retry from review must carry a **new** idempotency key attempt number
  (`idempotency.generate(key, attempt_number + 1)`), because a new attempt is being made. Reusing
  the original key would make the platform treat it as the same request it may have already
  accepted — silently defeating the retry.
- An audit-log entry is required on both transitions (README "Audit logs": record actor, action,
  previous state, new state). A user-initiated retry after an ambiguous result is exactly the kind
  of action that must be attributable.

## Not decided here

Whether the review queue surfaces the verification attempts already made, so the user can judge
without leaving the dashboard. That is a UI concern for the notifications/review surface, not a
state-machine one.
