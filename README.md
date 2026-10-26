# tractor_bringup

Single entry point for the Vario700 tractor recording rig (dataset v2).
Owns the launch composition, the TF policy, and the recording topic set —
no driver code.

## Usage

```bash
# everything (what the boot service runs)
ros2 launch tractor_bringup tractor_bringup.launch.py

# bench work: switch individual sensors off
ros2 launch tractor_bringup tractor_bringup.launch.py zed:=false novatel:=false

# TF tree only (e.g. on a desktop, for bag playback)
ros2 launch tractor_bringup tf.launch.py
```

Arguments: `tf`, `arkcams`, `ouster`, `zed`, `blickfeld`, `novatel`
(default `true`), `rviz` (default `false`), plus `camera_model`,
`ouster_hostname`, `oem7_ip_addr`, and `zed_params_override` (ZED wrapper
parameter file, e.g. `config/zed_no_depth.yaml` to switch depth off).

## TF policy

`tf.launch.py` (the `vario700_sensorrig` URDF via `robot_state_publisher`,
plus one additive identity `zed_camera_center -> zed_camera_link`) is the
**only** source of `/tf_static`. Every driver runs with its internal TF
publishing disabled — the ZED wrapper's own URDF points the
`zed_camera_center <-> zed_left_camera_frame` edge the other way and makes
the graph cyclic. See `system/MIGRATION_v1_v2.md`, section "TF tree (v2)".

## Recording config

`config/record_topics.txt` and `config/mcap_writer_options.yml` are read
by `system/scripts/record.sh` from the install space — rebuild (or use
`--symlink-install`) after editing.
