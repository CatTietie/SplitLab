import uuid
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Experiment, ExperimentGroup, ExperimentLayer, Whitelist
from app.schemas.experiment import ExperimentCreate, ExperimentUpdate
from app.services.audit_service import log_audit


async def create_experiment(db: AsyncSession, data: ExperimentCreate) -> Experiment:
    experiment = Experiment(
        layer_id=data.layer_id,
        key=data.key,
        name=data.name,
        description=data.description,
        bucket_start=data.bucket_start,
        bucket_end=data.bucket_end,
        created_by=data.created_by,
        rollout_steps=[s.model_dump() for s in data.rollout_steps] if data.rollout_steps else None,
        guardrail_metrics=[m.model_dump() for m in data.guardrail_metrics] if data.guardrail_metrics else None,
    )
    db.add(experiment)
    await db.flush()

    for g in data.groups:
        group = ExperimentGroup(
            experiment_id=experiment.id,
            name=g.name,
            traffic_percentage=g.traffic_percentage,
            config_json=g.config_json,
        )
        db.add(group)

    await log_audit(db, "experiment", experiment.id, "create", new_value=data.model_dump(mode="json"))
    await db.commit()
    await db.refresh(experiment, attribute_names=["groups"])
    return experiment


async def get_experiment(db: AsyncSession, experiment_id: uuid.UUID) -> Experiment | None:
    result = await db.execute(
        select(Experiment)
        .options(selectinload(Experiment.groups), selectinload(Experiment.whitelists))
        .where(Experiment.id == experiment_id)
    )
    return result.scalar_one_or_none()


async def list_experiments(db: AsyncSession, status: str | None = None, layer_id: uuid.UUID | None = None) -> list[Experiment]:
    query = select(Experiment).options(selectinload(Experiment.groups))
    if status:
        query = query.where(Experiment.status == status)
    if layer_id:
        query = query.where(Experiment.layer_id == layer_id)
    query = query.order_by(Experiment.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def update_experiment(db: AsyncSession, experiment_id: uuid.UUID, data: ExperimentUpdate) -> Experiment | None:
    exp = await get_experiment(db, experiment_id)
    if not exp:
        return None

    old_data = {"name": exp.name, "description": exp.description, "bucket_start": exp.bucket_start, "bucket_end": exp.bucket_end}
    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        if field == "rollout_steps" and value is not None:
            value = [s if isinstance(s, dict) else s.model_dump() for s in value]
        elif field == "guardrail_metrics" and value is not None:
            value = [m if isinstance(m, dict) else m.model_dump() for m in value]
        setattr(exp, field, value)

    await log_audit(db, "experiment", exp.id, "update", old_value=old_data, new_value=update_fields)
    await db.commit()
    await db.refresh(exp)
    return exp


async def delete_experiment(db: AsyncSession, experiment_id: uuid.UUID) -> bool:
    exp = await get_experiment(db, experiment_id)
    if not exp:
        return False
    exp.status = "archived"
    await log_audit(db, "experiment", exp.id, "archive")
    await db.commit()
    return True


async def create_layer(db: AsyncSession, name: str, description: str | None = None) -> ExperimentLayer:
    layer = ExperimentLayer(
        name=name,
        salt=secrets.token_hex(16),
        description=description,
    )
    db.add(layer)
    await db.flush()
    await log_audit(db, "layer", layer.id, "create", new_value={"name": name})
    await db.commit()
    await db.refresh(layer)
    return layer


async def get_layer(db: AsyncSession, layer_id: uuid.UUID) -> ExperimentLayer | None:
    result = await db.execute(
        select(ExperimentLayer)
        .options(selectinload(ExperimentLayer.experiments).selectinload(Experiment.groups))
        .where(ExperimentLayer.id == layer_id)
    )
    return result.scalar_one_or_none()


async def list_layers(db: AsyncSession) -> list[ExperimentLayer]:
    result = await db.execute(select(ExperimentLayer).order_by(ExperimentLayer.created_at.desc()))
    return list(result.scalars().all())


async def add_whitelist(db: AsyncSession, experiment_id: uuid.UUID, group_id: uuid.UUID, user_id: str) -> Whitelist:
    entry = Whitelist(experiment_id=experiment_id, group_id=group_id, user_id=user_id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry
