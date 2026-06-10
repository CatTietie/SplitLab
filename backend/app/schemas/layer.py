import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class LayerCreate(BaseModel):
    name: str = Field(max_length=128)
    description: str | None = None


class LayerUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = None


class LayerResponse(BaseModel):
    id: uuid.UUID
    name: str
    salt: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
