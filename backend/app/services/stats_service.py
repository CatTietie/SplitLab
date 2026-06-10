import math

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, ExperimentGroup, Experiment
from app.schemas.stats import ExperimentStatsResponse, GroupStatsResponse


async def compute_experiment_stats(
    db: AsyncSession,
    experiment_id: str,
    goal_event: str,
) -> ExperimentStatsResponse:
    groups_result = await db.execute(
        select(ExperimentGroup).where(ExperimentGroup.experiment_id == experiment_id)
    )
    groups = list(groups_result.scalars().all())

    group_stats = []
    for group in groups:
        total_result = await db.execute(
            select(func.count(distinct(Event.user_id)))
            .where(Event.experiment_id == experiment_id, Event.group_id == group.id)
        )
        total_users = total_result.scalar() or 0

        conv_result = await db.execute(
            select(func.count(distinct(Event.user_id)))
            .where(
                Event.experiment_id == experiment_id,
                Event.group_id == group.id,
                Event.event_name == goal_event,
            )
        )
        conversions = conv_result.scalar() or 0

        rate = conversions / total_users if total_users > 0 else 0.0
        ci_half = 1.96 * math.sqrt(rate * (1 - rate) / total_users) if total_users > 0 else 0.0

        group_stats.append(GroupStatsResponse(
            group_name=group.name,
            total_users=total_users,
            conversions=conversions,
            conversion_rate=rate,
            ci_lower=max(0, rate - ci_half),
            ci_upper=min(1, rate + ci_half),
        ))

    z_stat = None
    p_value = None
    is_significant = False

    if len(group_stats) == 2:
        g0, g1 = group_stats[0], group_stats[1]
        if g0.total_users > 0 and g1.total_users > 0:
            p_pool = (g0.conversions + g1.conversions) / (g0.total_users + g1.total_users)
            se = math.sqrt(p_pool * (1 - p_pool) * (1 / g0.total_users + 1 / g1.total_users)) if p_pool > 0 and p_pool < 1 else 0

            if se > 0:
                z_stat = (g1.conversion_rate - g0.conversion_rate) / se
                from scipy.stats import norm
                p_value = 2 * (1 - norm.cdf(abs(z_stat)))
                is_significant = p_value < 0.05

    sample_size = None
    if len(group_stats) >= 2:
        baseline_rate = group_stats[0].conversion_rate
        if baseline_rate > 0:
            mde = max(0.005, baseline_rate * 0.1)
            sample_size = _min_sample_size(baseline_rate, mde)

    return ExperimentStatsResponse(
        experiment_id=experiment_id,
        goal_event=goal_event,
        groups=group_stats,
        z_statistic=z_stat,
        p_value=p_value,
        is_significant=is_significant,
        recommended_sample_size=sample_size,
    )


def _min_sample_size(baseline_rate: float, mde: float, alpha: float = 0.05, power: float = 0.8) -> int:
    from scipy.stats import norm
    z_alpha = norm.ppf(1 - alpha / 2)
    z_beta = norm.ppf(power)
    p1 = baseline_rate
    p2 = baseline_rate + mde
    n = ((z_alpha * math.sqrt(2 * p1 * (1 - p1)) + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) / mde) ** 2
    return math.ceil(n)
