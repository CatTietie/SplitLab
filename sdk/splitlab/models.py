from dataclasses import dataclass, field


@dataclass
class GroupConfig:
    id: str
    name: str
    traffic_percentage: int
    config_json: dict | None = None


@dataclass
class ExperimentConfig:
    id: str
    key: str
    status: str
    bucket_start: int
    bucket_end: int
    groups: list[GroupConfig] = field(default_factory=list)
    whitelist: dict[str, str] = field(default_factory=dict)


@dataclass
class LayerConfig:
    id: str
    name: str
    salt: str
    experiments: list[ExperimentConfig] = field(default_factory=list)


@dataclass
class SDKConfig:
    layers: list[LayerConfig] = field(default_factory=list)
    version: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "SDKConfig":
        layers = []
        for ld in data.get("layers", []):
            experiments = []
            for ed in ld.get("experiments", []):
                groups = [GroupConfig(**g) for g in ed.get("groups", [])]
                experiments.append(ExperimentConfig(
                    id=ed["id"],
                    key=ed["key"],
                    status=ed["status"],
                    bucket_start=ed["bucket_start"],
                    bucket_end=ed["bucket_end"],
                    groups=groups,
                    whitelist=ed.get("whitelist", {}),
                ))
            layers.append(LayerConfig(
                id=ld["id"],
                name=ld["name"],
                salt=ld["salt"],
                experiments=experiments,
            ))
        return cls(layers=layers, version=data.get("version", ""))

    def get_experiment(self, key: str) -> tuple[ExperimentConfig | None, LayerConfig | None]:
        for layer in self.layers:
            for exp in layer.experiments:
                if exp.key == key:
                    return exp, layer
        return None, None
