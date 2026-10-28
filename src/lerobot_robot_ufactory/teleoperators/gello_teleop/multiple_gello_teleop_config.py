from dataclasses import dataclass, field

from lerobot.teleoperators import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("uf::multiple_gello_teleop")
@dataclass
class MultipleGelloTeleopConfig(TeleoperatorConfig):
    teleops: dict[str, TeleoperatorConfig] = field(default_factory=dict)

    def __post_init__(self):
        self.id = self.id or "multiple_gello_teleop"
