"""Procrastinate application and worker entrypoint.

AGENTS.md §4 fixes the queue as Procrastinate for a specific reason:

    "scheduled publishing and the ``PUBLISHING`` state change must commit together. With Redis in
     between, a crash can leave a post marked ``SCHEDULED`` with no job, or a job with no post.
     With transactional deferral that window does not exist. Do not introduce Redis."

So the connector here is necessarily a Postgres one, and jobs must be deferred on the caller's
existing connection rather than on a fresh one. ``defer`` with a connection is what makes R9
achievable; a deferral that opens its own connection reintroduces exactly the window described
above.

**Not executed.** Requires PostgreSQL. See packages/infrastructure/__init__.py.
"""

from __future__ import annotations

from procrastinate import App, PsycopgConnector
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """Worker configuration, from the environment.

    ``database_url`` is the single setting that matters. It is read from the environment rather
    than defaulted to a literal, because a hardcoded fallback that happens to point at a real
    database is a footgun, and one pointing at localhost fails confusingly in production.
    """

    model_config = SettingsConfigDict(env_prefix="ASEBE_", extra="ignore")

    database_url: str


def create_app(settings: WorkerSettings | None = None) -> App:
    """Build the Procrastinate app.

    A factory rather than a module-level global so tests can construct an app against a test
    database, and so importing this module does not require a reachable database — which matters
    because ``tasks/`` imports ``app`` from here.
    """
    resolved = settings or WorkerSettings()  # type: ignore[call-arg]
    return App(connector=PsycopgConnector(conninfo=resolved.database_url))


app = create_app()
"""Module-level app that task modules attach to via ``@app.task``."""


__all__ = ["WorkerSettings", "app", "create_app"]
