"""SQLAlchemy models and repository implementations.

AGENTS.md §5 gives this package one job:

    "packages/domain must never import FastAPI, SQLAlchemy, or httpx directly. It defines
     protocols; packages/infrastructure implements them."

This is the *only* package where SQLAlchemy and httpx are permitted, and the domain's dependency
list proves it (packages/domain/pyproject.toml depends on pydantic alone, and
tests/test_boundaries.py fails if that changes).

## Status: written but NOT verified

There is no PostgreSQL available in this environment (Docker is unreachable, no local server), so
**none of this code has been executed**. No migration has been run, no repository method called, no
test written against a real database. It is transcribed from README's data model and may contain
errors that only a running database would reveal.

It is committed in this state because it is the data model the architecture is built around, and
because leaving it out would make the boundary set in AGENTS.md §5 look smaller than it is. It must
not be treated as working code. The first task in the next increment is to run it.
"""

__all__: list[str] = []
