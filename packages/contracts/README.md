# `@asebe/contracts`

The generated TypeScript types for the API wire format, and the only bridge between the Python
backend and the TypeScript frontend.

## Why this package exists

AGENTS.md §6 is blunt about it:

> The frontend and backend are different languages. The **only** thing holding them together is the
> OpenAPI schema, and a drifted contract is the most likely way this project breaks.

A single-language stack gets this consistency for free. A Python/TypeScript split does not, so the
schema is made load-bearing instead of documentary:

```text
Pydantic models  →  FastAPI OpenAPI  →  generated schema.d.ts  →  frontend
```

## The rules

1. Pydantic models in `apps/api` are the single source of truth for the wire format.
2. `pnpm contracts:generate` writes `src/schema.d.ts`. **The generated file is committed.**
3. The frontend imports types **only** from `@asebe/contracts`. A hand-written `interface Post`
   in `apps/web` is forbidden — it will drift and nothing will catch it.
4. CI regenerates and fails if the committed output differs.
5. **Any change to a Pydantic response model is a breaking frontend change.** Make it in the same
   commit as the frontend update, or do not make it.

## Status: `src/schema.d.ts` has not been generated yet

The generator is written and the pipeline is wired, but the file has deliberately **not** been
committed yet, because generating it requires running the toolchain — which has not been possible
in this environment (no `uv` installed yet, and no package installation performed).

Hand-writing the file to make the package look complete would be precisely the failure this
package exists to prevent: a hand-maintained artifact masquerading as generated, with CI unable to
tell the difference. So it is absent, and `src/index.ts` does not yet exist.

The first successful run of:

```bash
pnpm install
pnpm contracts:generate
```

creates it. At that point add:

```ts
// src/index.ts
export type { components, paths, operations } from "./schema";
```

and commit both `schema.d.ts` and `index.ts` together.

## Commands

| Command | Purpose |
|---|---|
| `pnpm contracts:generate` | Regenerate `src/schema.d.ts` from the live API schema |
| `pnpm contracts:check` | Regenerate, then `git diff --exit-code` — the CI staleness gate |

`generate` imports the FastAPI app and calls `.openapi()`. It starts no server and touches no
database, so it works before the persistence layer exists.
