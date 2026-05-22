#!/usr/bin/env bash
set -euo pipefail

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

ryu-manager --ofp-tcp-listen-port 6633 controller/sdn_controller.py
