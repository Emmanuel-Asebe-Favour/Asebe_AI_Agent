"""Job tasks.

Deliberately thin, per AGENTS.md §5. Each task loads state through a repository, calls a domain
function, and persists the result. It must not branch on publishing status, retry eligibility, or
platform capability — those decisions belong to ``asebe_domain`` so that the worker and the API
cannot diverge (architecture.md §6).

**Not executed.** These tasks need PostgreSQL and a running Procrastinate worker, neither of which
is available in this environment.
"""

__all__: list[str] = []
