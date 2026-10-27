# Tractor Orin — Operations Runbook

How to run the Vario 700 sensor rig computer ("tractor Jetson") in its three
operating modes, what each systemd unit does, what is configured/disabled,
and how the repositories fit together. Written for colleagues who have to take
over without prior context.

State: 2026-10-26 (demo week). Branch `feature/demo` of `tractor_bringup`.

---

## 0. Quick reference

| I want to … | Command (on the tractor Jetson, or prefix with `ssh user@<ip>`) |
|---|---|
| see what is running | `tractor-mode status` |
| run the **demo** (perception + Foxglove) | `sudo tractor-mode demo` |
| **record datasets** (MCAP to the 8 TB SSD) | `sudo tractor-mode record` |
| record a **calibration** (.db3) | `sudo tractor-mode calib`, then `calib-record start <name>` … `calib-record stop` |
| stop everything | `sudo tractor-mode off` |
| watch the demo | Foxglove → `ws://192.168.26.4:8765`, layout `perception_live_layout.json` |
| driver logs | `journalctl -u ros2-publishers-boot -f` |
| perception logs | `docker logs -f --tail 100 perception` |

The mode is **persistent**: after a reboot the Jetson comes up in the last
mode set with `tractor-mode`.

---

## 1. Access

| What | Value |
|---|---|
| Hardware | NVIDIA Jetson AGX Orin Developer Kit, JetPack 6.2.1 (L4T r36.4.4), Ubuntu 22.04 |
| User | `user` (password: ask the team; needed for `sudo`) |
| Hostname | `ubuntu` |
| Sensor LAN (eno1, 1 GbE switch on the tractor) | **192.168.26.4** |
| Tailscale (remote, slow: relayed, ~1 MB/s) | **100.73.97.60** (`tractor-jetson`) |
| Desktop | GDM auto-login as `user` (needed: it auto-mounts the 8 TB SSD) |

```bash
ssh user@192.168.26.4        # laptop on the tractor LAN
ssh user@100.73.97.60        # from anywhere via Tailscale
```

**Laptop on the tractor LAN:** plug into the sensor switch. If it gets no
address automatically, set a static one, e.g. `192.168.26.50/24`. Taken
addresses: `.1` (router/switch), `.4` (Jetson), `.26`, `.70–.74` (5 ArkCams),
`.85` (Ouster), `.100` (NovAtel), `.222` (a laptop on 2026-10-26).

**Windows command prompt (cmd):** wrap remote commands in **double** quotes,
single quotes break: `ssh -t user@100.73.97.60 "sudo tractor-mode status"`.

---

## 2. Operating modes

All three modes run the same sensor drivers (`tractor_bringup`); they differ
in the bringup arguments and what runs on top.

| | **demo** | **record** | **calib** | **off** |
|---|---|---|---|---|
| Sensor drivers (`ros2-publishers-boot`) | yes | yes | yes | no |
| Bringup TF (URDF from `vario700_sensorrig`) | **off** (`tf:=false`) — the perception stack publishes TF | on | on | – |
| Ouster driver's own static TF (`os_sensor→os_lidar/os_imu`) | **off** (`ouster_static_tf:=false`) | on | on | – |
| ZED depth | **off** (`depth_mode: NONE`) | NEURAL_LIGHT | NEURAL_LIGHT | – |
| Perception container (`perception-demo`) | **yes** | no | no | no |
| Continuous recording (`ros2-recording-continuous`) | no | **yes** (MCAP, 8 TB SSD) | no | no |
| Manual calibration recording (`calib-record`) | – | – | **yes** (.db3, NVMe) | – |
| Foxglove bridge | yes (`:8765`, in the container) | no | no | no |

### 2.1 Demo mode

```bash
sudo tractor-mode demo
tractor-mode status          # expect: 3 lines active/enabled as below
```

Expected status:
```
mode:        demo
  ros2-publishers-boot.service       active    enabled
  perception-demo.service            active    enabled
  ros2-recording-continuous.service  inactive  disabled
bringup:     tractor_bringup.launch.py tf:=false ouster_static_tf:=false zed_params_override:=.../zed_no_depth.yaml
launches:    1 (must be 0 or 1)
```

The perception container needs ~30 s after start (TensorRT engines are cached
in the Docker volume `perception_trt_cache`; if that volume is ever deleted,
the first start takes ~30 min to rebuild them).

**Watch it (Foxglove):**
1. Laptop on the tractor LAN (see §1).
2. Get the layout: `scp user@192.168.26.4:~/Desktop/perception_live_layout.json ~/`
   (also in `traversability_seg_ros2/foxglove/perception_live_layout.json`).
3. Foxglove → *Open connection* → *Foxglove WebSocket* → `ws://192.168.26.4:8765`.
4. *Layouts* → *Import from file* → `perception_live_layout.json`.

Layout: left 3D (tractor model, semantic Ouster cloud, BEV traversability grid,
lidar objects, safety zones); right top ZED front camera, right bottom the 5
ArkCams + BEV map. Camera images carry the detection boxes:

| Box | Meaning |
|---|---|
| red / yellow | person inside the red / yellow safety zone |
| green | person outside the zones |
| `person 4.2 m` | distance from `base_link`, position from a lidar object in the box |
| `person 4.2 m (cam)` | no lidar point in the box; position from ground projection |
| `person` (no distance) | no 3D position (no lidar hit, ground projection impossible) |

If boxes are missing in an image panel: panel settings → *Image annotations* →
enable `/safety_zone/annotations/<camera>`.

Measured live (workshop, 2026-10-26, depth off): YOLO ~20 Hz per ArkCam /
14.8 Hz ZED, lidar objects + fusion + safety alerts 10 Hz (Ouster runs
1024x10), segmentation masks ~12 Hz, BEV ~7 Hz. CPU ~66 %, GPU 40–98 %.

### 2.2 Record mode (datasets)

```bash
sudo tractor-mode record
tractor-mode status          # 8 TB SSD must show "mounted"
journalctl -u ros2-recording-continuous -f     # recorder output
```

- Writes MCAP (Zstd "Fast"), **20 s chunks**, to
  `/media/user/ext4_8tb_5/autorecord/rosbag2_YYYY_MM_DD-HH_MM_SS/`.
- Topics: `tractor_bringup/config/record_topics.txt` (all cameras +
  camera_info, ZED stereo + IMU + odom, Ouster, Blickfeld, NovAtel, /tf,
  /tf_static, /diagnostics). ~125 MB/s.
- The SSD is mounted by the desktop session (auto-login). If it is not
  plugged in / not mounted, the recorder's preflight fails on purpose
  (`FATAL: ... not a mount point`) and systemd retries every 30 s. Needs
  ≥ 100 GB free.
- Recording starts automatically after boot while in record mode.
- **Not yet tested end-to-end with `tractor-mode`** (the SSD was not attached
  on 2026-10-26). Check `journalctl -u ros2-recording-continuous` the first time.

Stop recording only: `sudo tractor-mode calib` (drivers keep running) or
`sudo tractor-mode off`.

### 2.3 Calibration mode (.db3 for MSA)

```bash
sudo tractor-mode calib                 # drivers only, no auto recording
calib-record start msa_run1             # name optional; no sudo
calib-record status                     # size so far
calib-record stop                       # finalizes, prints bag info
```

- Output: `/mnt/calibration/<YYYY-MM-DD_HH-MM-SS>_<name>/`
  - `bag/bag_0.db3` + `bag/metadata.yaml` — **one** uncompressed sqlite3 file per run
  - `calib_topics.txt` — the topic list used, `record.log` — recorder output
- Disk: internal NVMe (`/mnt`, 3.4 TB free), independent of the 8 TB SSD.
  ~125 MB/s, i.e. ~7.5 GB per minute.
- Topics: `tractor_bringup/config/calib_topics.txt` — 5 ArkCams (compressed +
  camera_info), ZED left/right (compressed + camera_info) + ZED IMU, Ouster
  points + IMU, Blickfeld points, NovAtel `imu/data`, `imu/data_raw`, `inspva`,
  `inspvax`, `/tf_static`. Tested 2026-10-26: all 23 topics present.
- Only one recording at a time; `stop` waits up to 60 s for the bag to close.
- Copy off: `rsync -a --info=progress2 user@192.168.26.4:/mnt/calibration/<dir> .`

### 2.4 Off / manual operation

```bash
sudo tractor-mode off        # stops + disables drivers, perception, recording
```

Running the drivers by hand (debugging), only while the services are stopped:
```bash
source /opt/ros/humble/setup.bash && source /mnt/ros2_ws/install/setup.bash
export ROS_DOMAIN_ID=0 RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
ros2 launch tractor_bringup tractor_bringup.launch.py            # = record/calib
ros2 launch tractor_bringup tractor_bringup.launch.py tf:=false \
  ouster_static_tf:=false \
  zed_params_override:=/mnt/ros2_ws/install/tractor_bringup/share/tractor_bringup/config/zed_no_depth.yaml   # = demo
```
Never run two bringups at once (two ZED / RTSP / Ouster clients). Check with
`tractor-mode status` → `launches: 1`. A hand-started bringup is stopped with
Ctrl+C; `tractor_multi_cam_publisher` sometimes hangs → `pkill -KILL -f tractor_multi_cam_publisher/lib`.

---

## 3. systemd units

| Unit | What it does | demo | record | calib |
|---|---|---|---|---|
| `ptp4l-eno1` | PTP grandmaster on eno1 (sensor time base) | always | always | always |
| `phc2sys-eno1` | syncs the NIC clock with the system clock | always | always | always |
| `ros2-boot-network-wait`, `ros2-boot-usb-wait` | advisory boot waits for sensors / ZED (never fail) | always | always | always |
| `ros2-publishers-boot` | the sensor drivers: `ros2 launch tractor_bringup tractor_bringup.launch.py $BRINGUP_ARGS` | ✔ | ✔ | ✔ |
| `perception-demo` | perception container (`docker run … live_stack.sh foxglove:=true`) | ✔ | – | – |
| `ros2-recording-continuous` | `record.sh` (MCAP, 20 s chunks) after `recording-preflight.sh` | – | ✔ | – |

Files:

| File | Source in repo | Purpose |
|---|---|---|
| `/etc/systemd/system/ros2-publishers-boot.service` | `/mnt/ros2_ws/system/units/` (not in git) | original unit |
| `/etc/systemd/system/ros2-publishers-boot.service.d/mode.conf` | `tractor_bringup/systemd/ros2-publishers-boot-mode.conf` | drop-in: replaces ExecStart with the bringup + `$BRINGUP_ARGS` from `/etc/tractor/mode.env`; stop = SIGINT, SIGKILL after 20 s |
| `/etc/systemd/system/perception-demo.service` | `tractor_bringup/systemd/perception-demo.service` | perception container |
| `/etc/systemd/system/ros2-recording-continuous.service` | `/mnt/ros2_ws/system/units/` | recorder (requires the SSD mount) |
| `/etc/tractor/mode.env` | written by `tractor-mode` | `TRACTOR_MODE=…`, `BRINGUP_ARGS="…"` |
| `/etc/tractor/perception.env` (optional) | by hand | `PERCEPTION_RIG=…` calibration of the perception stack (§4.4) |
| `/usr/local/bin/tractor-mode`, `/usr/local/bin/calib-record` | `tractor_bringup/scripts/` | mode switch, calibration recorder |

`tractor-mode <mode>` = write `mode.env` + `systemctl enable/disable --now`
the units of that mode + restart the drivers. Doing the same by hand:

```bash
systemctl status ros2-publishers-boot perception-demo ros2-recording-continuous
sudo systemctl restart ros2-publishers-boot      # drivers (re-reads mode.env)
sudo systemctl restart perception-demo           # perception container only
sudo systemctl enable  <unit>    # start at boot     | disable: no start at boot
sudo systemctl start   <unit>    # start now         | stop: stop now
sudo systemctl enable --now <unit>                # both
journalctl -u <unit> -f                           # follow logs
journalctl -u <unit> -b --no-pager | tail -100    # this boot
```

**Install / update** the mode setup (after `git pull` in `tractor_bringup`):
```bash
cd /mnt/ros2_ws/src/tractor_bringup && git pull
cd /mnt/ros2_ws && source /opt/ros/humble/setup.bash && colcon build --packages-select tractor_bringup
sudo /mnt/ros2_ws/src/tractor_bringup/systemd/install.sh     # units + scripts, does not change the mode
sudo tractor-mode demo                                         # (or the mode you want) re-applies it
```

> **Pending one-time step (2026-10-26):** run the two lines above
> (`install.sh` + `tractor-mode demo`) once more — the installed
> `tractor-mode` predates the fix that quotes `BRINGUP_ARGS` (only the status
> display was wrong) and `perception-demo.service` predates `PERCEPTION_RIG`.

**Back to the original recording setup** (no modes at all):
```bash
sudo rm /etc/systemd/system/ros2-publishers-boot.service.d/mode.conf
sudo systemctl disable --now perception-demo
sudo systemctl daemon-reload && sudo systemctl restart ros2-publishers-boot
```

---

## 4. Configuration — what is changed / disabled and what can be set

### 4.1 Changed for the demo (only in demo mode)

| What | Setting | Why | Where |
|---|---|---|---|
| Bringup TF | `tf:=false` | the bringup's URDF is `vario700_sensorrig` **0.2.0 / kalibr**, whose `*_optical_frame`s are wrong (fixed in 0.3.0) and the images are stamped with those frames; the perception stack publishes TF from its own calibration instead (one source for TF, projection and camera_info) | `mode.env` |
| Ouster static TF | `ouster_static_tf:=false` (driver's `/tf_static` remapped to `/ouster/tf_static_unused`) | ouster-ros always publishes `os_sensor→os_lidar` rotated 180° about z (from the sensor); **all** rig URDFs define it as identity and the calibrations assume that. With both on `/tf_static`, the whole sensor tree below `os_lidar` (all cameras in msa_new) flipped randomly → "all sensors tilted" (found 2026-10-27). The same double definition exists in record/calib mode (affects the lidar cloud only) | `mode.env` |
| ZED depth | `depth_mode: NONE` | frees the GPU (segmentation 9.5 → 12 Hz); the stack only uses the left image. Disables ZED point cloud, odometry (`/zed/zed_node/odom`), object detection | `tractor_bringup/config/zed_no_depth.yaml` via `zed_params_override` |
| Recording | off | — | `tractor-mode` |

### 4.2 Always off / reduced in the perception stack

| What | Setting | Why |
|---|---|---|
| Semantic Blickfeld cloud | `lidar:=/ouster/points` in `live_stack.sh` | frame `blickfeld_qb2` is not in the msa_new URDF — re-enable when the new calibration URDF contains it (`lidar:=true`) |
| YOLO annotated images | `publish_annotated_image: false` (`yolo_multi_cam/config/params.yaml`) | JPEG encoding costs CPU; boxes are drawn by Foxglove from `/safety_zone/annotations/*` instead |
| YOLO classes | person only, baked into `yolo11n_person_fused.onnx` | pre/post-processing on the GPU (`yolo_multi_cam/tools/fuse_onnx.py`) |
| BLAS/OpenMP/OpenCV threads | `OMP_NUM_THREADS=OPENBLAS_NUM_THREADS=OPENCV_FOR_THREADS_NUM=1` (Dockerfile) | nested thread pools oversubscribed the Orin (3x slower) |
| Recording of perception outputs | none | the stack's topics are not in `record_topics.txt` |

### 4.3 Things you may want to change

| What | Where | Effect / how to apply |
|---|---|---|
| Safety zone sizes (red / yellow, in `base_link`: +y forward, +x right) | `obstacle_detection/config/fusion_params.yaml` (`red_zone_*`, `yellow_zone_*`) | rebuild image (§6) |
| YOLO confidence / NMS | `yolo_multi_cam/config/params.yaml` (`confidence_threshold`, `iou_threshold`) | rebuild image |
| Segmentation model | `perception_stack.launch.py model:=…` (default `pidnet_s_trav_b`; ONNX in `/mnt/perception/models/onnx`) | append to `live_stack.sh foxglove:=true` in `perception-demo.service`; new models build a TensorRT engine on first start (~10–20 min) |
| Recording topics | `tractor_bringup/config/record_topics.txt` | `colcon build --packages-select tractor_bringup`, restart recorder |
| Calibration recording topics | `tractor_bringup/config/calib_topics.txt` | `colcon build --packages-select tractor_bringup` |
| Calibration output dir | `ROOT=` in `scripts/calib-record` | `install.sh` |
| ZED parameters (resolution, depth mode, …) | `zed-ros2-wrapper/zed_wrapper/config/common_stereo.yaml` (base), override files like `zed_no_depth.yaml` | restart drivers |
| Ouster mode (1024x10) | `ouster-ros` config (branch `ros2`) | restart drivers |
| Foxglove port | `foxglove_port:=` in `perception-demo.service` | `sudo systemctl daemon-reload && sudo systemctl restart perception-demo` |

### 4.4 Calibration of the perception stack (new MSA calibration)

The perception stack takes **all** geometry from one *rig file*
(`traversability_seg_ros2/config/rig_vario700_<name>_live.yaml`):
`urdf` (TF + extrinsics), `intrinsics_dir` (one `*.intrinsics.yaml` per camera),
`ego_mask_dir` (optional masks of the tractor body per camera), camera topics,
optical frames and image sizes. Currently: `rig_vario700_msa_new_live.yaml`
(MSA calibration from 2025-11-21, URDF `vario700_sensorrig_msa_new.urdf` from
sensorrig 0.3.0).

To use a new calibration `<name>`:
1. URDF → `vario700_sensorrig/urdf/vario700_sensorrig_<name>.urdf` (with
   correct `*_optical_frame` children, like 0.3.0; ideally incl. `blickfeld_qb2`).
2. Intrinsics → `traversability_seg_ros2/config/intrinsics/<name>/` with the
   file names used in the rig file (`camera_side_left.intrinsics.yaml`, …,
   `zed_zed_node_left_raw_color.intrinsics.yaml`).
3. Copy `rig_vario700_msa_new_live.yaml` → `rig_vario700_<name>_live.yaml`,
   change `urdf`, `intrinsics_dir`, `ego_mask_dir`; set the ZED `image_size`
   if the calibration resolution differs from the live 1920x1080 (same field of
   view required; the camera_info is scaled).
4. Rebuild the image (§6), then
   ```bash
   echo 'PERCEPTION_RIG=/root/ros2_ws/install/share/traversability_seg_ros2/config/rig_vario700_<name>_live.yaml' | sudo tee /etc/tractor/perception.env
   sudo systemctl restart perception-demo
   ```
5. Check in Foxglove: lidar points in the 3D view should line up with the
   segmentation; boxes should get lidar distances (no `(cam)`) for people
   that are visible to the Ouster.

The drivers' own `camera_info` (from `tractor_multi_cam_publisher/calibration/`,
currently the old `msa` files) is not used by the stack; the stack publishes
its calibration on `/perception/<camera topic>/camera_info`.

---

## 5. Repositories and how they interact

### 5.1 Two workspaces on the Jetson

| Path | Contents | Built how | Used by |
|---|---|---|---|
| `/mnt/ros2_ws` | sensor drivers + bringup (native Humble) | `colcon build` on the Jetson | `ros2-publishers-boot`, recording |
| `/mnt/perception` | perception sources (`src/`), Docker setup (`docker/perception_jetson/`), models (`models/onnx/`) | Docker image `perception-jetson:humble` | `perception-demo` |

The perception packages in `/mnt/ros2_ws/src` (`obstacle_detection`,
`yolo_multi_cam`, `ROS2-Pointcloud-Filter-Tools` on `main`) are **old
versions and not used** by the demo — the container has its own copies in
`/mnt/perception/src` (branches below).

### 5.2 Repositories (all `github.com/Gunreben/…`)

| Repo | Branch in use | Where | Role |
|---|---|---|---|
| `tractor_bringup` | **`feature/demo`** | `/mnt/ros2_ws/src` | launch of all drivers, TF policy, record/calib topic lists, ZED override, **modes + systemd + this runbook** |
| `tractor_multi_cam_publisher` | `main` (0.2.0) | `/mnt/ros2_ws/src` | 5 ArkCam RTSP → NVDEC → NVJPG → `/camera/<cam>/image_raw/compressed` (25 Hz) + `camera_info` |
| `ouster-ros` | `ros2` | `/mnt/ros2_ws/src` | Ouster OS-0-128 → `/ouster/points` (10 Hz) |
| `zed-ros2-wrapper` | `v2-humble-5.1` | `/mnt/ros2_ws/src` | ZED 2i (USB) → `/zed/zed_node/left/color/raw/image/compressed` (1080p, 15 Hz), IMU |
| `blickfeld_qb2_ros2_driver` | `main` | `/mnt/ros2_ws/src` | Blickfeld Qb2 → `/bf/points_raw` |
| NovAtel (`novatel_oem7_driver`, apt) | – | `/opt/ros/humble` | GNSS/INS → `/novatel/oem7/*` |
| `vario700_sensorrig` | `main` (0.2.0) in `/mnt/ros2_ws`; `fix/camera-optical-frames` (0.3.0) in `/mnt/perception` | both | URDF/meshes of the rig. 0.2.0 = bringup TF (not used in demo), 0.3.0 = perception TF |
| `traversability_seg_ros2` | `feature/presentation` | `/mnt/perception/src` | semantic segmentation (PIDNet-S, TensorRT), BEV grid, semantic lidar, rig files/calibration, `camera_info_publisher`, **`perception_stack.launch.py`** (starts everything below), Foxglove layouts, **`docker/perception_jetson/`** (Dockerfile, `live_stack.sh`, HIL tools) |
| `yolo_multi_cam` | `feature/desktop-presentation` | `/mnt/perception/src` | YOLO11n person detection on all 6 cameras in one TensorRT batch → `/yolo/<cam>/detections` |
| `ROS2-Pointcloud-Filter-Tools` (pkg `lidar_filter`) | `feature/desktop-presentation` | `/mnt/perception/src` | Ouster self-box + ground removal → `/ouster/points/filtered` |
| `obstacle_detection` | `feature/desktop-presentation` | `/mnt/perception/src` | clustering + tracking → `/lidar/objects`; **fusion** (YOLO ↔ lidar) → `/safety_zone/detections`, `/safety_zone/alerts`, image boxes `/safety_zone/annotations/<cam>`; zone scene for Foxglove 3D |

### 5.3 Data flow (demo mode)

```
 sensors ──► tractor_bringup (native, ros2-publishers-boot, domain 0, Cyclone DDS)
   ArkCams ─► /camera/<cam>/image_raw/compressed ───────────────┐
   ZED ─────► /zed/zed_node/left/color/raw/image/compressed ────┤
   Ouster ──► /ouster/points ───────────────────────────────────┤
   NovAtel, Blickfeld (not used by the stack)                   │
                                                                ▼
 perception-demo container (perception_stack.launch.py, same domain/DDS, wall clock)
   robot_state_publisher (rig URDF) ─► /tf_static
   camera_info_publisher ─► /perception/.../camera_info  (rig intrinsics)
   yolo_multi_cam ─► /yolo/<cam>/detections ──────────────┐
   lidar_filter ─► /ouster/points/filtered                │
     └► obstacle_detection_node ─► /lidar/objects ────────┤
   detection_fusion_node ◄────────────────────────────────┘
     ─► /safety_zone/detections, /safety_zone/alerts, /safety_zone/annotations/<cam>
   safety_zone_scene_node ─► /safety_zone/scene (3D boxes, zones, STOP)
   seg_node ─► /<cam>/traversability/mask|overlay, /traversability/bev/*, /traversability/points/ouster
   foxglove_bridge :8765 ─► laptop
```

DDS: everything in domain 0 with `rmw_cyclonedds_cpp` (set in the units and
in `live_stack.sh`). A laptop with ROS 2 on the LAN sees the topics with the
same settings, but use Foxglove for viewing — subscribing to the Ouster cloud
over the 1 GbE switch (~63 MB/s) works, more than that does not.

---

## 6. Updating the perception stack (code changes)

From a development PC with the workspace (`~/ros2_ws`, sources on the
branches of §5.2):

```bash
~/ros2_ws/src/traversability_seg_ros2/docker/perception_jetson/sync_to_jetson.sh user@192.168.26.4 /mnt/perception
ssh user@192.168.26.4 "cd /mnt/perception && docker build -t perception-jetson:humble -f docker/perception_jetson/Dockerfile ."
ssh -t user@192.168.26.4 "sudo systemctl restart perception-demo"
```

- The build only re-runs the last layers (~4 min). A full rebuild (new base
  image) downloads ~8 GB — use the tractor's own internet, not Tailscale.
- `sync_to_jetson.sh` copies the 5 packages, the Docker dir and the two models
  in use (`MODELS=all` for all ONNX models).
- New/changed ONNX models build a TensorRT engine on first start (minutes; the
  stack starts once it is done).

---

## 7. Troubleshooting

| Symptom | Check / fix |
|---|---|
| `tractor-mode status` shows `launches: 2` | two driver sets fight over the sensors. `sudo systemctl stop ros2-publishers-boot`, kill leftovers (`pkill -INT -f "ros2 launch tractor_bringup"`, then `pkill -KILL -f tractor_multi_cam_publisher/lib`), `sudo systemctl start ros2-publishers-boot` |
| no camera images | `ping 192.168.26.70` … `.74`; `journalctl -u ros2-publishers-boot | grep -i rtsp` |
| ZED missing | USB cable; `journalctl -u ros2-publishers-boot | grep -i zed` ("Camera successfully opened") |
| perception container restarts | `docker logs --tail 100 perception`; `journalctl -u perception-demo` |
| sensors / cameras rotated or tilted in Foxglove 3D | two TF sources for the same frame. `ros2 topic info -v /tf_static` (in demo only `robot_state_publisher` may publish); demo `mode.env` must contain `tf:=false ouster_static_tf:=false` |
| boxes but no distances | TF/calibration: `/tf_static` from the container? (`tractor-mode status` must show `tf:=false` in demo); Ouster running? |
| Foxglove cannot connect | laptop IP in 192.168.26.0/24? `ss -ltn | grep 8765` on the Jetson; demo mode active? |
| recorder fails | `journalctl -u ros2-recording-continuous` — SSD mounted? ≥ 100 GB free? |
| `calib-record start` says "already recording" after a crash | `rm /mnt/calibration/.recording` |
| everything slow | `tegrastats` (GPU `GR3D_FREQ`); is ZED depth really off (`journalctl -u ros2-publishers-boot | grep "Depth mode"`)? |

Background on the perception setup (HIL tests, performance work, Docker):
`traversability_seg_ros2/docker/perception_jetson/README.md`.
