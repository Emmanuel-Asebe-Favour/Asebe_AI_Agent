"""SQLAlchemy models.

Importing every model here gives Alembic's autogenerate a single place to import from, so that all
tables are registered in ``Base.metadata`` before it compares against the database. A model that is
not imported is invisible to autogenerate, and the migration silently omits its table — which is
discovered later as a missing column in production.
"""

from asebe_infrastructure.database.models.publishing import (
    ContentItem,
    PlatformPost,
    PublishingAttempt,
)
from asebe_infrastructure.database.models.users import User

__all__ = ["ContentItem", "PlatformPost", "PublishingAttempt", "User"]
