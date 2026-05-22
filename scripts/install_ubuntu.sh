#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y python3 python3-pip python3-venv mininet openvswitch-switch iperf3 curl tcpdump wireshark
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

echo "Installation terminee."
echo "Verifie avec:"
echo "  mn --version"
echo "  ovs-vsctl --version"
echo "  ryu-manager --version"
