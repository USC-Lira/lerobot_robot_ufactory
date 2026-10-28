# LIRA Lab: xArm7 + GELLO

## Create the account (administrator)

An existing sudo user runs these on the workstation. Replace `YOUR_USERNAME` with the new username:

```bash
sudo adduser YOUR_USERNAME
sudo usermod -aG dialout YOUR_USERNAME
```

Log into the new account after the group is assigned. If it was already logged in, log out and back in.

## Connect and install

```bash
ssh -t YOUR_USERNAME@10.137.31.180
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
mkdir -p ~/code
cd ~/code
git clone https://github.com/USC-Lira/lerobot_robot_ufactory.git
cd lerobot_robot_ufactory
uv venv --python 3.12
source .venv/bin/activate
uv pip install --torch-backend cpu -e ".[gello]" "lerobot[intelrealsense]==0.6.1"
```

For each new terminal, run `cd ~/code/lerobot_robot_ufactory` and `source .venv/bin/activate`.

## Choose and configure

- Arm `.216`: `config/liralab/xarm7_216_gello.yaml`
- Arm `.239`: `config/liralab/xarm7_239_gello.yaml`
- Both arms: `config/liralab/dual_xarm7_gello.yaml`

```bash
ls -l /dev/serial/by-id/
CFG=config/liralab/dual_xarm7_gello.yaml
nano "$CFG"
```

Replace each `REPLACE_GELLO_*` path with the corresponding leader's full USB path. Identify the physical pairing onsite; do not assign leaders by `/dev/ttyUSB0` numbering. Known adapter serial: `FT8ISRWA`. The second GELLO is currently unplugged.

Set `gripper_type` for the tool currently mounted on each arm, and verify each joint direction (`joint_signs`). Keep `robot.start_joints: null`: the arm stays at its current pose during initialization; Space aligns the leader to that pose. The configured joint speed is 10°/s. Initialization can still open attached grippers.

```bash
uf-robot-teleop --config_path="$CFG" --check-config
uf-lerobot-record --config_path="$CFG" --check-config
```

These checks do not open any hardware or verify physical pairing.

## Operate onsite

Power both required GELLOs, release their triggers, and hold them still. Clear the workspace and keep the emergency stop accessible. Use a workstation desktop terminal for keyboard controls.

```bash
uf-robot-teleop --config_path="$CFG"
```

Enter enables the selected arms and initializes/opens grippers. **Space** starts/pauses tracking; **Esc** stops and exits. Test one joint at a time before collecting data. Exit teleoperation first.

```bash
uf-lerobot-record --config_path="$CFG"
```

Recording: **Space** starts, **Right** saves, **Left** discards, **Esc** exits. Wait for saving to finish. Change `dataset.root` for a new dataset; add `-r` to append to the existing one.

The profiles use D455 `035622251296` and D415 `217222067304` at 640×480/30 fps. Dual recording opens each shared camera once.

## Validation status

GELLO `FT8ISRWA` joint reads and both cameras were tested previously. Offline tests saved and resumed a two-camera synthetic dataset. Live arm following, dual GELLO control, and recording with real hardware still need onsite validation. The last check found `.216` unreachable and `.239` returning gripper communication error C19. Resolve these before testing that configuration.
