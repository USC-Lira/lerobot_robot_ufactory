"""Configuration checks shared by the GELLO teleop and recording commands."""

import os
import sys
from pathlib import Path


def gello_pairs(cfg):
    """Return (name, follower config, leader config), without creating devices."""
    if cfg.teleop is None:
        return []
    teleop_type = getattr(cfg.teleop, "type", None)
    if teleop_type == "uf::gello_teleop":
        if cfg.robot.type != "uf::robot":
            raise ValueError("A single GELLO requires a single uf::robot.")
        return [("arm", cfg.robot, cfg.teleop)]
    if teleop_type != "uf::multiple_gello_teleop":
        return []
    if cfg.robot.type != "uf::multiple_robot":
        raise ValueError("Multiple GELLOs require uf::multiple_robot.")
    if not cfg.robot.robots or set(cfg.robot.robots) != set(cfg.teleop.teleops):
        raise ValueError("robot.robots and teleop.teleops must have the same nonempty keys.")
    return [(key, robot, cfg.teleop.teleops[key]) for key, robot in cfg.robot.robots.items()]


def validate_gello_config(cfg, *, check_ports=False):
    """Validate mappings; check_ports only inspects paths/permissions, never opens them."""
    pairs = gello_pairs(cfg)
    ports, addresses = set(), set()
    for name, robot, teleop in pairs:
        if robot.type != "uf::robot" or teleop.type != "uf::gello_teleop":
            raise ValueError(f"{name}: expected uf::robot and uf::gello_teleop.")
        if robot.control_space != "joint" or robot.robot_dof != len(teleop.joint_ids):
            raise ValueError(
                f"{name}: joint control and matching robot_dof/joint_ids are required."
            )
        if len(teleop.joint_signs) != robot.robot_dof or any(
            sign not in (-1, 1) for sign in teleop.joint_signs
        ):
            raise ValueError(f"{name}: one joint_sign (+1 or -1) is required per joint.")
        if len(teleop.start_joints) != robot.robot_dof:
            raise ValueError(f"{name}: teleop.start_joints must match robot_dof (degrees).")
        ids = list(teleop.joint_ids)
        if teleop.gripper_id >= 0:
            ids.append(teleop.gripper_id)
        if len(ids) != len(set(ids)):
            raise ValueError(f"{name}: motor IDs must be unique within each GELLO.")
        if robot.gripper_type and teleop.gripper_id < 0:
            raise ValueError(f"{name}: a follower gripper requires a GELLO gripper_id.")
        if robot.start_joints is not None and tuple(robot.start_joints) != tuple(
            teleop.start_joints
        ):
            raise ValueError(
                f"{name}: robot/teleop.start_joints must match, or robot.start_joints is null."
            )
        port = str(Path(teleop.port).expanduser().resolve())
        if port in ports or robot.robot_ip in addresses:
            raise ValueError("Each arm needs a distinct robot_ip and GELLO serial port.")
        ports.add(port)
        addresses.add(robot.robot_ip)
        if check_ports:
            if "REPLACE" in teleop.port or not Path(port).exists():
                raise ValueError(
                    f"{name}: set teleop.port to the connected GELLO's /dev/serial/by-id path."
                )
            if not os.access(port, os.R_OK | os.W_OK):
                raise PermissionError(
                    f"{name}: no read/write permission for {port}; check dialout membership."
                )
    return pairs


def confirm_gello_start(cfg):
    pairs = validate_gello_config(cfg, check_ports=True)
    if not pairs:
        return
    for name, robot, teleop in pairs:
        print(f"{name}: {teleop.port} -> xArm {robot.robot_ip}, gripper_type={robot.gripper_type}")
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Start GELLO control from an interactive terminal with an onsite operator."
        )
    input(
        "Clear the workspace; release GELLO triggers and hold leaders still. "
        "Enter enables the arm(s) and initializes/opens grippers; Ctrl+C cancels: "
    )


def close_devices(*devices):
    """Attempt every cleanup even if another device fails to disconnect."""
    import logging

    for device in devices:
        if device is not None:
            try:
                device.disconnect()
            except Exception:
                logging.warning("Failed to close %s", type(device).__name__, exc_info=True)
