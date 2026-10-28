# LIRA Lab: xArm7 + GELLO

GELLO teleoperation and LeRobot data collection for the lab's two xArm7 arms.

Start with the [setup guide](guides/liralab-xarm-gello.md) for account creation, serial permissions, installation, and hardware configuration. The illustrated version is on [Notion](https://app.notion.com/p/407017f4566081cbaa38e2a6ced8cb8b).

## Configurations

- [Arm 192.168.1.216](config/liralab/xarm7_216_gello.yaml)
- [Arm 192.168.1.239](config/liralab/xarm7_239_gello.yaml)
- [Both arms](config/liralab/dual_xarm7_gello.yaml)

Set the GELLO USB paths and match the tool and camera settings to the current hardware before running.

## Quick reference

After completing setup:

```bash
cd ~/code/lerobot_robot_ufactory
source .venv/bin/activate
CFG=config/liralab/dual_xarm7_gello.yaml
uf-robot-teleop --config_path="$CFG" --check-config
uf-lerobot-record --config_path="$CFG" --check-config
```

Configuration checks do not open hardware.

Teleoperate from a workstation desktop terminal:

```bash
uf-robot-teleop --config_path="$CFG"
```

**Enter** enables the arms and initializes/opens attached grippers. **Space** starts/pauses tracking; **Esc** exits.

Exit teleoperation before recording:

```bash
uf-lerobot-record --config_path="$CFG"
```

**Space** starts, **Right** saves, **Left** discards, **Esc** exits. Add `-r` to append to an existing dataset.

## Validation

CPU installation, camera I/O, and offline tests for recording/resuming synthetic data have passed. Live teleoperation and recording with real hardware still need onsite validation.

## Upstream and license

Based on [xArm-Developer/lerobot_robot_ufactory](https://github.com/xArm-Developer/lerobot_robot_ufactory). Released under [Apache 2.0](LICENSE).
