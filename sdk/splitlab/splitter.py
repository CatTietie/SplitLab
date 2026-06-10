import hashlib
from splitlab.models import SDKConfig, ExperimentConfig, LayerConfig


def get_bucket(user_id: str, salt: str) -> int:
    raw = f"{user_id}{salt}".encode("utf-8")
    digest = hashlib.md5(raw).hexdigest()
    return int(digest[:8], 16) % 10000


def get_variant(user_id: str, experiment_key: str, config: SDKConfig) -> str | None:
    experiment, layer = config.get_experiment(experiment_key)
    if not experiment or not layer:
        return None
    if experiment.status not in ("running", "full_rollout"):
        return None

    if user_id in experiment.whitelist:
        return experiment.whitelist[user_id]

    bucket = get_bucket(user_id, layer.salt)

    if not (experiment.bucket_start <= bucket <= experiment.bucket_end):
        return None

    range_size = experiment.bucket_end - experiment.bucket_start + 1
    relative_bucket = bucket - experiment.bucket_start

    cumulative = 0
    for group in experiment.groups:
        group_size = int(range_size * group.traffic_percentage / 100)
        if relative_bucket < cumulative + group_size:
            return group.name
        cumulative += group_size

    return experiment.groups[-1].name if experiment.groups else None
