# Architecture

Rationale for the structural decisions in this project. `AGENTS.md` states the rules; this document
explains why they are the rules. Read this before proposing a structural change.

## 1. The problem shape

This is not a CRUD app that happens to call social APIs. It is a **distributed system with an
unreliable remote party and no two-phase commit**. The platform may or may not have received a post,
and we cannot always find out. Every architectural decision below follows from that.

The specific hazard: a publish request is sent, the platform accepts it, and the response is lost —
timeout, dropped connection, 502 from an intermediary. The platform has the post. We do not know it
has the post. If we report failure and the user retries, the content is published twice. For a
creator, a duplicate post is a visible, embarrassing, unrecoverable error.

So the system's job is not "publish reliably" in the optimistic sense. It is **to never lie**. It is
acceptable to say "we don't know" and make the user check. It is not acceptable to say "failed" when
it might have succeeded, or "succeeded" without a platform post ID.

## 2. Why the type system carries the invariant

Rules that depend on developer discipline decay. Rules enforced by the compiler do not.

```python
# packages/domain/publishing/results.py

class Published(BaseModel):
    """A publish we can prove happened."""
    model_config = ConfigDict(frozen=True)
    platform_post_id: str          # <- required. no default. no Optional.
    published_at: datetime
    raw_response: dict[str, Any]

class Failed(BaseModel):
    """The platform definitively rejected this. It did not publish."""
    model_config = ConfigDict(frozen=True)
    error_class: ErrorClass
    message: str

class Unknown(BaseModel):
    """We do not know whether the platform published this."""
    model_config = ConfigDict(frozen=True)
    reason: str
    raw_response: dict[str, Any] | None

class RequiresAuthentication(BaseModel):
    model_config = ConfigDict(frozen=True)
    platform: str

PublishResult = Published | Failed | Unknown | RequiresAuthentication
```

`Published` cannot be constructed without a `platform_post_id`. There is no `success: bool`. An
adapter author who has not figured out how to obtain a post ID *cannot* claim success — the only
thing they can build is `Unknown`, which is the correct answer.

This is the whole design in one type. Everything else is plumbing.

## 3. Failure classification

The retry policy is a pure function over the classified error. It has no I/O, which makes it
exhaustively testable.

| Observed | Classified as | Retry? |
|---|---|---|
| HTTP 200, valid body, post ID present | `Published` | n/a |
| HTTP 200, body unparseable | `Unknown` | never |
| HTTP 200, body says error | `Failed(PERMANENT)` | never |
| Timeout / connection reset | `Unknown` | never |
| HTTP 429 | `Temporary` | once, after backoff |
| HTTP 5xx with explicit terminal body | `Temporary` | once |
| HTTP 401 / 403 | `RequiresAuthentication` | never |
| HTTP 400 / 422 (content invalid) | `Failed(PERMANENT)` | never |
| Response is a 200 but we crashed parsing it | `Unknown` | never |

The asymmetry is deliberate: **anything we did not fully understand is `Unknown`**, because
`Unknown` is safe and `Temporary` is not. A mistaken `Temporary` causes a duplicate post; a mistaken
`Unknown` causes a user to check their account.

```python
def decide(result: PublishResult, attempt_count: int) -> RetryDecision:
    match result:
        case Published() | RequiresAuthentication():
            return RetryDecision.NONE
        case Failed(error_class=ErrorClass.PERMANENT):
            return RetryDecision.NONE
        case Failed(error_class=ErrorClass.TEMPORARY) if attempt_count < 2:
            return RetryDecision.RETRY_ONCE
        case Unknown():
            return RetryDecision.REQUIRE_REVIEW      # R3 — unconditional
        case _:
            return RetryDecision.REQUIRE_REVIEW
```

No `default` arm that returns `RETRY_ONCE`. Ever.

## 4. The transactional boundary

State change and job creation must be atomic. This is why the queue is Postgres-backed.

```python
async with uow.begin() as tx:                    # one transaction
    post.status = PublishingStatus.PUBLISHING
    post.idempotency_key = idempotency_service.generate(post)   # R6
    attempt = publishing_attempts.start(post)                    # R7
    if post.scheduled_at:
        publish_task.configure(connection=tx.conn).defer(...)    # R9
    await repo.save(post, conn=tx.conn)
# commit — state and job become visible together, or neither does
```

If the process dies before commit, nothing happened. If it dies after commit, the job exists and
will run. There is no state in which a post claims to be scheduled with no job behind it.

This is the single strongest argument against Redis in this stack, and the reason `AGENTS.md` §4
forbids it.

## 5. Verification

`verify_post()` exists because a publish response is not always the final word — some platforms
accept asynchronously and report the outcome later, and some let you query by client reference.

Verification is best-effort by design:

- Platform supports lookup by post ID → confirm existence, resolve `Unknown` to `Published` or
  `Failed`.
- Platform supports lookup by idempotency/client reference → use it to answer "did my request land?"
- Platform supports neither → `VerificationResult.unsupported()`, and the post stays `Unknown` and
  goes to `REQUIRES_USER_REVIEW`.

An adapter must never fake verification by re-reading the original response. That converts a
genuine unknown into a false certainty, which is the one thing this system must not do.

## 6. Why domain logic is framework-free

`packages/domain` imports no FastAPI, no SQLAlchemy, no `httpx`. It defines protocols;
`packages/infrastructure` implements them.

Two reasons, both practical:

1. **The worker and the API run identical publishing logic.** A scheduled publish and an immediate
   publish must not diverge in their retry or verification behaviour. Shared code, not parallel
   implementations.
2. **The reliability rules are testable without infrastructure.** The state machine, retry policy,
   and idempotency behaviour are pure functions over values. They get exhaustive unit tests that run
   in milliseconds, covering every (status, event) pair. That is only possible if the logic does not
   know what a database is.

## 7. The contract boundary

The frontend is TypeScript, the backend is Python. Nothing structural prevents them from drifting —
so the OpenAPI schema is made load-bearing:

```text
Pydantic models  →  FastAPI OpenAPI  →  generated schema.d.ts  →  frontend
```

The generated client is committed, CI fails if it is stale, and hand-written response types are
forbidden. This is a deliberate replacement for what a single-language stack would have given for
free, and it is the highest-risk boundary in the codebase. Treat it accordingly.

## 8. Consequence: the README is now partly stale

The original README assumed a TypeScript monorepo. Choosing a Python backend invalidates parts of
it. These sections need updating:

| README section | Status |
|---|---|
| `Project Structure` | **Wrong.** Lists `packages/publishing`, `packages/platform-adapters`, etc. as TS. Now Python under `packages/domain/`, split api/worker. |
| `Architecture → Platform adapter interface` | **Wrong.** The `interface PlatformAdapter` TS block must become a Python `Protocol` plus the closed `PublishResult` union in §2. |
| `Architecture → Shared services` | Names remain valid as concepts; they become modules under `packages/domain/`. |
| `Data Model` | Still valid as a logical model; field naming now follows Python conventions. |
| Everything else | Still authoritative — it is the product spec. |

The product requirements in the README are **not** superseded. Only the structural sections are.

## 9. Open decisions

- Object storage: MinIO locally, but production target (S3 vs R2) is undecided.
- Email provider for production (Resend assumed).
- Deployment target — affects whether the worker runs as a separate service or a process.
- Whether the reconciler sweep for posts stuck in `PUBLISHING` is a Procrastinate periodic task or a
  cron-driven job. It is required either way; a worker dying mid-publish must not strand a post.
