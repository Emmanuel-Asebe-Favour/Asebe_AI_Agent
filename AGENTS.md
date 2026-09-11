# AGENTS.md

Operating instructions for any AI agent or human contributor working in this repository.

This file is **normative**. Where it conflicts with your instincts, your training priors, or a
pattern you have seen in another project, this file wins. If you believe a rule here is wrong,
do not silently deviate — propose an ADR (see §11) and get it accepted first.

---

## 1. What this is

A creator-publishing platform. Users upload image/video content, write captions, and publish or
schedule that content to multiple social-media platforms through pluggable adapters. Users and
administrators share **one** dashboard — there is no separate admin application.

The workflow the whole system exists to serve:

```text
Connect → Create → Validate → Preview → Schedule/Publish → Verify → Notify → Review
```

Full product requirements live in [`README.md`](./README.md). Architecture rationale lives in
[`docs/architecture.md`](./docs/architecture.md).

---

## 2. The prime invariant

> **Never report a publish as successful unless it is proven. Never retry an ambiguous result.**

Everything below is downstream of this. Most bugs that matter in this codebase are violations of
this invariant, not crashes. When you are unsure how to implement something, ask:
*"does this make it possible to claim success we cannot prove?"* If yes, you are on the wrong path.

The failure this system is designed to prevent: a creator's post is published, the platform's
response is lost to a timeout, the system says "failed", the creator retries, and the content is
posted twice.

---

## 3. Non-negotiable rules

Each rule names what enforces it. A rule with no enforcement mechanism is a bug in this file.

| # | Rule | Enforced by |
|---|---|---|
| R1 | A `PUBLISHED` result **must** carry a `platform_post_id`. It is impossible to construct one without it. | Type system — `Published` is a frozen model with a required field |
| R2 | A timeout, connection error, or unparseable response yields `STATUS_UNKNOWN`. Never `FAILED`. | `PublishResult` is a closed union; the HTTP layer maps every non-2xx/exception to `Unknown` unless a response body was successfully parsed |
| R3 | `STATUS_UNKNOWN` is **never** automatically retried. Ever. | `retry_policy.decide()` returns `RetryDecision.REQUIRE_REVIEW` for it; unit-tested |
| R4 | At most **one** automatic retry, and only for a confirmed temporary technical failure. | `attempt_count` checked in `retry_policy`; unit-tested |
| R5 | Auth failures, validation failures, and permission failures are **never** automatically retried. | Same policy function, exhaustive over `ErrorClass` |
| R6 | Every publishing attempt carries an idempotency key, generated before the request. | `idempotency_service`; the key is written in the same transaction that sets `PUBLISHING` |
| R7 | Every attempt and its raw response is persisted. | `publishing_attempts` table; no publish path bypasses it |
| R8 | State transitions go through the central state machine. Illegal transitions raise. | `publishing/state_machine.py` — the only place transition rules exist |
| R9 | The state change to `PUBLISHING` and the enqueue of any follow-up job commit in **one** transaction. | Repository accepts an existing connection; jobs are deferred on that connection |
| R10 | User content is never silently truncated, translated, or altered. | Validation reports; it never rewrites. Any adaptation requires explicit user approval |
| R11 | `is_demo = true` content cannot reach a real platform adapter. | Checked at the repository/adapter boundary, not in the UI |
| R12 | Authorization is enforced server-side. Hiding a nav link is not authorization. | Permission dependency on every protected route |
| R13 | No visible string is hardcoded. | Lint rule + `packages/contracts` message keys |
| R14 | Access or refresh tokens never reach the browser, a log line, or an error message. | pino/structlog redaction filters; tokens are encrypted at rest |

---

## 4. Stack — fixed

Do not substitute a component in this table without an accepted ADR. "I prefer X" is not a reason.

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), React, TypeScript `strict`, Tailwind CSS, shadcn/ui (Radix) |
| Frontend i18n | next-intl (ICU messages) |
| Frontend data | Generated API client + TanStack Query |
| Backend | FastAPI, Python 3.12, Pydantic v2 |
| Domain logic | Pure Python in `packages/domain` — no framework imports |
| Database | PostgreSQL 16 |
| ORM / migrations | SQLAlchemy 2.0 (async) + Alembic |
| Job queue | Procrastinate (Postgres-backed, transactional deferral) |
| Auth | Server-side sessions in Postgres; opaque session ID in an HttpOnly cookie |
| Storage | S3-compatible (MinIO locally); presigned direct upload |
| Email | Resend in production, Mailpit locally |
| Package mgmt | `uv` (Python), `pnpm` (TypeScript) |

**Why Postgres-backed queueing:** scheduled publishing and the `PUBLISHING` state change must commit
together. With Redis in between, a crash can leave a post marked `SCHEDULED` with no job, or a job
with no post. With transactional deferral that window does not exist. Do not introduce Redis.

---

## 5. Where code goes

This is the boundary set. Deciding "where does this file live" is a design decision, not a
convenience one.

```text
apps/web/                  Next.js. Routing, layout, rendering, forms. No business logic.
apps/api/                  FastAPI. HTTP concerns only: parse, authorize, delegate, serialize.
apps/worker/               Procrastinate consumer entrypoint. Thin — registers tasks, calls domain.

packages/domain/           THE business logic. Framework-free, importable, unit-testable.
  publishing/              state machine, retry policy, idempotency, verification, orchestration
  adapters/                PlatformAdapter protocol + platform_1 … platform_8
  validation/              media + caption + capability validation
  scheduling/              timezone resolution, UTC normalization, DST handling
  permissions/             permission model and checks
  notifications/           notification rules
  audit/                   audit log writes
  analytics/               metric normalization
packages/infrastructure/   SQLAlchemy models, repositories, S3, email, HTTP clients
packages/contracts/        OpenAPI output + generated TypeScript client (committed)
```

**Hard boundaries:**

- `apps/web` must never contain a business rule. If you are writing an `if` about publishing
  status, retry eligibility, or platform capability in a React component, it belongs in the API or
  the response shape.
- `packages/domain` must never import FastAPI, SQLAlchemy, or `httpx` directly. It defines
  protocols; `packages/infrastructure` implements them. This is what lets the domain be tested
  without a database and lets the worker and API run identical logic.
- `apps/api` route handlers must never talk to the database directly. Route → domain service →
  repository.
- No generic `utils/` or `helpers/` module. Name the responsibility (`timezone_resolution.py`,
  `caption_length.py`). If you cannot name it, you have not identified the responsibility yet.

---

## 6. The contract rule

The frontend and backend are different languages. The **only** thing holding them together is the
OpenAPI schema, and a drifted contract is the most likely way this project breaks.

1. Pydantic models in `apps/api` are the single source of truth for the wire format.
2. `pnpm contracts:generate` writes `packages/contracts/src/schema.d.ts` from the live OpenAPI spec.
   **The generated file is committed.**
3. The frontend imports types **only** from `@asebe/contracts`. Hand-written `interface Post { … }`
   in `apps/web` is forbidden — it will drift and nothing will catch it.
4. CI regenerates and fails if the committed output differs.
5. **Any change to a Pydantic response model is a breaking frontend change.** Make it in the same
   commit as the frontend update, or do not make it.

The same discipline applies in reverse for platform APIs: responses from a platform are parsed
strictly into a discriminated union. An unparseable response is `Unknown`, not `Success` — this is
R2 in mechanical form. Never type a platform response as `dict` or `Any`.

---

## 7. Recipes

### Adding a platform adapter

Never modify core publishing code to add a platform. If you find yourself editing
`packages/domain/publishing/`, stop — the adapter interface is wrong and that is a separate ADR.

1. Create `packages/domain/adapters/platform_N/`.
2. Implement the `PlatformAdapter` protocol exactly. Do not widen it — adding a method to the
   protocol is a change to all eight adapters.
3. Declare `get_capabilities()` honestly. **Overstating a capability is a defect**, because the UI
   uses it to decide what to hide, block, and warn about.
4. Map every platform error into the closed `ErrorClass` union. An unmapped error must land in
   `Unknown`, never `Temporary`.
5. Implement `verify_post()`. If the platform offers no way to verify, return
   `VerificationResult.unsupported()` — do not fake a verification.
6. Add the adapter to the registry and to the capability matrix test.
7. Tests: a success path, a timeout, an ambiguous response, an expired token, and an unsupported
   media type.

### Changing the state machine

`publishing/state_machine.py` is the only place transition rules exist. To add a state or
transition:

1. Add it to the transition table.
2. Add the transition to the README's "Allowed state transitions" block — the README is the spec.
3. Prove no illegal transition became legal: the exhaustive test iterates all
   (from, to) pairs and asserts against the table.
4. Update any UI that renders status. The status enum is generated into the contract, so
   TypeScript will fail to compile on an unhandled case — that is intentional and you should
   exhaustively handle it rather than adding a default case.

### Adding an API endpoint

1. Pydantic request/response models first.
2. Domain service function second — testable without HTTP.
3. Route handler third: authorize, delegate, return. No logic.
4. Regenerate the contract. Update the frontend in the same commit.

---

## 8. Forbidden

These are the defaults you will be tempted by. Each one has caused the class of bug this project
exists to prevent.

- **Never** write `status = "PUBLISHED"` outside the state machine.
- **Never** catch an exception from `publish_post()` and convert it to `FAILED`. Route it through
  the error classifier. Most surprises are `Unknown`.
- **Never** retry by calling the adapter again. Retries go through the retry policy and create a
  new attempt row.
- **Never** add a `default:` branch to an exhaustive match over a status or error type. The
  compiler is telling you that you have not handled a case.
- **Never** put `is_demo` filtering in the UI. Demo isolation is a server-side guarantee.
- **Never** `try/except` around a platform call and swallow the error.
- **Never** hand-write a frontend type that mirrors an API response.
- **Never** add a dependency for something the standard library or an existing dependency does.
  Every dependency in the publish path is a reliability liability.
- **Never** mark a task complete because the happy path works. See §9.

---

## 9. Definition of done

A change is done when **all** of the following hold. Partial completion must be reported as
partial — do not describe unfinished work as finished.

- [ ] Happy path implemented.
- [ ] **Failure paths implemented**: timeout, ambiguous response, expired token, unsupported media,
      rate limit.
- [ ] Unit tests cover the failure paths, not just the happy path. For anything touching publishing
      status, retry, or idempotency, failure tests are mandatory.
- [ ] No new `Any`/`dict` at a trust boundary (platform response, request body).
- [ ] Contract regenerated if any Pydantic model changed.
- [ ] No hardcoded user-visible strings.
- [ ] Logs contain no tokens, no PII, no raw platform payloads with credentials.
- [ ] `pnpm check` and `uv run pytest` both pass.
- [ ] You have read your own diff and can explain every line.

---

## 10. Self-check before you finish

Run this against your own change. Report the answers honestly, including failures.

1. Can this code path report success without proof? How do you know?
2. What happens if the platform times out *after* accepting the post? Trace it.
3. Is there any path where an ambiguous result gets retried automatically?
4. Where does the idempotency key get created relative to the `PUBLISHING` write — same transaction?
5. Did I change a Pydantic model without regenerating the contract?
6. Did I hardcode a string a user will see?
7. Would this still be correct if the platform returned a 200 with an error body?
8. If I deleted every test I wrote, what would silently break?

If you cannot answer #1 and #3 with certainty, the change is not ready.

---

## 11. Changing the rules

Architecture decisions that contradict this file require an ADR in `docs/adr/`, numbered
sequentially, with: context, the decision, alternatives considered, and the consequence you accept.
Accepted ADRs supersede this file; update the relevant section here in the same commit.

Do not edit this file to make a failing approach appear compliant.
