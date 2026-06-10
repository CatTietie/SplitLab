import uuid
from pydantic import BaseModel


class GroupConfig(BaseModel):
    id: str
    name: str
    traffic_percentage: int
    config_json: dict | None = None


class ExperimentConfig(BaseModel):
    id: str
    key: str
    status: str
    bucket_start: int
    bucket_end: int
    groups: list[GroupConfig]
    whitelist: dict[str, str] = {}  # user_id -> group_name


class LayerConfig(BaseModel):
    id: str
    name: str
    salt: str
    experiments: list[ExperimentConfig]


class SDKConfigResponse(BaseModel):
    layers: list[LayerConfig]
    version: str
