"""Database access: engine, session, declarative base, and models.

This is the layer that owns PostgreSQL. Nothing above it — route handlers especially — may import
from here directly (AGENTS.md §5: "apps/api route handlers must never talk to the database
directly. Route → domain service → repository.").

The engine and session factory are not defined yet. They belong with the persistence work that
requires a running database, and defining them without being able to execute a single query would
produce configuration nobody could have validated.
"""

__all__: list[str] = []
