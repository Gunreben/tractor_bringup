#!/bin/bash
# Install the operating-mode setup on the tractor Orin (once, with sudo):
#   sudo /mnt/ros2_ws/src/tractor_bringup/systemd/install.sh
# Installs: ros2-publishers-boot drop-in (mode.conf), perception-demo.service,
# /usr/local/bin/tractor-mode and calib-record. Does not change the mode; then
#   sudo tractor-mode demo|record|calib|off
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
D=$(dirname "$(readlink -f "$0")")
install -D -m 644 "$D/ros2-publishers-boot-mode.conf" \
    /etc/systemd/system/ros2-publishers-boot.service.d/mode.conf
rm -f /etc/systemd/system/ros2-publishers-boot.service.d/demo.conf   # pre-mode demo drop-in
install -m 644 "$D/perception-demo.service" /etc/systemd/system/perception-demo.service
install -m 755 "$D/../scripts/tractor-mode" /usr/local/bin/tractor-mode
install -m 755 "$D/../scripts/calib-record" /usr/local/bin/calib-record
install -d -o user -g user /mnt/calibration
systemctl daemon-reload
echo "installed. current state:"
tractor-mode status
