from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from ..base_teleop import UFBaseTeleop
from .gello_teleop import GelloTeleop
from .multiple_gello_teleop_config import MultipleGelloTeleopConfig


class MultipleGelloTeleop(UFBaseTeleop):
    config_class = MultipleGelloTeleopConfig
    name = "Multiple GELLO Teleop For xArm"

    def __init__(self, config: MultipleGelloTeleopConfig):
        super().__init__(config)
        if not config.teleops:
            raise ValueError("At least one GELLO is required.")
        self.teleops = {key: GelloTeleop(cfg) for key, cfg in config.teleops.items()}

    @property
    def action_features(self):
        return {
            f"{key}.{name}": value
            for key, teleop in self.teleops.items()
            for name, value in teleop.action_features.items()
        }

    @property
    def feedback_features(self):
        return {
            f"{key}.{name}": value
            for key, teleop in self.teleops.items()
            for name, value in teleop.feedback_features.items()
        }

    @property
    def is_connected(self):
        return all(teleop.is_connected for teleop in self.teleops.values())

    @property
    def is_calibrated(self):
        return all(teleop.is_calibrated for teleop in self.teleops.values())

    def connect(self, calibrate=True):
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")
        try:
            for teleop in self.teleops.values():
                teleop.connect(calibrate=calibrate)
            super().connect(calibrate)
        except BaseException:
            self.disconnect()
            raise

    def calibrate(self):
        for teleop in self.teleops.values():
            teleop.calibrate()

    def configure(self):
        for teleop in self.teleops.values():
            teleop.configure()

    def set_teleop_enabled(self, enabled, obs=None):
        for key, teleop in self.teleops.items():
            prefix = f"{key}."
            child_obs = (
                {
                    name.removeprefix(prefix): value
                    for name, value in obs.items()
                    if name.startswith(prefix)
                }
                if obs is not None
                else None
            )
            teleop.set_teleop_enabled(enabled, child_obs)

    def get_action(self):
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        return {
            f"{key}.{name}": value
            for key, teleop in self.teleops.items()
            for name, value in teleop.get_action().items()
        }

    def send_feedback(self, feedback):
        raise NotImplementedError

    def disconnect(self):
        from lerobot_robot_ufactory.utils.gello_setup import close_devices

        close_devices(*self.teleops.values())
        super().disconnect()
