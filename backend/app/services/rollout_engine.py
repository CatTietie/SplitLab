import uuid
import logging

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.models import Experiment, RolloutStepLog, Event
from app.services.audit_service import log_audit
from app.services.config_service import invalidate_config_cache
from app.services.sse_publisher import publish_event
from app.services.rollout_timer import schedule_timer, cancel_timer, save_remaining, pop_remaining

logger = logging.getLogger(__name__)

CONFIRM_KEY_PREFIX = "splitlab:rollout_confirm_needed:"
CONFIRM_TTL = 3600


async def start_gradual_rollout(db: AsyncSession, redis_client: redis.Redis, experiment_id: uuid.UUID):
    exp = await _get_experiment(db, experiment_id)
    if not exp or not exp.rollout_steps:
        return

    exp.current_step_index = 0
    step = exp.rollout_steps[0]

    await _log_step(db, experiment_id, 0, step["traffic_percentage"], "auto_advance", None)
    await log_audit(
        db, "experiment", experiment_id, "rollout_step",
        new_value={"step_index": 0, "traffic_percentage": step["traffic_percentage"]},
    )
    await db.commit()

    await invalidate_config_cache(redis_client)
    await publish_event(redis_client, "rollout_step_advanced", {
        "experiment_id": str(experiment_id),
        "step_index": 0,
        "traffic_percentage": step["traffic_percentage"],
        "trigger_type": "auto_advance",
    })

    if step["hold_seconds"] > 0:
        await schedule_timer(redis_client, experiment_id, step["hold_seconds"])


async def advance_step(
    db: AsyncSession,
    redis_client: redis.Redis,
    experiment_id: uuid.UUID,
    trigger_type: str,
    triggered_by: str | None = None,
):
    exp = await _get_experiment(db, experiment_id)
    if not exp or exp.current_step_index is None or not exp.rollout_steps:
        return

    if exp.current_step_index >= len(exp.rollout_steps) - 1:
        return

    await cancel_timer(redis_client, experiment_id)

    new_index = exp.current_step_index + 1
    exp.current_step_index = new_index
    step = exp.rollout_steps[new_index]

    await _log_step(db, experiment_id, new_index, step["traffic_percentage"], trigger_type, triggered_by)
    await log_audit(
        db, "experiment", experiment_id, "rollout_step",
        old_value={"step_index": new_index - 1},
        new_value={"step_index": new_index, "traffic_percentage": step["traffic_percentage"], "trigger": trigger_type},
    )
    await db.commit()

    await invalidate_config_cache(redis_client)
    await _clear_confirm_flag(redis_client, experiment_id)

    if new_index == len(exp.rollout_steps) - 1 and step["hold_seconds"] == 0:
        await publish_event(redis_client, "rollout_completed", {
            "experiment_id": str(experiment_id),
            "traffic_percentage": step["traffic_percentage"],
        })
    else:
        await publish_event(redis_client, "rollout_step_advanced", {
            "experiment_id": str(experiment_id),
            "step_index": new_index,
            "traffic_percentage": step["traffic_percentage"],
            "trigger_type": trigger_type,
        })
        if step["hold_seconds"] > 0:
            await schedule_timer(redis_client, experiment_id, step["hold_seconds"])


async def rollback_step(
    db: AsyncSession,
    redis_client: redis.Redis,
    experiment_id: uuid.UUID,
    trigger_type: str,
    triggered_by: str | None = None,
):
    exp = await _get_experiment(db, experiment_id)
    if not exp or exp.current_step_index is None or not exp.rollout_steps:
        return

    if exp.current_step_index <= 0:
        return

    await cancel_timer(redis_client, experiment_id)

    new_index = exp.current_step_index - 1
    exp.current_step_index = new_index
    step = exp.rollout_steps[new_index]

    await _log_step(db, experiment_id, new_index, step["traffic_percentage"], trigger_type, triggered_by)
    await log_audit(
        db, "experiment", experiment_id, "rollout_rollback",
        old_value={"step_index": new_index + 1},
        new_value={"step_index": new_index, "traffic_percentage": step["traffic_percentage"], "trigger": trigger_type},
    )
    await db.commit()

    await invalidate_config_cache(redis_client)
    await _set_confirm_flag(redis_client, experiment_id)

    await publish_event(redis_client, "rollout_step_rolled_back", {
        "experiment_id": str(experiment_id),
        "step_index": new_index,
        "traffic_percentage": step["traffic_percentage"],
        "trigger_type": trigger_type,
    })

    if step["hold_seconds"] > 0:
        await schedule_timer(redis_client, experiment_id, step["hold_seconds"])


async def check_guardrails(db: AsyncSession, redis_client: redis.Redis, experiment_id: uuid.UUID) -> str:
    exp = await _get_experiment(db, experiment_id)
    if not exp or not exp.guardrail_metrics:
        return "ok"

    control_group = next((g for g in exp.groups if g.name == "control"), None)
    treatment_groups = [g for g in exp.groups if g.name != "control"]
    if not control_group or not treatment_groups:
        return "ok"

    for metric in exp.guardrail_metrics:
        metric_name = metric["metric_name"]
        threshold = metric["threshold"]
        direction = metric["direction"]

        control_stats = await _get_metric_stats(db, experiment_id, control_group.id, metric_name)

        if control_stats["total_users"] < 30:
            continue

        for tg in treatment_groups:
            t_stats = await _get_metric_stats(db, experiment_id, tg.id, metric_name)
            if t_stats["total_users"] < 30:
                continue

            control_rate = control_stats["rate"]
            treatment_rate = t_stats["rate"]

            if direction == "up":
                degradation = treatment_rate - control_rate
            else:
                degradation = control_rate - treatment_rate

            if degradation > 2 * threshold:
                await publish_event(redis_client, "rollout_guardrail_warning", {
                    "experiment_id": str(experiment_id),
                    "metric_name": metric_name,
                    "degradation": degradation,
                    "threshold": threshold,
                    "severity": "critical",
                })
                return "rollback"
            elif degradation > threshold:
                await publish_event(redis_client, "rollout_guardrail_warning", {
                    "experiment_id": str(experiment_id),
                    "metric_name": metric_name,
                    "degradation": degradation,
                    "threshold": threshold,
                    "severity": "warning",
                })
                return "warn"

    return "ok"


async def pause_rollout(redis_client: redis.Redis, experiment_id: uuid.UUID):
    await save_remaining(redis_client, experiment_id)
    await cancel_timer(redis_client, experiment_id)


async def resume_rollout(db: AsyncSession, redis_client: redis.Redis, experiment_id: uuid.UUID):
    exp = await _get_experiment(db, experiment_id)
    if not exp or exp.current_step_index is None or not exp.rollout_steps:
        return

    remaining = await pop_remaining(redis_client, experiment_id)
    if remaining is not None:
        if remaining > 0:
            await schedule_timer(redis_client, experiment_id, remaining)
    else:
        step = exp.rollout_steps[exp.current_step_index]
        if step["hold_seconds"] > 0:
            await schedule_timer(redis_client, experiment_id, step["hold_seconds"])


async def needs_confirmation(redis_client: redis.Redis, experiment_id: uuid.UUID) -> bool:
    key = f"{CONFIRM_KEY_PREFIX}{experiment_id}"
    return await redis_client.exists(key) > 0


async def _get_experiment(db: AsyncSession, experiment_id: uuid.UUID) -> Experiment | None:
    from app.services.experiment_service import get_experiment
    return await get_experiment(db, experiment_id)


async def _log_step(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    step_index: int,
    traffic_percentage: int,
    trigger_type: str,
    triggered_by: str | None,
):
    log = RolloutStepLog(
        experiment_id=experiment_id,
        step_index=step_index,
        traffic_percentage=traffic_percentage,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
    )
    db.add(log)


async def _set_confirm_flag(redis_client: redis.Redis, experiment_id: uuid.UUID):
    key = f"{CONFIRM_KEY_PREFIX}{experiment_id}"
    await redis_client.set(key, "1", ex=CONFIRM_TTL)


async def _clear_confirm_flag(redis_client: redis.Redis, experiment_id: uuid.UUID):
    key = f"{CONFIRM_KEY_PREFIX}{experiment_id}"
    await redis_client.delete(key)


async def _get_metric_stats(
    db: AsyncSession,
    experiment_id: uuid.UUID,
    group_id: uuid.UUID,
    metric_name: str,
) -> dict:
    total_result = await db.execute(
        select(func.count(func.distinct(Event.user_id)))
        .where(Event.experiment_id == experiment_id)
        .where(Event.group_id == group_id)
    )
    total_users = total_result.scalar() or 0

    event_result = await db.execute(
        select(func.count(func.distinct(Event.user_id)))
        .where(Event.experiment_id == experiment_id)
        .where(Event.group_id == group_id)
        .where(Event.event_name == metric_name)
    )
    event_users = event_result.scalar() or 0

    rate = event_users / total_users if total_users > 0 else 0.0
    return {"total_users": total_users, "event_users": event_users, "rate": rate}
