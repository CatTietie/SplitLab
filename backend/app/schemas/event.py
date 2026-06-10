import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    experiment_key: str
    group_name: str
    user_id: str = Field(max_length=256)
    event_name: str = Field(max_length=128)
    metadata: dict | None = None
    event_time: datetime


class EventBatch(BaseModel):
    events: list[EventCreate] = Field(max_length=500)


class EventResponse(BaseModel):
    id: int
    experiment_id: uuid.UUID
    group_id: uuid.UUID
    user_id: str
    event_name: str
    event_time: datetime
    received_at: datetime

    model_config = {"from_attributes": True}
