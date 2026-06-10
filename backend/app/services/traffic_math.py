from app.models import ExperimentGroup


def compute_effective_traffic(
    rollout_steps: list[dict] | None,
    current_step_index: int | None,
    groups: list[ExperimentGroup],
) -> list[tuple[ExperimentGroup, int]]:
    if current_step_index is None or not rollout_steps:
        return [(g, g.traffic_percentage) for g in groups]

    step = rollout_steps[current_step_index]
    target_pct = step["traffic_percentage"]

    control_group = next((g for g in groups if g.name == "control"), None)
    if control_group is None:
        control_group = groups[0]

    treatment_groups = [g for g in groups if g.id != control_group.id]

    if not treatment_groups:
        return [(g, g.traffic_percentage) for g in groups]

    original_treatment_total = sum(g.traffic_percentage for g in treatment_groups)

    result = []
    treatment_allocated = 0
    for i, tg in enumerate(treatment_groups):
        if original_treatment_total > 0:
            share = tg.traffic_percentage / original_treatment_total
        else:
            share = 1.0 / len(treatment_groups)

        if i == len(treatment_groups) - 1:
            allocated = target_pct - treatment_allocated
        else:
            allocated = round(target_pct * share)
        treatment_allocated += allocated
        result.append((tg, allocated))

    control_pct = 100 - target_pct
    return [(control_group, control_pct)] + result
