from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
import uuid
from pydantic import BaseModel, Field, ConfigDict

class DomainModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, from_attributes=True)

class DomainEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_name: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
