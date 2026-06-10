import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class RolloutStep(BaseModel):
    traffic_percentage: int = Field(ge=1, le=100)
    hold_seconds: int = Field(ge=0)


class GuardrailMetric(BaseModel):
    metric_name: str = Field(max_length=128)
    threshold: float = Field(gt=0)
    direction: str = Field(pattern=r"^(up|down)$")


class GroupCreate(BaseModel):
    name: str = Field(max_length=64)
    traffic_percentage: int = Field(ge=0, le=100)
    config_json: dict | None = None


class GroupResponse(BaseModel):
    id: uuid.UUID
    name: str
    traffic_percentage: int
    config_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WhitelistCreate(BaseModel):
    group_id: uuid.UUID
    user_id: str = Field(max_length=256)


class WhitelistResponse(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    user_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExperimentCreate(BaseModel):
    layer_id: uuid.UUID
    key: str = Field(max_length=128)
    name: str = Field(max_length=256)
    description: str | None = None
    bucket_start: int = Field(ge=0, le=9999)
    bucket_end: int = Field(ge=0, le=9999)
    groups: list[GroupCreate]
    created_by: str | None = None
    rollout_steps: list[RolloutStep] | None = None
    guardrail_metrics: list[GuardrailMetric] | None = None
    targeting_rules: dict | None = None
    stratification_dimensions: list[str] | None = Field(default=None, max_length=5)


class ExperimentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    description: str | None = None
    bucket_start: int | None = Field(default=None, ge=0, le=9999)
    bucket_end: int | None = Field(default=None, ge=0, le=9999)
    rollout_steps: list[RolloutStep] | None = None
    guardrail_metrics: list[GuardrailMetric] | None = None
    targeting_rules: dict | None = None
    stratification_dimensions: list[str] | None = None


class ExperimentResponse(BaseModel):
    id: uuid.UUID
    layer_id: uuid.UUID
    key: str
    name: str
    description: str | None
    status: str
    bucket_start: int
    bucket_end: int
    winner_group_id: uuid.UUID | None
    rollout_steps: list[RolloutStep] | None = None
    current_step_index: int | None = None
    guardrail_metrics: list[GuardrailMetric] | None = None
    targeting_rules: dict | None = None
    stratification_dimensions: list[str] | None = None
    created_by: str | None
    created_at: datetime
    updated_at: datetime
    groups: list[GroupResponse] = []

    model_config = {"from_attributes": True}


class ExperimentListResponse(BaseModel):
    items: list[ExperimentResponse]
    total: int


class RolloutAdvanceRequest(BaseModel):
    confirmed: bool = False


class RolloutStepLogResponse(BaseModel):
    id: uuid.UUID
    step_index: int
    traffic_percentage: int
    trigger_type: str
    triggered_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RolloutStatusResponse(BaseModel):
    current_step_index: int | None
    current_traffic_percentage: int | None
    steps: list[RolloutStep]
    step_logs: list[RolloutStepLogResponse] = []
