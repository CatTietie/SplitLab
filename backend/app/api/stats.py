import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.stats import ExperimentStatsResponse
from app.services.stats_service import compute_experiment_stats

router = APIRouter(prefix="/api/v1/experiments", tags=["stats"])


@router.get("/{experiment_id}/stats", response_model=ExperimentStatsResponse)
async def get_experiment_stats(
    experiment_id: uuid.UUID,
    goal_event: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await compute_experiment_stats(db, str(experiment_id), goal_event)
