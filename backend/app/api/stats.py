import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.stats import ExperimentStatsResponse
from app.schemas.targeting import StratificationBalanceResponse
from app.services.stats_service import compute_experiment_stats
from app.services.stratification_service import compute_stratification_balance
from app.services.experiment_service import get_experiment

router = APIRouter(prefix="/api/v1/experiments", tags=["stats"])


@router.get("/{experiment_id}/stats", response_model=ExperimentStatsResponse)
async def get_experiment_stats(
    experiment_id: uuid.UUID,
    goal_event: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await compute_experiment_stats(db, str(experiment_id), goal_event)


@router.get("/{experiment_id}/stratification", response_model=StratificationBalanceResponse)
async def get_stratification(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    exp = await get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if not exp.stratification_dimensions:
        return StratificationBalanceResponse(dimensions=[])
    return await compute_stratification_balance(db, str(experiment_id), exp.stratification_dimensions)
