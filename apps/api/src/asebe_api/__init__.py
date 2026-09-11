"""The API application package.

AGENTS.md §5 places one hard rule on everything under this package:

    "apps/api route handlers must never talk to the database directly. Route → domain service →
     repository."

So route modules parse input, delegate to a domain service, and serialize the result. When a route
needs data, the repository enters through a domain protocol defined in ``asebe_domain`` and
implemented in ``asebe_infrastructure`` — never by importing a session or a model here.
"""

__all__: list[str] = []
