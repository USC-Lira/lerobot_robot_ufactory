# LIRA Lab: xArm7 + GELLO

Start with one arm. After it works, repeat for the other arm before trying both together. Installation, GELLO joint reads, and camera I/O were tested previously; live following and recording still need onsite validation.

## 1. SSH

Replace `YOUR_USERNAME` with your workstation account (`peiqi` for the current setup):

```bash
ssh -t YOUR_USERNAME@10.137.31.180
```

Run the remaining commands on the workstation. Use a desktop terminal in your own account for teleoperation and recording, so keyboard controls work.

## 2. Prepare the environment

**Already installed (including peiqi):**

```bash
cd ~/code/lerobot_robot_ufactory
git pull --ff-only origin main
source .venv/bin/activate
```

**First installation only:** skip this block if the existing environment works.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
mkdir -p ~/code
cd ~/code
git clone https://github.com/USC-Lira/lerobot_robot_ufactory.git
cd lerobot_robot_ufactory
uv venv --python 3.12
source .venv/bin/activate
uv pip install --torch-backend cpu -e ".[gello]" "lerobot[intelrealsense]==0.6.1"
uv pip check
```

If the repository already exists but `.venv` is missing, run the installation block starting at `uv venv` from inside the repository.

## 3. Prepare one arm

Switch on its control box. Open UFACTORY Studio on the workstation desktop: [arm .216](http://192.168.1.216:18333) or [arm .239](http://192.168.1.239:18333). Confirm the IP of the physical arm you intend to use and resolve any controller errors before continuing.

Connect that arm's GELLO USB cable and switch on GELLO's external power. USB alone does not power the motors. Keep the emergency stop accessible and clear the workspace.

## 4. Configure

This example uses `.239`. For `.216`, replace `239` with `216` in both filenames:

```bash
CFG=config/liralab/xarm7_239.local.yaml
test -f "$CFG" || cp config/liralab/xarm7_239_gello.yaml "$CFG"
ls /dev/serial/by-id/*
nano "$CFG"
```

The USB listing should show a full `/dev/serial/by-id/...` path. Replace `teleop.port` with the path for this GELLO; do not use changing `/dev/ttyUSB0` numbering. If no path appears, check the USB connection before continuing. Save in nano with **Ctrl+O**, **Enter**, then exit with **Ctrl+X**.

Match `gripper_type` to the currently mounted tool ([supported values](../src/lerobot_robot_ufactory/robots/uf_robot/uf_robot.py)). Keep `robot.start_joints: null` to avoid startup homing. The supplied camera settings are for the previously tested front and overhead cameras; update their serials if cameras change.

For the first test, keep the supplied 15-second, one-episode dataset settings. If `dataset.root` already exists, choose a new root or use `-r` when recording to append. Set `dataset.single_task` to describe the task when collecting actual data.

```bash
uf-robot-teleop --config_path="$CFG" --check-config
uf-lerobot-record --config_path="$CFG" --check-config
```

Both should print **Configuration structure OK**. These checks parse configuration; they do not test USB permissions, motor power, cameras, or robot connectivity.

## 5. Test following

In a workstation desktop terminal, activate the environment and set the same configuration again:

```bash
cd ~/code/lerobot_robot_ufactory
source .venv/bin/activate
CFG=config/liralab/xarm7_239.local.yaml
uf-robot-teleop --config_path="$CFG"
```

1. Check the printed GELLO-to-arm mapping. Release the trigger and hold GELLO still.
2. **Enter** enables the arm and initializes/opens its gripper. Wait for the keyboard-control prompt.
3. **Space** starts following. Slowly move one GELLO joint a small amount, then test the others and the trigger. Confirm the intended arm follows in the intended directions.
4. **Space** pauses; **Esc** stops and exits. If movement is unexpected, stop and correct the configuration before collecting data.

If startup reports `Permission denied`, an administrator must grant `dialout` access; log out and back in afterward. If motors do not reply, check GELLO's external power. If initialization reports a gripper error, verify the current tool and its configuration before retrying.

## 6. Record and replay

Exit teleoperation first. In the same desktop terminal:

```bash
uf-lerobot-record --config_path="$CFG"
```

**Enter** initializes hardware. **Space** starts the episode. The test ends after 15 seconds; **Right** saves early, **Left** discards, and **Esc** exits without saving the current episode. Wait for **save finish** before closing. To append to the same dataset:

```bash
uf-lerobot-record -r --config_path="$CFG"
```

For the default `.239` test dataset, replay the first front-camera video; **q** closes the player:

```bash
SDL_RENDER_DRIVER=software ffplay -an -loop 0 \
  ~/data/xarm7_239_smoke/videos/observation.images.front/chunk-000/file-000.mp4
```

Replace `front` with `overhead` to check the other view. Use your configured `dataset.root` if you changed it (`~/data/xarm7_216_smoke` for the `.216` template). Confirm both views show the recorded movement.

## Both arms (after single-arm tests)

Connect and power both GELLOs. Identify two different USB paths and confirm each physical pairing.

```bash
CFG=config/liralab/dual_xarm7.local.yaml
test -f "$CFG" || cp config/liralab/dual_xarm7_gello.yaml "$CFG"
nano "$CFG"
uf-robot-teleop --config_path="$CFG" --check-config
uf-lerobot-record --config_path="$CFG" --check-config
```

Set both ports, then use the same teleoperation and recording commands above. Shared cameras are opened once. The default replay root is `~/data/dual_xarm7_smoke`; image directories are `observation.images.arm216.front` and `observation.images.arm216.overhead`.

## New accounts only (administrator)

Skip account creation if your account already exists. An existing sudo user runs these on the workstation for a new account:

```bash
sudo adduser YOUR_USERNAME
sudo usermod -aG dialout YOUR_USERNAME
```

For an existing account that lacks serial access, run only the `usermod` command. Log out and back in after group changes. Normal operation does not require sudo.
