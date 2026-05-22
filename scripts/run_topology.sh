#!/usr/bin/env bash
set -euo pipefail

mn -c >/dev/null 2>&1 || true
python3 topology/sdn_topology.py
