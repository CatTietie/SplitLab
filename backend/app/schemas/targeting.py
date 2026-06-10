import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


ATTR_KEY_PATTERN = re.compile(r"^[a-z_]+$")


class TargetingCondition(BaseModel):
    key: str = Field(max_length=64)
    op: Literal["eq", "neq", "in", "not_in", "contains", "gt", "lt", "gte", "lte"]
    value: str | None = None
    values: list[str] | None = None

    @field_validator("key")
    @classmethod
    def validate_key_format(cls, v: str) -> str:
        if not ATTR_KEY_PATTERN.match(v):
            raise ValueError("attribute key must match [a-z_]+")
        return v


class TargetingRule(BaseModel):
    operator: Literal["AND", "OR"] | None = None
    rules: list["TargetingRule"] | None = None
    key: str | None = None
    op: Literal["eq", "neq", "in", "not_in", "contains", "gt", "lt", "gte", "lte"] | None = None
    value: str | None = None
    values: list[str] | None = None


def validate_targeting_depth(rules: dict, depth: int = 0) -> None:
    if depth > 3:
        raise ValueError("Targeting rules exceed maximum nesting depth of 3")
    if "operator" in rules and "rules" in rules:
        for sub in rules["rules"]:
            validate_targeting_depth(sub, depth + 1)


class AttributeUpload(BaseModel):
    user_id: str = Field(max_length=256, min_length=1)
    attributes: dict[str, str]

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 20:
            raise ValueError("Maximum 20 attributes per user")
        for key, value in v.items():
            if len(key) > 64 or not ATTR_KEY_PATTERN.match(key):
                raise ValueError(f"Invalid attribute key: {key}")
            if len(value) > 256:
                raise ValueError(f"Attribute value too long for key: {key}")
        return v


class AttributeBatchRequest(BaseModel):
    users: list[AttributeUpload] = Field(max_length=100)


class DimensionGroupDistribution(BaseModel):
    group_name: str
    attribute_value: str
    count: int
    proportion: float


class DimensionBalance(BaseModel):
    dimension: str
    distributions: list[DimensionGroupDistribution]
    max_bias: float
    warning: bool


class StratificationBalanceResponse(BaseModel):
    dimensions: list[DimensionBalance]
