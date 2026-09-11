"""Dump the live OpenAPI schema to stdout.

This is the first stage of the contract pipeline described in AGENTS.md §6:

    Pydantic models  →  FastAPI OpenAPI  →  generated schema.d.ts  →  frontend

``packages/contracts`` runs this, then feeds the output to openapi-typescript. The result is
committed, and CI regenerates it and fails if the committed copy differs — so a Pydantic model
changed without regenerating the contract breaks the build rather than drifting silently into
production.

Requires only that ``asebe_api`` imports. No database access, no running server: the schema is
derived from the type annotations, so this works before the persistence layer exists.
"""

from __future__ import annotations

import json
import sys

from asebe_api.main import create_app


def main() -> int:
    schema = create_app().openapi()
    # sort_keys so the output is byte-stable: CI diffs this file, and dict ordering from
    # FastAPI's route registration is not a stable interface to depend on.
    json.dump(schema, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
