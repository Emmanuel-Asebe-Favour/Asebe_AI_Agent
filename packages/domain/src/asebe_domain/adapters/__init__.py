"""The platform adapter contract.

``protocol.py`` defines the ``PlatformAdapter`` protocol and the value types crossing it. Adapters
for real platforms are added per AGENTS.md §7's recipe, one directory each, and never by modifying
core publishing code.

No adapter is implemented yet. README's MVP scope calls for one or two initially.
"""

from asebe_domain.adapters.protocol import (
    AnalyticsResult,
    ConnectInput,
    ConnectionResult,
    PlatformAdapter,
    PlatformCapabilities,
    PublishPostInput,
    RefreshInput,
    ValidationMessage,
    ValidationResult,
    ValidationSeverity,
    VerificationOutcome,
    VerificationResult,
)

__all__ = [
    "AnalyticsResult",
    "ConnectInput",
    "ConnectionResult",
    "PlatformAdapter",
    "PlatformCapabilities",
    "PublishPostInput",
    "RefreshInput",
    "ValidationMessage",
    "ValidationResult",
    "ValidationSeverity",
    "VerificationOutcome",
    "VerificationResult",
]
