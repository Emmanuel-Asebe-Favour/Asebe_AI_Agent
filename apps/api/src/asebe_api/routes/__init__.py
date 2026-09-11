"""HTTP route modules.

This package is declared empty on purpose. An ``__init__.py`` that imported the route modules would
make ``main.create_app`` sensitive to import order and would let a route be registered by the mere
act of importing a module. Routes are wired explicitly in ``main.create_app`` instead, so a route
that exists is a route somebody deliberately attached to the application.
"""

__all__: list[str] = []
