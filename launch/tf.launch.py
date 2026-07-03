#!/usr/bin/env python3
"""TF tree for the Vario700 rig — the ONLY source of /tf_static.

Also usable standalone on a desktop for bag playback:
    ros2 launch tractor_bringup tf.launch.py

The vario700_sensorrig URDF is the single source of truth for all
calibrated frames. Every driver runs with its own TF publishing disabled.
"""

import os

from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    vario700_pkg = FindPackageShare('vario700_sensorrig').find('vario700_sensorrig')
    urdf_path = os.path.join(vario700_pkg, 'urdf', 'vario700_sensorrig.urdf')
    with open(urdf_path, 'r') as f:
        robot_description = f.read()

    return LaunchDescription([
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
            respawn=True,
            respawn_delay=5.0,
        ),

        # The ZED wrapper hardcodes its base frame to '<camera_name>_camera_link'
        # and needs zed_camera_center -> zed_camera_link to resolve. The vario700
        # URDF does not define zed_camera_link, so provide it here (identity,
        # additive: no existing vario700 frame is modified).
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='zed_camera_link_publisher',
            arguments=['--frame-id', 'zed_camera_center',
                       '--child-frame-id', 'zed_camera_link'],
            respawn=True,
            respawn_delay=5.0,
        ),
    ])
