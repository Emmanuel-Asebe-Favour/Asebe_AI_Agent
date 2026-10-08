# ADR 0003 — Let a confirmed verification resolve `STATUS_UNKNOWN`

- **Status:** Accepted and applied, 2026-10-07 (maintainer decision).
- **Date:** 2026-10-07
- **Supersedes:** nothing
- **Affects:** README "Allowed state transitions", `packages/domain/publishing/state_machine.py`,
  `packages/infrastructure/publishing/verification.py`

## Context

Three parts of the spec describe verification, and they do not agree with the state machine.

README's flow for an uncertain publish:

```text
Publishing attempt
→ Receive response
→ Verify using platform ID or status endpoint
→ Mark Published, Failed, or Status Unknown
```

`docs/architecture.md` §5: when a platform supports lookup, verification will "confirm existence,
resolve `Unknown` to `Published` or `Failed`".

`VerificationResult.resolves_status` in the domain encodes exactly that: `CONFIRMED_PUBLISHED`
justifies `PUBLISHED`, `CONFIRMED_ABSENT` justifies `FAILED`.

But the transition table, transcribed from README, allows only one exit from `STATUS_UNKNOWN`:

```text
STATUS_UNKNOWN → REQUIRES_USER_REVIEW
```

So a platform can positively tell us "yes, it is live, here is the id" and the system has no legal
way to record it. The post can only go to review — and from review the only exits are a user retry
(`→ PUBLISHING`, which would duplicate a post that is already live) or `→ CANCELLED`. A post proven
to be published can never be shown as published. That is the same class of gap as ADR 0001 and
ADR 0002, and `AGENTS.md` §11 says it must be decided, not worked around.

## Decision

Add two transitions out of `STATUS_UNKNOWN`, each allowed only as the result of a verification:

```text
STATUS_UNKNOWN → PUBLISHED   when verify_post returns CONFIRMED_PUBLISHED, with a platform_post_id
STATUS_UNKNOWN → FAILED      when verify_post returns CONFIRMED_ABSENT
```

`INCONCLUSIVE` and `UNSUPPORTED` keep the existing route, `STATUS_UNKNOWN → REQUIRES_USER_REVIEW`.

Neither new transition is a retry. `FAILED` reached this way is a statement that the platform
confirmed the content is not there; getting from `FAILED` back to `PUBLISHING` stays the manual,
user-initiated step it already is, and R3 (no automatic retry of an unknown) is not weakened.

## Alternatives considered

**1. Leave it as it is.** Rejected: a confirmed-live post sits in review indefinitely and the only
"proceed" button available to the user (retry) would create a duplicate. The safe path becomes
the dangerous one.

**2. Add `REQUIRES_USER_REVIEW → PUBLISHED`, user-initiated.** Rejected as the *only* fix: it makes
a human re-confirm something the platform already proved. It could still be added alongside, for
the case where the user finds the post live and verification could not.

**3. Route `STATUS_UNKNOWN → FAILED` unconditionally.** Rejected, same reasoning as ADR 0002's
first alternative: `FAILED` means "the platform definitively rejected this", and we would be
claiming that without proof. The transitions above are allowed *only* with a confirming result.

**4. Apply without an ADR.** Forbidden by `AGENTS.md` §11.

## Consequences if accepted

- Two new rows in the transition table; README's spec block updated in the same commit.
- `STATUS_UNKNOWN` is no longer a single-exit status. The state machine cannot see the
  verification result, so "only with confirming evidence" is enforced by the caller —
  `PostVerifier.apply` — the same way ADR 0002 leaves "a human decided" to the API route.
- `PostVerifier.apply` switches from always choosing review to using `resolves_status`; the change
  is confined to that one method, and its tests flip from "waits in review" to the two new
  statuses.
- An audit-log entry is required on both transitions (actor: system, evidence: the verification
  outcome), since a post's status changing without a user present must be attributable.

## Applied

- `state_machine.py`: `STATUS_UNKNOWN` now has three exits; the spec block in README and the
  hand-copied spec in `test_state_machine.py` were changed in the same commit.
- `PostVerifier.apply` uses `VerificationResult.resolves_status` to choose the target; inconclusive
  and unsupported results still go to review. Its tests were flipped accordingly.

## Not yet done

The audit-log entry required above cannot be written yet because there is no `audit_logs` table.
Until it exists, a verification that resolves a post changes its status without leaving an
attributable record. Creating that table is the first step of the administration work, and the two
resolving transitions must write to it as soon as it does.
