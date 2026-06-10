from pydantic import BaseModel


class GroupStatsResponse(BaseModel):
    group_name: str
    total_users: int
    conversions: int
    conversion_rate: float
    ci_lower: float
    ci_upper: float


class ExperimentStatsResponse(BaseModel):
    experiment_id: str
    goal_event: str
    groups: list[GroupStatsResponse]
    z_statistic: float | None = None
    p_value: float | None = None
    is_significant: bool = False
    recommended_sample_size: int | None = None
