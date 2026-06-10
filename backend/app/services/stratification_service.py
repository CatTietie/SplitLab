from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, ExperimentGroup
from app.models.user_attribute import UserAttribute
from app.schemas.targeting import (
    StratificationBalanceResponse,
    DimensionBalance,
    DimensionGroupDistribution,
)

BIAS_THRESHOLD = 0.03


async def compute_stratification_balance(
    db: AsyncSession, experiment_id: str, dimensions: list[str]
) -> StratificationBalanceResponse:
    groups_result = await db.execute(
        select(ExperimentGroup).where(ExperimentGroup.experiment_id == experiment_id)
    )
    groups = {str(g.id): g.name for g in groups_result.scalars().all()}

    dimension_balances = []
    for dimension in dimensions:
        stmt = (
            select(
                Event.group_id,
                UserAttribute.attribute_value,
                func.count(func.distinct(Event.user_id)).label("user_count"),
            )
            .join(UserAttribute, Event.user_id == UserAttribute.user_id)
            .where(
                Event.experiment_id == experiment_id,
                UserAttribute.attribute_key == dimension,
            )
            .group_by(Event.group_id, UserAttribute.attribute_value)
        )
        result = await db.execute(stmt)
        rows = result.all()

        distributions = []
        group_totals: dict[str, int] = {}
        for group_id, attr_value, count in rows:
            gid = str(group_id)
            group_totals[gid] = group_totals.get(gid, 0) + count
            distributions.append((gid, attr_value, count))

        output_distributions = []
        max_bias = 0.0

        attr_values = set(d[1] for d in distributions)
        for attr_value in attr_values:
            proportions = []
            for gid in groups:
                count = next(
                    (c for g, a, c in distributions if g == gid and a == attr_value), 0
                )
                total = group_totals.get(gid, 0)
                proportion = count / total if total > 0 else 0.0
                proportions.append(proportion)
                output_distributions.append(DimensionGroupDistribution(
                    group_name=groups.get(gid, gid),
                    attribute_value=attr_value,
                    count=count,
                    proportion=round(proportion, 4),
                ))

            if len(proportions) >= 2:
                bias = max(proportions) - min(proportions)
                max_bias = max(max_bias, bias)

        dimension_balances.append(DimensionBalance(
            dimension=dimension,
            distributions=output_distributions,
            max_bias=round(max_bias, 4),
            warning=max_bias > BIAS_THRESHOLD,
        ))

    return StratificationBalanceResponse(dimensions=dimension_balances)
