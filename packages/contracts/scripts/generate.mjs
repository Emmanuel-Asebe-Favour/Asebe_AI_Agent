/**
 * Regenerate src/schema.d.ts from the API's live OpenAPI schema.
 *
 * This is stage three of the pipeline AGENTS.md §6 defines:
 *
 *   Pydantic models  →  FastAPI OpenAPI  →  generated schema.d.ts  →  frontend
 *
 * Two properties make the pipeline load-bearing rather than decorative:
 *
 *  1. The generated file is COMMITTED. Consumers get types without running Python.
 *  2. `pnpm contracts:check` regenerates and then `git diff --exit-code`s. If a Pydantic model
 *     changed without the contract being regenerated, CI fails. Drift is therefore impossible to
 *     merge, not merely discouraged — which matters because §6 calls this "the highest-risk
 *     boundary in the codebase".
 *
 * The schema is obtained by importing the FastAPI app and calling .openapi(). No server is
 * started and no database is touched, so this works before the persistence layer exists.
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = resolve(here, "..");
const repoRoot = resolve(packageRoot, "..", "..");
const outputFile = join(packageRoot, "src", "schema.d.ts");

const BANNER = `/**
 * GENERATED FILE — DO NOT EDIT BY HAND.
 *
 * Produced by \`pnpm contracts:generate\` from the FastAPI OpenAPI schema, which is derived from the
 * Pydantic models in apps/api. AGENTS.md §6:
 *
 *   "The frontend imports types only from @asebe/contracts. Hand-written \`interface Post { … }\`
 *    in apps/web is forbidden — it will drift and nothing will catch it."
 *
 * An edit made here is lost on the next generation, and CI will fail on the resulting diff.
 * To change a type, change the Pydantic model and regenerate.
 */

`;

function main() {
  const scratch = mkdtempSync(join(tmpdir(), "asebe-openapi-"));
  const specPath = join(scratch, "openapi.json");

  try {
    const spec = execFileSync(
      "uv",
      ["run", "python", "apps/api/scripts/dump_openapi.py"],
      { cwd: repoRoot, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
    );
    writeFileSync(specPath, spec, "utf8");

    execFileSync("pnpm", ["exec", "openapi-typescript", specPath, "-o", outputFile], {
      cwd: repoRoot,
      stdio: "inherit",
    });

    const generated = readFileSync(outputFile, "utf8");
    writeFileSync(outputFile, BANNER + generated, "utf8");

    process.stdout.write(`Wrote ${outputFile}\n`);
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
}

main();
