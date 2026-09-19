"""Response shape for the activity record."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.activity_event import ActivityVia


class ActivityOut(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    entity_type: str
    entity_id: UUID | None
    summary: str
    via: ActivityVia
    actor: str | None
