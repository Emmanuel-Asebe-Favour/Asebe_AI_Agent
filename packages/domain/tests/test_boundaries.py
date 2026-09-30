"""Mechanical enforcement of AGENTS.md §5's hard boundary.

    "``packages/domain`` must never import FastAPI, SQLAlchemy, or ``httpx`` directly. It defines
     protocols; ``packages/infrastructure`` implements them."

The primary enforcement is that these packages are not dependencies of ``asebe-domain``, so an
import fails at runtime. This file adds two things that the dependency list cannot give:

1. A static check over the source tree, which catches a forbidden import even if the dependency
   were later added to the wrong pyproject.
2. A guard on the dependency list itself, so widening it is a deliberate, visible act rather than a
   quiet edit that erodes the boundary.

architecture.md §6 explains what is protected: the ability to test the reliability rules without a
database, and the guarantee that the worker and the API run identical publishing logic.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import pytest

DOMAIN_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = DOMAIN_ROOT / "src" / "asebe_domain"
PYPROJECT = DOMAIN_ROOT / "pyproject.toml"

# Anything that ties the domain to a framework, a driver, or a transport. The domain defines
# protocols for these; packages/infrastructure implements them.
FORBIDDEN_IMPORTS = frozenset(
    {
        "fastapi",
        "starlette",
        "sqlalchemy",
        "alembic",
        "asyncpg",
        "psycopg",
        "psycopg2",
        "procrastinate",
        "httpx",
        "requests",
        "aiohttp",
        "pydantic_settings",
    }
)

# AGENTS.md §5: "No generic utils/ or helpers/ module. Name the responsibility."
FORBIDDEN_MODULE_NAMES = frozenset({"utils", "helpers", "common", "misc"})


def _python_files() -> list[Path]:
    files = sorted(SRC_ROOT.rglob("*.py"))
    assert files, f"no Python sources found under {SRC_ROOT}"
    return files


def _imported_top_level_modules(path: Path) -> set[str]:
    """Every top-level module name imported by ``path``, including inside functions."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_no_forbidden_framework_imports(path: Path) -> None:
    """Runs per-file so a failure names the offending module rather than the whole package."""
    offenders = _imported_top_level_modules(path) & FORBIDDEN_IMPORTS
    assert not offenders, (
        f"{path.relative_to(DOMAIN_ROOT)} imports {sorted(offenders)}. AGENTS.md §5 forbids the "
        f"domain from depending on frameworks; define a Protocol and implement it in "
        f"packages/infrastructure."
    )


def test_domain_dependency_list_is_only_pydantic() -> None:
    """Widening this list is an architectural change, not a convenience.

    pydantic earns its place because the reliability guarantees are enforced by frozen, validated
    model types. Any other entry needs an argument: architecture.md §6's testability claim depends
    on this list staying tiny.
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dependencies = config["project"]["dependencies"]

    assert len(dependencies) == 1, (
        f"asebe-domain should depend on pydantic alone, found {dependencies}. "
        f"See packages/domain/pyproject.toml for why this list is the enforcement mechanism."
    )
    assert dependencies[0].startswith("pydantic")


def _declared_distributions(config: dict[str, object]) -> set[str]:
    """Every distribution named in any dependency-bearing table of a pyproject.

    All four tables are walked, because a forbidden package hidden in ``optional-dependencies`` or
    a dev group is exactly as much a boundary violation as one in ``dependencies`` — and is easier
    to add without noticing. PEP 508 specifiers are reduced to the bare distribution name:
    ``"httpx>=0.27"`` -> ``"httpx"``, ``"sqlalchemy[asyncio]==2.0"`` -> ``"sqlalchemy"``.
    """
    requirements: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            requirements.append(value)
        elif isinstance(value, list):
            requirements.extend(str(item) for item in value)
        elif isinstance(value, dict):
            for nested in value.values():
                collect(nested)

    project = config.get("project", {})
    if isinstance(project, dict):
        collect(project.get("dependencies", []))
        collect(project.get("optional-dependencies", {}))

    collect(config.get("dependency-groups", {}))

    # Narrow to a local first. Written as one expression, the ``.get()`` chain would be typed as
    # ``object.get`` even though it is guarded by an isinstance -- the guard is applied to a
    # second, independent call and so does not narrow the result of the first. mypy said so.
    build_system = config.get("build-system", {})
    if isinstance(build_system, dict):
        collect(build_system.get("requires", []))

    declared: set[str] = set()
    for requirement in requirements:
        name = requirement.split("[")[0].split(">")[0].split("=")[0].split("<")[0]
        name = name.split(";")[0].strip().lower()
        if name:
            declared.add(name)
    return declared


def test_domain_declares_no_framework_dependencies_anywhere() -> None:
    """Catches a forbidden package declared under an optional or dev dependency group.

    The non-vacuity assertion below is load-bearing. An earlier version of this test read only
    ``dependency-groups``, which this pyproject does not have — so it iterated an empty dict and
    passed without examining anything. A boundary test that cannot fail is worse than no test,
    because it reports the boundary as checked.
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared = _declared_distributions(config)

    assert declared, (
        "no dependencies found in packages/domain/pyproject.toml. This test is meant to guard the "
        "dependency list, so finding nothing means the parser is wrong, not that the list is clean."
    )
    assert "pydantic" in declared, (
        f"pydantic should be declared by the domain, found {sorted(declared)}"
    )
    assert not (declared & FORBIDDEN_IMPORTS), (
        f"asebe-domain declares forbidden dependencies: {sorted(declared & FORBIDDEN_IMPORTS)}"
    )


def test_no_generic_utility_modules() -> None:
    """AGENTS.md §5: "If you cannot name it, you have not identified the responsibility yet." """
    offenders = [path.name for path in _python_files() if path.stem in FORBIDDEN_MODULE_NAMES]
    assert not offenders, f"forbidden generic module names: {offenders}"


def test_domain_imports_nothing_from_apps() -> None:
    """Dependencies point inward. The domain must not reach up into an application."""
    for path in _python_files():
        imported = _imported_top_level_modules(path)
        assert not {m for m in imported if m.startswith("apps")}, (
            f"{path.relative_to(DOMAIN_ROOT)} imports from apps/; the domain is the innermost layer"
        )
