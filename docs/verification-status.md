# Verification status

What has been executed, what it proved, and what it did not.

`AGENTS.md` §9 makes this distinction the definition of done: a change is finished when something
ran that could have failed, not when it looks finished. This page exists so that the honest reading
of this repository is available without having to reconstruct it from docstrings, CI comments, and
commit history.

---

## The result below is stale

**Last full run: 2026-09-11.** Since that run, these files changed — to apply ADR 0001 and ADR 0002,
and to correct references that still described them as unapplied proposals:

- `packages/domain/src/asebe_domain/publishing/state_machine.py`
- `packages/domain/src/asebe_domain/publishing/status.py`
- `packages/domain/tests/publishing/test_state_machine.py`
- `packages/infrastructure/src/asebe_infrastructure/database/models/publishing.py`
- `README.md` (the "Allowed state transitions" block)
- `pyproject.toml`, `.github/workflows/ci.yml`, `packages/contracts/package.json`

**So the numbers below do not cover the current tree.** Re-running the three commands is what makes
this page true again. It is written this way rather than deferred because a status page that
quietly describes the wrong revision is worse than one that says so.

---

## What was run

| Command | Result |
|---|---|
| `ruff check .` | clean |
| `mypy --no-incremental` | clean — 17 source files, mypy 2.3.1 |
| `pytest packages/domain/tests -q` | 1481 passed |

Run against Python 3.12.3 in a throwaway venv at `/tmp/asebe`, because `uv` is not installed on this
machine. **`uv` is the toolchain `AGENTS.md` §4 fixes**, so this is evidence about the code and not
about the workspace definition — `uv sync` has never run, and there is no `uv.lock`.

---

## Rules

R1–R14 from `AGENTS.md` §3, with what each is actually backed by today.

| Rule | Subject | State |
|---|---|---|
| R1 | `PUBLISHED` must carry a `platform_post_id` | ✅ enforced by type, tested |
| R2 | Ambiguous outcome → `STATUS_UNKNOWN`, never `FAILED` | ✅ tested, including the asymmetry cases |
| R3 | `STATUS_UNKNOWN` is never automatically retried | ✅ tested |
| R4 | At most one automatic retry | ✅ tested |
| R5 | Auth / validation / permission never auto-retried | ✅ tested |
| R6 | Idempotency key before every attempt | ⚠️ generator written and tested; the transactional write is not |
| R7 | Every attempt and raw response persisted | ❌ model only — needs PostgreSQL |
| R8 | All transitions through one state machine | ✅ table + exhaustive 81-pair test. A DB check constraint was added alongside it, but has never been executed — no Postgres |
| R9 | State change and job enqueue commit together | ❌ not written |
| R10 | Content never silently altered | ❌ no validation package |
| R11 | `is_demo` cannot reach a real adapter | ⚠️ column and property exist; no adapter boundary to enforce at |
| R12 | Authorization enforced server-side | ❌ no routes beyond `/health` |
| R13 | No hardcoded visible strings | ❌ not enabled — no UI strings exist yet to hardcode |
| R14 | Tokens never reach browser, log, or error | ❌ no logging layer |

**Two rules are partially satisfied, and the "⚠️" is not a soft pass.** R6's generator is
deterministic and tested, but the key is not yet written in the same transaction as the
`PUBLISHING` status change — that ordering *is* R9, and R9 does not exist. R11's column exists on
the model, but the check belongs at the repository/adapter boundary, which has not been written;
until it is, nothing enforces R11 at all.

---

## Written but never executed

None of the following has ever run. Not "passes tests" — has never been imported by a live process.

| Path | What it is |
|---|---|
| `packages/infrastructure` | SQLAlchemy `Base` and the publishing models. No migrations, no repositories, no session management, no engine. |
| `apps/api` | FastAPI app exposing `/health` only. Never started. |
| `apps/worker` | Procrastinate entrypoint. Never run; no job has ever been enqueued or consumed. |
| `apps/web` | Next.js App Router shell. Never built or type-checked — `pnpm install` has not run. |
| `packages/contracts` | The generator exists; it has never been run. |

`packages/contracts/src/schema.d.ts` is **deliberately absent**. It is generated-but-committed
(`AGENTS.md` §6 rule 2), and hand-writing it would produce a hand-maintained artifact masquerading
as generated — undetectable by CI, which is the exact failure that package exists to prevent. It
appears the first time `pnpm contracts:generate` runs for real, alongside `src/index.ts`.

The contract gate in CI was strengthened so it can no longer pass vacuously while this file is
missing: `git diff --exit-code` does not report untracked files, so the original check would have
gone green on exactly the state described above.

---

## Not written

Per `AGENTS.md` §5, the domain is expected to contain `validation/`, `scheduling/`, `permissions/`,
`notifications/`, `audit/`, and `analytics/`. **None exist.** `publishing/` and `adapters/` do, and
`adapters/protocol.py` defines the `PlatformAdapter` protocol, but no platform is implemented — not
one of the eight.

---

## What blocks the rest

| Blocker | Effect |
|---|---|
| `uv` not installed | Workspace definition, lockfile, and `uv run` are all unavailable |
| Docker daemon unreachable (`student` not in the `docker` group) | No PostgreSQL, no MinIO |
| PostgreSQL absent | R7, R9, the repository layer, and every integration test |

Unblocking PostgreSQL is necessary but not sufficient for R7 and R9: `docker-compose.yml`, the
Alembic environment and migrations, and the repository implementations **all still have to be
written**. See the table in "Written but never executed" — `packages/infrastructure` is six files.

---

## How to reproduce

Once `uv` is installed:

```bash
uv sync --all-packages
uv run pytest packages/domain/tests -v
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Until `uv sync` has run and produced `uv.lock`, CI cannot execute: the `contract` and `web` jobs
invoke `pnpm install --frozen-lockfile`, which fails outright when no lockfile is committed. Neither
`uv.lock` nor `pnpm-lock.yaml` exists in this repository yet.
