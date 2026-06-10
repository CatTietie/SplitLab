from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Experiment, ExperimentGroup, Event
from app.schemas.event import EventBatch


async def ingest_events(db: AsyncSession, batch: EventBatch) -> int:
    if not batch.events:
        return 0

    experiment_keys = list({ev.experiment_key for ev in batch.events})
    exp_result = await db.execute(
        select(Experiment).where(Experiment.key.in_(experiment_keys))
    )
    experiments_by_key = {exp.key: exp for exp in exp_result.scalars().all()}

    experiment_ids = [exp.id for exp in experiments_by_key.values()]
    if not experiment_ids:
        return 0

    group_result = await db.execute(
        select(ExperimentGroup).where(ExperimentGroup.experiment_id.in_(experiment_ids))
    )
    groups_by_exp_and_name: dict[tuple, ExperimentGroup] = {}
    for group in group_result.scalars().all():
        groups_by_exp_and_name[(group.experiment_id, group.name)] = group

    now = datetime.now(timezone.utc)
    events_to_insert = []
    for ev in batch.events:
        experiment = experiments_by_key.get(ev.experiment_key)
        if not experiment:
            continue

        group = groups_by_exp_and_name.get((experiment.id, ev.group_name))
        if not group:
            continue

        events_to_insert.append(Event(
            experiment_id=experiment.id,
            group_id=group.id,
            user_id=ev.user_id,
            event_name=ev.event_name,
            metadata_json=ev.metadata,
            event_time=ev.event_time,
            received_at=now,
        ))

    if events_to_insert:
        db.add_all(events_to_insert)
        await db.commit()

    return len(events_to_insert)
