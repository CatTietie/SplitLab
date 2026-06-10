import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core.database import get_db
from app.core.redis import get_redis
from app.models import RolloutStepLog
from app.schemas.experiment import (
    ExperimentCreate, ExperimentUpdate, ExperimentResponse,
    ExperimentListResponse, WhitelistCreate, WhitelistResponse,
    RolloutAdvanceRequest, RolloutStatusResponse, RolloutStepLogResponse, RolloutStep,
)
from app.services import experiment_service
from app.services.audit_service import log_audit
from app.services.config_service import invalidate_config_cache
from app.services.snapshot_service import create_snapshot
from app.services.rollout_engine import (
    start_gradual_rollout, advance_step, rollback_step,
    pause_rollout, resume_rollout, needs_confirmation,
)

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentResponse, status_code=201)
async def create_experiment(
    data: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.create_experiment(db, data)
    await invalidate_config_cache(redis_client)
    return exp


@router.get("", response_model=ExperimentListResponse)
async def list_experiments(
    status: str | None = Query(None),
    layer_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    items = await experiment_service.list_experiments(db, status=status, layer_id=layer_id)
    return ExperimentListResponse(items=items, total=len(items))


@router.get("/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.put("/{experiment_id}", response_model=ExperimentResponse)
async def update_experiment(
    experiment_id: uuid.UUID,
    data: ExperimentUpdate,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.update_experiment(db, experiment_id, data)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    await invalidate_config_cache(redis_client)
    return exp


@router.delete("/{experiment_id}", status_code=204)
async def delete_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    success = await experiment_service.delete_experiment(db, experiment_id)
    if not success:
        raise HTTPException(status_code=404, detail="Experiment not found")
    await invalidate_config_cache(redis_client)


@router.post("/{experiment_id}/start", response_model=ExperimentResponse)
async def start_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status not in ("draft", "paused"):
        raise HTTPException(status_code=400, detail=f"Cannot start experiment in status '{exp.status}'")
    old_status = exp.status
    exp.status = "running"
    await log_audit(db, "experiment", exp.id, "start", old_value={"status": old_status}, new_value={"status": "running"})
    await db.commit()
    await db.refresh(exp, attribute_names=["groups"])
    await invalidate_config_cache(redis_client)

    if exp.rollout_steps:
        await start_gradual_rollout(db, redis_client, exp.id)

    return exp


@router.post("/{experiment_id}/pause", response_model=ExperimentResponse)
async def pause_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status != "running":
        raise HTTPException(status_code=400, detail="Can only pause a running experiment")
    exp.status = "paused"
    await log_audit(db, "experiment", exp.id, "pause", old_value={"status": "running"}, new_value={"status": "paused"})
    await db.commit()
    await db.refresh(exp)
    await invalidate_config_cache(redis_client)

    if exp.current_step_index is not None:
        await pause_rollout(redis_client, exp.id)

    return exp


@router.post("/{experiment_id}/resume", response_model=ExperimentResponse)
async def resume_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status != "paused":
        raise HTTPException(status_code=400, detail="Can only resume a paused experiment")
    exp.status = "running"
    await log_audit(db, "experiment", exp.id, "resume", old_value={"status": "paused"}, new_value={"status": "running"})
    await db.commit()
    await db.refresh(exp, attribute_names=["groups"])
    await invalidate_config_cache(redis_client)

    if exp.current_step_index is not None:
        await resume_rollout(db, redis_client, exp.id)

    return exp


@router.post("/{experiment_id}/rollout", response_model=ExperimentResponse)
async def rollout_experiment(
    experiment_id: uuid.UUID,
    winner_group_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status not in ("running", "paused"):
        raise HTTPException(status_code=400, detail="Can only rollout running/paused experiments")

    await create_snapshot(db, experiment_id, "before_rollout")
    old_status = exp.status
    exp.status = "full_rollout"
    exp.winner_group_id = winner_group_id
    exp.current_step_index = None
    await log_audit(
        db, "experiment", exp.id, "rollout",
        old_value={"status": old_status},
        new_value={"status": "full_rollout", "winner_group_id": str(winner_group_id)},
    )
    await db.commit()
    await db.refresh(exp)
    await invalidate_config_cache(redis_client)

    from app.services.rollout_timer import cancel_timer
    await cancel_timer(redis_client, experiment_id)

    return exp


@router.post("/{experiment_id}/rollback", response_model=ExperimentResponse)
async def rollback_experiment(
    experiment_id: uuid.UUID,
    snapshot_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    from app.services.snapshot_service import rollback_to_snapshot
    try:
        exp = await rollback_to_snapshot(db, experiment_id, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await invalidate_config_cache(redis_client)
    return exp


@router.post("/{experiment_id}/whitelist", response_model=WhitelistResponse, status_code=201)
async def add_whitelist(
    experiment_id: uuid.UUID,
    data: WhitelistCreate,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    entry = await experiment_service.add_whitelist(db, experiment_id, data.group_id, data.user_id)
    await invalidate_config_cache(redis_client)
    return entry


@router.post("/{experiment_id}/rollout-advance", response_model=ExperimentResponse)
async def advance_rollout_step(
    experiment_id: uuid.UUID,
    body: RolloutAdvanceRequest = RolloutAdvanceRequest(),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status != "running" or exp.current_step_index is None:
        raise HTTPException(status_code=400, detail="Experiment is not in gradual rollout mode")
    if exp.current_step_index >= len(exp.rollout_steps) - 1:
        raise HTTPException(status_code=400, detail="Already at final step")

    if await needs_confirmation(redis_client, experiment_id) and not body.confirmed:
        raise HTTPException(status_code=409, detail="Confirmation required after rollback. Set confirmed=true to proceed.")

    await advance_step(db, redis_client, experiment_id, "manual_advance", triggered_by="api_user")
    exp = await experiment_service.get_experiment(db, experiment_id)
    return exp


@router.post("/{experiment_id}/rollout-rollback", response_model=ExperimentResponse)
async def rollback_rollout_step(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    if exp.status != "running" or exp.current_step_index is None:
        raise HTTPException(status_code=400, detail="Experiment is not in gradual rollout mode")
    if exp.current_step_index <= 0:
        raise HTTPException(status_code=400, detail="Already at first step, cannot rollback further")

    await rollback_step(db, redis_client, experiment_id, "manual_rollback", triggered_by="api_user")
    exp = await experiment_service.get_experiment(db, experiment_id)
    return exp


@router.get("/{experiment_id}/rollout-status", response_model=RolloutStatusResponse)
async def get_rollout_status(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    exp = await experiment_service.get_experiment(db, experiment_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    steps = [RolloutStep(**s) for s in exp.rollout_steps] if exp.rollout_steps else []
    current_pct = None
    if exp.current_step_index is not None and exp.rollout_steps:
        current_pct = exp.rollout_steps[exp.current_step_index]["traffic_percentage"]

    result = await db.execute(
        select(RolloutStepLog)
        .where(RolloutStepLog.experiment_id == experiment_id)
        .order_by(RolloutStepLog.created_at.desc())
        .limit(50)
    )
    logs = result.scalars().all()

    return RolloutStatusResponse(
        current_step_index=exp.current_step_index,
        current_traffic_percentage=current_pct,
        steps=steps,
        step_logs=[RolloutStepLogResponse.model_validate(log) for log in logs],
    )
