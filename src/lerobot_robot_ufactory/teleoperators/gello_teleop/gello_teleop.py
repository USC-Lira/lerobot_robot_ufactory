#!/usr/bin/env python
import logging
import time
import math
import numpy as np
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from ..base_teleop import UFBaseTeleop
from .gello_teleop_config import GelloTeleopConfig


logger = logging.getLogger(__name__)

class GelloTeleop(UFBaseTeleop):
    """
    GELLO for xArm tele-op, ref: https://wuphilipp.github.io/gello_site/
    """

    config_class = GelloTeleopConfig
    name = "Gello Teleop For xArm"

    def __init__(self, config: GelloTeleopConfig):
        super().__init__(config)
        self.config = config
        self._is_connected = False
        self._is_calibrated = True # CHECK!!
        self.dof = len(config.joint_ids)
        self._joint_shift = np.zeros(self.dof)
        self.gello_agent = None

    @staticmethod
    def _wait_for_joints(driver):
        deadline = time.monotonic() + 5
        while driver._joint_angles is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("No GELLO motor replies: check external power and motor cables.")
            time.sleep(0.01)

    def _make_dynamixel_config(self):
        from gello.dynamixel.driver import DynamixelDriver
        from gello.agents.gello_agent import DynamixelRobotConfig

        # auto get joint offset from gello
        joint_ids = []
        joint_ids.extend(self.config.joint_ids)
        if self.config.gripper_id >= 0:
            joint_ids.append(self.config.gripper_id)
        driver = DynamixelDriver(
            joint_ids, port=self.config.port, baudrate=57600,
            max_retries=1, use_fake_fallback=False,
        )
        try:
            self._wait_for_joints(driver)
            for _ in range(10):
                driver.get_joints()  # warmup
            curr_joints = driver.get_joints()
        finally:
            driver.close()
        joint_offsets = []
        start_joints = list(map(math.radians, self.config.start_joints))
        for i in range(len(start_joints)):
            offset = curr_joints[i] - start_joints[i] / self.config.joint_signs[i]
            joint_offsets.append(offset)
        if self.config.gripper_id >= 0:
            gripper_config = [self.config.gripper_id, np.rad2deg(curr_joints[-1]) - 0.2, np.rad2deg(curr_joints[-1]) - 42]
        else:
            gripper_config = None

        param_dict = {
                "joint_ids": self.config.joint_ids,
                "joint_signs": self.config.joint_signs,
                "joint_offsets": joint_offsets,
                "gripper_config": gripper_config
        }
        dynamixel_config = DynamixelRobotConfig(**param_dict)

        if self.config.torque_joint_ids:
            driver = DynamixelDriver(self.config.torque_joint_ids, port=self.config.port, baudrate=57600)
            driver.set_torque_mode(True)
            driver.close()
        return dynamixel_config

    @property
    def action_features(self) -> dict:
        # Add one more dof for gripper
        # act_ft = {
        #     "joint_position": {
        #     "dtype": "float",
        #     "shape": (self.dof+1,)
        #     }
        # }
        act_ft = {f"J{i+1}.pos": float for i in range(self.dof)}
        if self.config.gripper_id >= 0:
            act_ft["gripper.pos"] = float
        return act_ft

    @property
    def feedback_features(self) -> dict:
        # fbk_ft = {
        #     "joint_position": {
        #     "dtype": "float",
        #     "shape": (self.dof+1,)
        #     }
        # }
        fbk_ft = dict(self.action_features)
        return fbk_ft

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    def connect(self, calibrate: bool = True) -> None:
        if self._is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")
        from gello.agents.gello_agent import GelloAgent

        try:
            config = self._make_dynamixel_config()
            self.gello_agent = GelloAgent(port=self.config.port, dynamixel_config=config)
            if getattr(self.gello_agent._robot._driver, "_is_fake", False):
                raise ConnectionError("GELLO fell back to a fake driver; check the serial connection.")
            self._wait_for_joints(self.gello_agent._robot._driver)
            if not self._is_calibrated and calibrate:
                self.calibrate()
            self.configure()
            self._is_connected = True
            super().connect(calibrate)
            logger.info(f"{self} connected.")
        except BaseException:
            self.disconnect()
            raise

    @property
    def is_calibrated(self) -> bool:
        return self._is_calibrated

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        # TODO: Go to sync position slowly? Can not 
        pass

    def set_teleop_enabled(self, enabled: bool, obs=None):
        # Rebase at every start/resume, so moving a paused leader cannot cause a jump.
        if enabled and obs is not None:
            current = self.get_action()
            for i in range(self.dof):
                key = f"J{i+1}.pos"
                self._joint_shift[i] += float(obs[key]) - current[key]

    def get_action(self) -> dict[str, np.ndarray]:
        if not self._is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        start = time.perf_counter()
        fake_obs = dict({"joint_state": np.array([0.0]*(self.dof+1))}) # for agent.act() argument, actually no use
        action_array = self.gello_agent.act(fake_obs) # current gello joint pos as np.ndarray
        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read action: {dt_ms:.1f}ms")

        action = {}
        for i in range(self.dof):
            action.update({f"J{i+1}.pos": float(action_array[i] + self._joint_shift[i])})
        if self.config.gripper_id >= 0:
            action.update({"gripper.pos": float(action_array[self.dof])})
        return action

    def send_feedback(self, feedback: dict[str, float]) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        self._is_connected = False
        if hasattr(self, "gello_agent") and self.gello_agent is not None:
            try:
                self.gello_agent._robot._driver.close()
            except Exception:
                logger.warning("Failed to close GelloAgent", exc_info=True)
            self.gello_agent = None
        super().disconnect()
        logger.info(f"{self} disconnected.")
