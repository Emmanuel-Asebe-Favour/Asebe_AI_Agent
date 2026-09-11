"""The worker process.

AGENTS.md §5: "apps/worker/ — Procrastinate consumer entrypoint. Thin — registers tasks, calls
domain."

It holds no publishing logic. A scheduled publish and an immediate publish must run identical retry
and verification behaviour (architecture.md §6), and the only structural way to guarantee that is
for both to call the same domain functions rather than each implementing the rules.
"""

__all__: list[str] = []
