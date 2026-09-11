"""Health and readiness endpoints.

Two distinct questions, deliberately not collapsed into one endpoint:

* ``/health`` — is the process alive and serving? Answerable without a database, so it stays
  useful when the database is the thing that is broken.
* ``/ready`` — can this process serve real traffic? Depends on the database, so it reports
  not-ready rather than failing.

Conflating them makes a process that is running fine but cannot reach Postgres get restarted by an
orchestrator, which turns a database blip into a crash loop.

Route shape follows AGENTS.md §5: parse, delegate, serialize. There is no logic here, and no
database access.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Response model. Per AGENTS.md §6 this is the single source of truth for the wire format,
    and any change to it is a breaking frontend change requiring a contract regeneration."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "not_ready"]
    database: Literal["reachable", "unreachable", "not_configured"]


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    """Liveness only. Touches nothing external, so it cannot fail for an infrastructure reason.

    README requires no user-visible string to be hardcoded (R13); the value returned here is a
    machine-readable literal, not interface text, so it is not subject to that rule. Anything a
    user reads is resolved from ``packages/contracts`` message keys.
    """
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready() -> ReadinessResponse:
    """Reports readiness, never raises for an infrastructure failure.

    Not yet wired to a real check: the database layer is not functional in this increment (no
    PostgreSQL available — see docs/architecture.md §9 and the increment notes). Reporting
    ``not_configured`` is accurate and, importantly, is not the same claim as ``unreachable``.

    When the database lands, this must perform a real round-trip. Leaving it returning a constant
    ``ready`` would be exactly the "claim success we cannot prove" failure AGENTS.md §2 forbids,
    applied to infrastructure rather than to publishing.
    """
    return ReadinessResponse(status="not_ready", database="not_configured")
