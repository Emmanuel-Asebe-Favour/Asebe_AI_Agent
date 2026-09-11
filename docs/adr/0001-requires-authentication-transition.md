# ADR 0001 — Add `PUBLISHING → REQUIRES_AUTHENTICATION`

- **Status:** Accepted — applied 2026-09-11.
- **Date:** 2026-09-10
- **Supersedes:** nothing
- **Affects:** README "Allowed state transitions", `packages/domain/publishing/state_machine.py`

## Context

README declares `REQUIRES_AUTHENTICATION` as one of the nine publishing statuses:

```text
DRAFT
SCHEDULED
PUBLISHING
PUBLISHED
FAILED
STATUS_UNKNOWN
CANCELLED
REQUIRES_AUTHENTICATION
REQUIRES_USER_REVIEW
```

but its "Allowed state transitions" block contains no transition into it:

```text
DRAFT → SCHEDULED
DRAFT → PUBLISHING
SCHEDULED → PUBLISHING
SCHEDULED → CANCELLED
PUBLISHING → PUBLISHED
PUBLISHING → FAILED
PUBLISHING → STATUS_UNKNOWN
FAILED → PUBLISHING
STATUS_UNKNOWN → REQUIRES_USER_REVIEW
```

So the status is **unreachable**. No sequence of legal transitions can produce a post in
`REQUIRES_AUTHENTICATION`.

This is not merely untidy, because the rest of the design does produce that outcome.
`docs/architecture.md` §2 defines a `RequiresAuthentication` member of the `PublishResult` union,
and §3's classification table maps HTTP 401 and 403 onto it:

| Observed | Classified as | Retry? |
|---|---|---|
| HTTP 401 / 403 | `RequiresAuthentication` | never |

`packages/domain/publishing/error_classifier.py` implements that mapping. The consequence is a
contradiction inside the system: the classifier can determine that a publish failed for
authentication reasons, but the state machine has no way to record that determination. A caller
holding a `RequiresAuthentication` result must either leave the post in `PUBLISHING` forever —
violating README's requirement that publishing status be displayed clearly to the user — or write a
status the transition table forbids, violating R8.

The gap is currently pinned by a test rather than fixed, per §11 of `AGENTS.md`:

```
tests/publishing/test_state_machine.py::test_known_gap_requires_authentication_is_unreachable
```

## Decision

Add a single transition to the README's allowed-transitions block and to the state machine table:

```text
PUBLISHING → REQUIRES_AUTHENTICATION
```

`REQUIRES_AUTHENTICATION` remains terminal, as it is today. Recovering from it is the *connector*
flow — the user reconnects the account — and that is a separate post, not a transition of this one.

## Alternatives considered

**1. Remove `REQUIRES_AUTHENTICATION` from the status list.** Then README's "Failure workflow" and
"Authentication failures require reconnection" (completion criterion 16) have no corresponding
state, and the classifier's `RequiresAuthentication` member would have no persisted representation
at all. Rejected: it deletes a required product behaviour to resolve a bookkeeping inconsistency.

**2. Map 401/403 onto `FAILED` instead.** Rejected. `Failed` carries the claim "the platform
definitively did not publish, and retrying the same content would be appropriate". An expired token
says nothing about the content; conflating the two misdirects the user toward a content fix, which
is precisely what README's error guidance exists to prevent. R5 already distinguishes them in the
retry policy, and the persisted status should agree with the policy.

**3. Leave the status unreachable and let the API layer expose it without persistence.** Rejected:
README requires the final status be displayed to the user, and a status that exists only in a
response body and never in the database cannot survive a page reload.

**4. Apply the change without an ADR.** Forbidden by `AGENTS.md` §11.

## Consequence accepted

- One new row in the transition table, and one line added to the README spec block in the same
  commit (§7 requires the README be updated when the table changes).
- The exhaustive test in `test_state_machine.py` grew to assert the new pair legal, and
  `test_known_gap_requires_authentication_is_unreachable` was **inverted** into
  `test_requires_authentication_is_reachable_from_publishing_only`, which asserts exactly one
  inbound transition and that it comes from `PUBLISHING`. A companion test,
  `test_requires_authentication_stays_terminal`, pins the no-exit decision below.
- Any UI rendering status must handle the case. Because the status enum is generated into the
  contract, TypeScript will fail to compile on an unhandled case, which is the intended behaviour
  (`AGENTS.md` §7).
- The reconciler for posts stuck in `PUBLISHING` (`docs/architecture.md` §9) now has a defined
  destination for posts whose connection expired mid-publish.

## Not decided here

Whether an expired connection should be detected *before* a publish attempt rather than as a result
of one. That is a capability of the connection-health check in README's "Platform connection
monitoring", and it is orthogonal — a token can expire in the seconds between the health check and
the publish request.
