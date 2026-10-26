#!/usr/bin/env python3
"""Top-level bringup for the Vario700 tractor recording rig.

Every sensor can be switched off for bench work or when hardware is
down, e.g.:
    ros2 launch tractor_bringup tractor_bringup.launch.py zed:=false

TF policy: tf.launch.py (vario700_sensorrig URDF) is the only source of
/tf_static; all driver-internal TF publishing is disabled here. See
system/MIGRATION_v1_v2.md "TF tree (v2)".
"""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def _pkg(name):
    return FindPackageShare(name).find(name)


def generate_launch_description():
    bringup_pkg = _pkg('tractor_bringup')

    args = [
        DeclareLaunchArgument('tf', default_value='true',
                              description='Publish the URDF TF tree.'),
        DeclareLaunchArgument('arkcams', default_value='true',
                              description='5x ArkCam RTSP publisher + camera_info.'),
        DeclareLaunchArgument('ouster', default_value='true',
                              description='Ouster OS-0-128 driver.'),
        DeclareLaunchArgument('zed', default_value='true',
                              description='ZED 2i stereo camera.'),
        DeclareLaunchArgument('blickfeld', default_value='true',
                              description='Blickfeld Qb2 driver.'),
        DeclareLaunchArgument('novatel', default_value='true',
                              description='NovAtel OEM7 GNSS/INS driver.'),
        DeclareLaunchArgument('rviz', default_value='false',
                              description='RViz with the sensorrig config.'),
        DeclareLaunchArgument('camera_model', default_value='zed2i',
                              description='ZED camera model.'),
        DeclareLaunchArgument('zed_params_override', default_value='',
                              description='ZED wrapper parameter override file '
                                          '(e.g. config/zed_no_depth.yaml).'),
        DeclareLaunchArgument('ouster_hostname', default_value='192.168.26.85',
                              description='Ouster sensor IP.'),
        DeclareLaunchArgument('oem7_ip_addr', default_value='192.168.26.100',
                              description='NovAtel OEM7 IP.'),
    ]

    tf_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(bringup_pkg, 'launch', 'tf.launch.py')),
        condition=IfCondition(LaunchConfiguration('tf')),
    )

    arkcam_publisher = Node(
        package='tractor_multi_cam_publisher',
        executable='tractor_multi_cam_publisher',
        name='multi_cam_publisher',
        output='screen',
        condition=IfCondition(LaunchConfiguration('arkcams')),
        respawn=True,
        respawn_delay=10.0,
    )

    camera_info_publisher = Node(
        package='tractor_multi_cam_publisher',
        executable='camera_info_publisher',
        name='camera_info_publisher',
        output='screen',
        parameters=[{'calibration_path': os.path.join(
            _pkg('tractor_multi_cam_publisher'), 'calibration')}],
        condition=IfCondition(LaunchConfiguration('arkcams')),
        respawn=True,
        respawn_delay=10.0,
    )

    ouster_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(_pkg('ouster_ros'), 'launch', 'driver.launch.py')),
        launch_arguments=[
            ('sensor_hostname', LaunchConfiguration('ouster_hostname')),
        ],
        condition=IfCondition(LaunchConfiguration('ouster')),
    )

    # publish_urdf/tf/map_tf/imu_tf all false: the URDF owns the zed_*
    # frames (the wrapper's own URDF publishes zed_camera_center <->
    # zed_left_camera_frame in the opposite direction, which makes the
    # static TF graph cyclic and wedges the wrapper's own lookups);
    # zed_imu_link comes from vario700_sensorrig >= 0.2.0. ZED odometry
    # stays available on /zed/zed_node/odom.
    zed_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(_pkg('zed_wrapper'), 'launch', 'zed_camera.launch.py')),
        launch_arguments=[
            ('camera_model', LaunchConfiguration('camera_model')),
            ('publish_urdf', 'false'),
            ('publish_tf', 'false'),
            ('publish_map_tf', 'false'),
            ('publish_imu_tf', 'false'),
            ('ros_params_override_path', LaunchConfiguration('zed_params_override')),
        ],
        condition=IfCondition(LaunchConfiguration('zed')),
    )

    blickfeld_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(_pkg('blickfeld_qb2_ros2_driver'), 'launch',
                         'blickfeld_qb2_ros2_driver.launch.py')),
        condition=IfCondition(LaunchConfiguration('blickfeld')),
    )

    novatel_include = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(_pkg('novatel_oem7_driver'), 'launch',
                         'oem7_net.launch.py')),
        launch_arguments=[
            ('oem7_ip_addr', LaunchConfiguration('oem7_ip_addr')),
        ],
        condition=IfCondition(LaunchConfiguration('novatel')),
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', os.path.join(_pkg('vario700_sensorrig'),
                                      'rviz', 'vario700_sensorrig.rviz')],
        condition=IfCondition(LaunchConfiguration('rviz')),
    )

    return LaunchDescription(args + [
        tf_include,
        arkcam_publisher,
        camera_info_publisher,
        ouster_include,
        zed_include,
        blickfeld_include,
        novatel_include,
        rviz_node,
    ])
