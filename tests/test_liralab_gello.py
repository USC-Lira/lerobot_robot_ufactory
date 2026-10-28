"""Offline regression checks. All network connections and serial opens are blocked."""

import math
import socket
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import serial

from lerobot_robot_ufactory.robots.uf_robot import (
    MultipleUFRobot,
    MultipleUFRobotConfig,
    UFRobot,
    UFRobotConfig,
)
from lerobot_robot_ufactory.scripts import uf_lerobot_record, uf_robot_teleop
from lerobot_robot_ufactory.teleoperators.gello_teleop import (
    GelloTeleop,
    GelloTeleopConfig,
    MultipleGelloTeleop,
    MultipleGelloTeleopConfig,
)
from lerobot_robot_ufactory.utils.gello_setup import (
    confirm_gello_start,
    validate_gello_config,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILES = sorted((ROOT / "config/liralab").glob("*.yaml"))


@pytest.fixture(autouse=True)
def no_hardware(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline tests must never connect to hardware")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(serial.Serial, "open", forbidden)


def config(monkeypatch, path="dual_xarm7_gello.yaml", module=uf_robot_teleop):
    monkeypatch.setattr(sys, "argv", ["check", f"--config_path={ROOT / 'config/liralab' / path}"])
    return module.get_cfg()


@pytest.mark.parametrize("module", [uf_robot_teleop, uf_lerobot_record])
@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.name)
def test_check_config_never_creates_devices(monkeypatch, capsys, module, profile):
    def forbidden(*args, **kwargs):
        raise AssertionError("--check-config must not construct any device")

    monkeypatch.setattr(module, "make_robot_from_config", forbidden)
    monkeypatch.setattr(module, "make_teleoperator_from_config", forbidden)
    monkeypatch.setattr(sys, "argv", ["check", f"--config_path={profile}", "--check-config"])
    module.main()
    assert "Configuration structure OK" in capsys.readouterr().out


def test_both_arm_addresses_and_relative_start(monkeypatch):
    pairs = validate_gello_config(config(monkeypatch))
    assert {robot.robot_ip for _, robot, _ in pairs} == {"192.168.1.216", "192.168.1.239"}
    assert all(robot.start_joints is None for _, robot, _ in pairs)


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.name)
def test_native_factories_resolve_and_match_action_features(monkeypatch, profile):
    cfg = config(monkeypatch, profile.name)
    robot = uf_robot_teleop.make_robot_from_config(cfg.robot)
    teleop = uf_robot_teleop.make_teleoperator_from_config(cfg.teleop)
    assert robot.action_features == teleop.action_features
    assert not robot.is_connected and not teleop.is_connected
    robot.disconnect()
    teleop.disconnect()


def test_rejects_different_pair_keys(monkeypatch):
    cfg = config(monkeypatch)
    cfg.teleop.teleops.pop("arm239")
    with pytest.raises(ValueError, match="same nonempty keys"):
        validate_gello_config(cfg)


@pytest.mark.parametrize("duplicate", ["ip", "port"])
def test_rejects_duplicate_device_mapping(monkeypatch, duplicate):
    cfg = config(monkeypatch)
    if duplicate == "ip":
        cfg.robot.robots["arm239"].robot_ip = cfg.robot.robots["arm216"].robot_ip
    else:
        cfg.teleop.teleops["arm239"].port = cfg.teleop.teleops["arm216"].port
    with pytest.raises(ValueError, match="distinct"):
        validate_gello_config(cfg)


def test_rejects_two_symlinks_to_same_usb_port(monkeypatch, tmp_path):
    cfg = config(monkeypatch)
    target = tmp_path / "ttyUSB0"
    target.touch()
    for name in ["arm216", "arm239"]:
        link = tmp_path / name
        link.symlink_to(target)
        cfg.teleop.teleops[name].port = str(link)
    with pytest.raises(ValueError, match="distinct"):
        validate_gello_config(cfg)


def test_placeholder_ports_block_start_before_confirmation(monkeypatch):
    cfg = config(monkeypatch)
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("too early")))
    with pytest.raises(ValueError, match="set teleop.port"):
        confirm_gello_start(cfg)


@pytest.mark.parametrize("bad_signs", [(1, 1), (1, 1, 1, 1, 1, 1, 0)])
def test_rejects_invalid_joint_signs(monkeypatch, bad_signs):
    cfg = config(monkeypatch, "xarm7_216_gello.yaml")
    cfg.teleop.joint_signs = bad_signs
    with pytest.raises(ValueError, match="joint_sign"):
        validate_gello_config(cfg)


def test_gello_constructor_does_not_open_serial():
    teleop = GelloTeleop(GelloTeleopConfig())
    assert not teleop.is_connected
    teleop.disconnect()  # Cleanup is also safe before connecting.


def test_start_and_resume_rebase_only_joints():
    teleop = GelloTeleop(GelloTeleopConfig())
    raw = np.array([0.1] * 7 + [0.75])
    teleop.gello_agent = SimpleNamespace(act=lambda obs: raw.copy())
    teleop._is_connected = True
    obs = {f"J{i}.pos": 0.5 for i in range(1, 8)}
    teleop.set_teleop_enabled(True, obs)
    assert teleop.get_action()["J1.pos"] == pytest.approx(0.5)
    assert teleop.get_action()["gripper.pos"] == pytest.approx(0.75)
    teleop.set_teleop_enabled(False)
    raw[:7] += 0.4  # Operator moved the leader while paused.
    teleop.set_teleop_enabled(True, obs)
    assert teleop.get_action()["J1.pos"] == pytest.approx(0.5)
    raw[0] += 0.1
    assert teleop.get_action()["J1.pos"] == pytest.approx(0.6)


def test_no_gripper_feature_without_trigger():
    teleop = GelloTeleop(GelloTeleopConfig(gripper_id=-1))
    assert "gripper.pos" not in teleop.action_features


class FakeLeader:
    def __init__(self, cfg):
        self.is_connected = False
        self.is_calibrated = True
        self.action_features = {"J1.pos": float, "gripper.pos": float}
        self.feedback_features = self.action_features
        self.obs = None
        self.closed = False
        self.fail = cfg.id == "fail"

    def connect(self, calibrate=True):
        if self.fail:
            raise RuntimeError("second GELLO failed")
        self.is_connected = True

    def disconnect(self):
        self.closed = True
        self.is_connected = False

    def set_teleop_enabled(self, enabled, obs=None):
        self.obs = obs

    def get_action(self):
        return {"J1.pos": 0.3, "gripper.pos": 0.8}


def multiple_leaders(monkeypatch, fail=False):
    monkeypatch.setattr(
        "lerobot_robot_ufactory.teleoperators.gello_teleop.multiple_gello_teleop.GelloTeleop",
        FakeLeader,
    )
    return MultipleGelloTeleop(
        MultipleGelloTeleopConfig(
            teleops={
                "arm216": GelloTeleopConfig(id="first"),
                "arm239": GelloTeleopConfig(id="fail" if fail else "second"),
            }
        )
    )


def test_dual_actions_are_namespaced_and_observations_are_separated(monkeypatch):
    teleop = multiple_leaders(monkeypatch)
    teleop.connect()
    assert set(teleop.get_action()) == {
        "arm216.J1.pos",
        "arm216.gripper.pos",
        "arm239.J1.pos",
        "arm239.gripper.pos",
    }
    assert set(teleop.action_features) == set(teleop.get_action())
    teleop.set_teleop_enabled(True, {"arm216.J1.pos": 0.1, "arm239.J1.pos": 0.2})
    assert teleop.teleops["arm216"].obs == {"J1.pos": 0.1}
    assert teleop.teleops["arm239"].obs == {"J1.pos": 0.2}
    teleop.disconnect()


def test_second_leader_failure_closes_first(monkeypatch):
    teleop = multiple_leaders(monkeypatch, fail=True)
    with pytest.raises(RuntimeError, match="second GELLO failed"):
        teleop.connect()
    assert all(child.closed for child in teleop.teleops.values())


@pytest.mark.parametrize("asynchronous", [False, True])
def test_second_arm_failure_stops_every_arm(monkeypatch, asynchronous):
    class FakeArm:
        cameras = {}

        def __init__(self, cfg, prefix):
            self.fail = prefix == "arm239"
            self.is_connected = False
            self.closed = False

        def connect(self, calibrate=True):
            if self.fail:
                raise RuntimeError("second arm failed")
            self.is_connected = True

        def disconnect(self):
            self.closed = True
            self.is_connected = False

    monkeypatch.setattr("lerobot_robot_ufactory.robots.uf_robot.multiple_uf_robot.UFRobot", FakeArm)
    robot = MultipleUFRobot(
        MultipleUFRobotConfig(
            async_connect=asynchronous,
            robots={"arm216": UFRobotConfig(), "arm239": UFRobotConfig()},
        )
    )
    with pytest.raises(RuntimeError, match="second arm failed"):
        robot.connect()
    assert all(child.closed for child in robot.robots.values())


def test_connect_failure_keeps_original_error_and_closes_leader(monkeypatch):
    robot = Mock()
    robot.connect.side_effect = RuntimeError("gripper C19")
    robot.disconnect.side_effect = RuntimeError("cleanup also failed")
    teleop = Mock()
    monkeypatch.setattr(uf_robot_teleop, "make_robot_from_config", lambda cfg: robot)
    monkeypatch.setattr(uf_robot_teleop, "make_teleoperator_from_config", lambda cfg: teleop)
    cfg = config(monkeypatch, "xarm7_239_gello.yaml")
    with pytest.raises(RuntimeError, match="gripper C19"):
        uf_robot_teleop.teleop_loop(cfg)
    teleop.disconnect.assert_called_once()


def test_rejects_fake_gello_fallback(monkeypatch):
    driver = Mock(_is_fake=True)
    agent = SimpleNamespace(_robot=SimpleNamespace(_driver=driver))
    monkeypatch.setattr("gello.agents.gello_agent.GelloAgent", lambda **kwargs: agent)
    teleop = GelloTeleop(GelloTeleopConfig())
    monkeypatch.setattr(teleop, "_make_dynamixel_config", lambda: None)
    with pytest.raises(ConnectionError, match="fake driver"):
        teleop.connect()
    driver.close.assert_called_once()
    assert not teleop.is_connected


def test_no_motor_power_times_out_and_releases_serial(monkeypatch):
    driver = Mock(_joint_angles=None)
    factory = Mock(return_value=driver)
    monkeypatch.setattr("gello.dynamixel.driver.DynamixelDriver", factory)
    clock = iter([0.0, 6.0])
    monkeypatch.setattr(
        "lerobot_robot_ufactory.teleoperators.gello_teleop.gello_teleop.time.monotonic",
        lambda: next(clock),
    )
    teleop = GelloTeleop(GelloTeleopConfig())
    with pytest.raises(TimeoutError, match="external power"):
        teleop._make_dynamixel_config()
    assert factory.call_args.kwargs["use_fake_fallback"] is False
    driver.close.assert_called_once()


@pytest.mark.parametrize("start_joints", [None, (0, 0, 0, 0, 0, 0, 0)])
def test_no_homing_by_default_and_configured_homing_speed(monkeypatch, start_joints):
    robot = UFRobot(
        UFRobotConfig(robot_dof=7, gripper_type=0, start_joints=start_joints, max_joint_velocity=10)
    )
    robot.real_arm = Mock()
    robot.real_arm.get_err_warn_code.return_value = (0, [0, 0])
    robot.real_arm.set_servo_angle.return_value = 0
    monkeypatch.setattr(
        "lerobot_robot_ufactory.robots.uf_robot.uf_robot.time.sleep", lambda s: None
    )
    robot.configure()
    if start_joints is None:
        robot.real_arm.set_servo_angle.assert_not_called()
    else:
        assert robot.real_arm.set_servo_angle.call_args.kwargs["speed"] == pytest.approx(
            math.radians(10)
        )


@pytest.mark.parametrize("command_count", [0, 19, 20])
@pytest.mark.parametrize("speed_degrees", [10, 90])
def test_tracking_never_exceeds_configured_joint_speed(command_count, speed_degrees):
    robot = UFRobot(
        UFRobotConfig(
            robot_dof=7,
            gripper_type=0,
            start_joints=None,
            max_joint_velocity=speed_degrees,
        )
    )
    robot._is_connected = True
    robot._cmd_cnt = command_count
    robot.real_arm = Mock(error_code=0, mode=0 if command_count == 0 else 6)
    robot.send_action({f"J{i}.pos": 0.0 for i in range(1, 8)})
    sent_speed = robot.real_arm.set_servo_angle.call_args.kwargs["speed"]
    assert 0 < sent_speed <= math.radians(speed_degrees)
    robot.disconnect()


def test_dual_record_and_resume_with_simulated_hardware(monkeypatch, tmp_path):
    """Exercise the real recording/encoding path with synthetic leader/camera data."""
    from lerobot_robot_ufactory.utils.keyboard import KeyboardState

    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    cfg = config(monkeypatch, module=uf_lerobot_record)
    cfg.dataset.root = tmp_path / "recording"
    cfg.dataset.fps = 10
    cfg.dataset.episode_time_s = 0.15
    cfg.dataset.num_image_writer_processes = 0
    cfg.dataset.num_image_writer_threads_per_camera = 1
    cfg.dataset.encoder_threads = 1
    cfg.dataset.rgb_encoder.vcodec = "libsvtav1"
    cfg.display_data = False
    original_repo_id = cfg.dataset.repo_id

    class SimDriver:
        _is_fake = False

        def __init__(self, ids, **kwargs):
            self._joint_angles = np.zeros(len(ids))

        def get_joints(self):
            return self._joint_angles.copy()

        def set_torque_mode(self, enabled):
            pass

        def close(self):
            pass

    monkeypatch.setattr("gello.dynamixel.driver.DynamixelDriver", SimDriver)
    leader = MultipleGelloTeleop(cfg.teleop)

    class SimRobot:
        name = "simulated_dual_xarm7"
        robot_type = name
        cameras = {"front": object(), "overhead": object()}
        action_features = leader.action_features
        observation_features = {
            **action_features,
            "arm216.front": (64, 64, 3),
            "arm216.overhead": (64, 64, 3),
        }
        is_connected = False
        sent_count = 0

        def connect(self):
            self.is_connected = True

        def configure(self):
            pass

        def get_observation(self):
            return {
                **dict.fromkeys(self.action_features, 0.1),
                "arm216.front": np.full((64, 64, 3), 64, dtype=np.uint8),
                "arm216.overhead": np.full((64, 64, 3), 128, dtype=np.uint8),
            }

        def send_action(self, action):
            assert set(action) == set(self.action_features)
            self.sent_count += 1
            return action

        def disconnect(self):
            self.is_connected = False

    robot = SimRobot()
    monkeypatch.setattr(uf_lerobot_record, "make_robot_from_config", lambda cfg: robot)
    monkeypatch.setattr(uf_lerobot_record, "make_teleoperator_from_config", lambda cfg: leader)

    def keyboard_ready(kb_state, **kwargs):
        assert isinstance(kb_state, KeyboardState)
        kb_state.set_event("recorded", True)
        return Mock(), kb_state

    monkeypatch.setattr(uf_lerobot_record, "register_keyboard_controls", keyboard_ready)
    first = uf_lerobot_record.record(cfg)
    assert first.num_episodes == 1
    assert first.num_frames >= 1
    assert cfg.dataset.repo_id == original_repo_id
    cfg.resume = True
    resumed = uf_lerobot_record.record(cfg)
    assert resumed.num_episodes == 2
    assert resumed.num_frames > first.num_frames
    assert robot.sent_count >= 2
    assert not robot.is_connected and not leader.is_connected
    assert len(list(cfg.dataset.root.glob("videos/**/*.mp4"))) >= 2
