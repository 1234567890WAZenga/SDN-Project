#!/bin/bash

set -Eeuo pipefail

cd "$(dirname "$0")/.."

export LANG=C
export LC_ALL=C

info() {
    echo "$*"
}

fail() {
    echo "ERREUR : $*" >&2
    exit 1
}

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    fail "la topologie Mininet doit etre lancee avec sudo. Utilise : sudo ./scripts/run_topology.sh"
fi

info "Lancement de la topologie Mininet..."
info "Note : Mininet utilise le Python systeme, pas l'environnement virtuel Ryu."

info "Verification du module Python Mininet..."
python3 -c "from mininet.cli import CLI; print('Mininet Python OK')"

info "Verification de topology_config.json..."
python3 -m json.tool topology_config.json >/dev/null

info "Verification du controleur Ryu sur 127.0.0.1:6653..."
python3 - <<'PY'
import socket
import sys

sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", 6653))
except OSError:
    print("ERREUR : Ryu n'ecoute pas sur 127.0.0.1:6653.")
    print("Lance d'abord : ./scripts/run_controller.sh")
    sys.exit(1)
finally:
    sock.close()

print("Controleur Ryu joignable.")
PY

info "Arret des anciennes instances de topologie..."
pkill -f "python3 topology/sdn_topology.py" >/dev/null 2>&1 || true
pkill -f "topology/sdn_topology.py" >/dev/null 2>&1 || true
pkill -f "mininet:" >/dev/null 2>&1 || true

if command -v fuser >/dev/null 2>&1; then
    info "Liberation du port API Mininet 8090 si necessaire..."
    fuser -k 8090/tcp >/dev/null 2>&1 || true
fi

if [ "${DEEP_MININET_CLEAN:-0}" = "1" ]; then
    info "Nettoyage profond Mininet avec mn -c..."
    info "Attention : ce mode peut interrompre le controleur sur certaines installations."
    mn -c >/dev/null 2>&1 || true
else
    info "Nettoyage cible Mininet sans arreter Ryu..."
fi

info "Suppression des interfaces Mininet restantes..."
if command -v ip >/dev/null 2>&1; then
    ip -o link show \
        | awk -F': ' '{print $2}' \
        | cut -d@ -f1 \
        | grep -E '^[[:alnum:]_.-]+-eth[0-9]+$' \
        | while read -r intf; do
            ip link delete "$intf" >/dev/null 2>&1 || true
        done || true
fi

info "Suppression des bridges Open vSwitch sX restants..."
if command -v ovs-vsctl >/dev/null 2>&1; then
    ovs-vsctl --timeout=2 list-br 2>/dev/null \
        | grep -E '^s[0-9]+$' \
        | while read -r bridge; do
            ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
        done || true
fi

info "Nouvelle verification du controleur Ryu sur 127.0.0.1:6653..."
python3 - <<'PY'
import socket
import sys

sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", 6653))
except OSError:
    print("ERREUR : Ryu n'ecoute pas sur 127.0.0.1:6653.")
    print("Lance d'abord : ./scripts/run_controller.sh")
    sys.exit(1)
finally:
    sock.close()

print("Controleur Ryu joignable.")
PY

python3 topology/sdn_topology.py
