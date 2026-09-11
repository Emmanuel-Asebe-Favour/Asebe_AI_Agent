"""FastAPI application factory.

AGENTS.md §5: "apps/api/ — FastAPI. HTTP concerns only: parse, authorize, delegate, serialize."

The application is assembled by a factory rather than at import time so tests can build an app
without the module-level singleton, and so the OpenAPI schema can be generated deterministically
by ``scripts/dump_openapi.py`` (which is what CI diffs against the committed contract).
"""

from __future__ import annotations

from fastapi import FastAPI

from asebe_api.routes.health import router as health_router


def create_app() -> FastAPI:
    """Build the application.

    Routes are registered explicitly. There is deliberately no auto-discovery: a route that exists
    but is not listed here does not exist, which makes an accidental unauthenticated endpoint a
    visible omission rather than a silent addition (R12 — authorization is enforced server-side,
    and a route nobody remembered to protect is how that rule gets broken).
    """
    app = FastAPI(
        title="Asebe API",
        version="0.0.0",
        summary="Creator publishing platform API.",
        # The OpenAPI schema is the single source of truth for the frontend contract
        # (AGENTS.md §6). It is served in development and consumed by the contract generator;
        # production exposure is decided by the deployment target (docs/architecture.md §9).
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.include_router(health_router)
    return app


app = create_app()
