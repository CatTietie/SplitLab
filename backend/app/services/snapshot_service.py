import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Experiment, ExperimentGroup, ExperimentSnapshot
from app.services.audit_service import log_audit


async def create_snapshot(db: AsyncSession, experiment_id: uuid.UUID, reason: str, performed_by: str | None = None) -> ExperimentSnapshot:
    from app.services.experiment_service import get_experiment
    exp = await get_experiment(db, experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    snapshot_data = {
        "key": exp.key,
        "name": exp.name,
        "description": exp.description,
        "status": exp.status,
        "bucket_start": exp.bucket_start,
        "bucket_end": exp.bucket_end,
        "groups": [
            {"name": g.name, "traffic_percentage": g.traffic_percentage, "config_json": g.config_json}
            for g in exp.groups
        ],
    }

    snapshot = ExperimentSnapshot(
        experiment_id=experiment_id,
        snapshot_data=snapshot_data,
        reason=reason,
        created_by=performed_by,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def rollback_to_snapshot(db: AsyncSession, experiment_id: uuid.UUID, snapshot_id: uuid.UUID) -> Experiment:
    from app.services.experiment_service import get_experiment
    snapshot_result = await db.execute(
        select(ExperimentSnapshot).where(
            ExperimentSnapshot.id == snapshot_id,
            ExperimentSnapshot.experiment_id == experiment_id,
        )
    )
    snapshot = snapshot_result.scalar_one_or_none()
    if not snapshot:
        raise ValueError("Snapshot not found")

    exp = await get_experiment(db, experiment_id)
    if not exp:
        raise ValueError("Experiment not found")

    data = snapshot.snapshot_data
    exp.name = data["name"]
    exp.description = data.get("description")
    exp.bucket_start = data["bucket_start"]
    exp.bucket_end = data["bucket_end"]

    for group in exp.groups:
        await db.delete(group)
    await db.flush()

    for g_data in data["groups"]:
        group = ExperimentGroup(
            experiment_id=experiment_id,
            name=g_data["name"],
            traffic_percentage=g_data["traffic_percentage"],
            config_json=g_data.get("config_json"),
        )
        db.add(group)

    await log_audit(db, "experiment", experiment_id, "rollback", new_value={"snapshot_id": str(snapshot_id)})
    await db.commit()
    await db.refresh(exp, attribute_names=["groups"])
    return exp


async def list_snapshots(db: AsyncSession, experiment_id: uuid.UUID) -> list[ExperimentSnapshot]:
    result = await db.execute(
        select(ExperimentSnapshot)
        .where(ExperimentSnapshot.experiment_id == experiment_id)
        .order_by(ExperimentSnapshot.created_at.desc())
    )
    return list(result.scalars().all())
