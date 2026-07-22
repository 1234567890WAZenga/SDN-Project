#!/bin/bash

# Relance Mininet en arriere-plan pour le dashboard.
# Utilise par Flask via sudo -n apres installation de la permission sudoers.

set -Eeuo pipefail

cd "$(dirname "$0")/.."

PROJECT_DIR="$(pwd)"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/topology.pid"
TOPOLOGY_LOG="$LOG_DIR/topology.log"
MININET_API_PORT=8090
RYU_HOST="127.0.0.1"
RYU_OPENFLOW_PORT=6653

export LANG=C
export LC_ALL=C

info() {
    echo "[$(date '+%H:%M:%S')] $*"
}

fail() {
    echo "ERREUR : $*" >&2
    exit 1
}

require_root() {
    # Mininet doit etre gere en root pour creer/supprimer les interfaces reseau.
    if [ "${EUID:-$(id -u)}" -ne 0 ]; then
        fail "le redemarrage de Mininet doit etre lance avec sudo."
    fi
}

check_python_mininet() {
    # Verifie que le module Python Mininet est disponible dans le Python systeme.
    info "Verification du module Python Mininet..."
    python3 -c "from mininet.cli import CLI; print('Mininet Python OK')" >/dev/null
}

check_topology_config() {
    # Evite de relancer Mininet avec une configuration JSON invalide.
    info "Verification de topology_config.json..."
    python3 -m json.tool topology_config.json >/dev/null
}

check_ryu() {
    # Mininet ne doit demarrer que si Ryu ecoute deja sur le port OpenFlow.
    info "Verification du controleur Ryu ${RYU_HOST}:${RYU_OPENFLOW_PORT}..."
    python3 - <<PY
import socket
import sys

sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("${RYU_HOST}", ${RYU_OPENFLOW_PORT}))
except OSError:
    print("ERREUR : Ryu n'ecoute pas sur ${RYU_HOST}:${RYU_OPENFLOW_PORT}.")
    print("Lance d'abord : ./scripts/run_controller.sh")
    sys.exit(1)
finally:
    sock.close()
PY
}

stop_previous_topology() {
    # Arrete l'ancienne topologie et libere l'API Mininet 8090.
    info "Arret de l'ancienne topologie Mininet..."

    if [ -f "$PID_FILE" ]; then
        old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [ -n "${old_pid:-}" ]; then
            kill "$old_pid" >/dev/null 2>&1 || true
        fi
        rm -f "$PID_FILE" >/dev/null 2>&1 || true
    fi

    pkill -f "python3 topology/sdn_topology.py" >/dev/null 2>&1 || true
    pkill -f "topology/sdn_topology.py" >/dev/null 2>&1 || true
    pkill -f "mininet:" >/dev/null 2>&1 || true

    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${MININET_API_PORT}/tcp" >/dev/null 2>&1 || true
    fi
}

full_mininet_cleanup() {
    # Nettoie les interfaces et bridges restes apres un arret brutal.
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
}

start_topology() {
    # Lance Mininet sans CLI pour que le dashboard puisse garder la topologie active.
    mkdir -p "$LOG_DIR"
    : > "$TOPOLOGY_LOG"

    info "Demarrage de la nouvelle topologie en mode dashboard..."
    NO_CLI=1 nohup python3 topology/sdn_topology.py > "$TOPOLOGY_LOG" 2>&1 &
    new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    info "Attente de l'API Mininet sur le port ${MININET_API_PORT}..."
    for _ in $(seq 1 40); do
        if python3 - <<PY
import socket
sock = socket.socket()
sock.settimeout(0.5)
try:
    sock.connect(("127.0.0.1", ${MININET_API_PORT}))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
        then
            info "Topologie Mininet relancee. PID=${new_pid}"
            exit 0
        fi

        if ! kill -0 "$new_pid" >/dev/null 2>&1; then
            echo "ERREUR : le processus Mininet s'est arrete pendant le demarrage." >&2
            tail -80 "$TOPOLOGY_LOG" >&2 || true
            exit 1
        fi

        sleep 0.5
    done

    echo "ERREUR : la topologie n'a pas ouvert l'API ${MININET_API_PORT}." >&2
    echo "Consulte : $TOPOLOGY_LOG" >&2
    tail -80 "$TOPOLOGY_LOG" >&2 || true
    exit 1
}

require_root
check_python_mininet
check_topology_config
check_ryu
stop_previous_topology
full_mininet_cleanup
check_ryu
start_topology
