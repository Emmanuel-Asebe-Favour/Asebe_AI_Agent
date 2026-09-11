"""The domain layer: this project's business logic, and its reliability guarantees.

AGENTS.md §5 defines this package's defining constraint:

    "``packages/domain`` must never import FastAPI, SQLAlchemy, or ``httpx`` directly. It defines
     protocols; ``packages/infrastructure`` implements them. This is what lets the domain be tested
     without a database and lets the worker and API run identical logic."

That constraint is enforced by this package's dependency list (see pyproject.toml: pydantic is the
only entry) and checked statically by tests/test_boundaries.py.

architecture.md §6 gives the two practical reasons it is worth the discipline:

1. A scheduled publish and an immediate publish must not diverge in retry or verification
   behaviour. Shared code, not parallel implementations.
2. The reliability rules become pure functions over values, so they get exhaustive tests that run
   in milliseconds — covering every (status, event) pair.

Implemented so far: ``publishing`` (the reliability kernel) and ``adapters`` (the platform
contract). The remaining subpackages are declared boundaries with no implementation yet; each
names its responsibility and what it will need.
"""

__all__: list[str] = []
