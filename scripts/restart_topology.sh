#!/bin/bash

set -e

cd "$(dirname "$0")/.."

if [ "$EUID" -ne 0 ]; then
    echo "ERREUR : le redemarrage de Mininet doit etre lance avec sudo."
    echo "Utilise : sudo ./scripts/restart_topology.sh"
    exit 1
fi

mkdir -p logs

echo "Redemarrage controle de la topologie Mininet..."

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

echo "Arret de l'ancienne topologie si elle existe..."
pkill -f "python3 topology/sdn_topology.py" >/dev/null 2>&1 || true
pkill -f "topology/sdn_topology.py" >/dev/null 2>&1 || true

if command -v fuser >/dev/null 2>&1; then
    fuser -k 8090/tcp >/dev/null 2>&1 || true
fi

sleep 1

echo "Nettoyage des anciens bridges Mininet..."
if command -v ovs-vsctl >/dev/null 2>&1; then
    ovs-vsctl --timeout=2 list-br 2>/dev/null | grep -E '^s[0-9]+$' | while read -r bridge; do
        ovs-vsctl --if-exists del-br "$bridge" || true
    done
fi

echo "Demarrage de la nouvelle topologie en mode dashboard..."
NO_CLI=1 nohup python3 topology/sdn_topology.py > logs/topology.log 2>&1 &
TOPOLOGY_PID=$!

echo "$TOPOLOGY_PID" > logs/topology.pid

for _ in $(seq 1 20); do
    if python3 - <<'PY'
import socket
sock = socket.socket()
sock.settimeout(0.5)
try:
    sock.connect(("127.0.0.1", 8090))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
    then
        echo "Topologie Mininet relancee. PID=$TOPOLOGY_PID"
        exit 0
    fi
    sleep 0.5
done

echo "ERREUR : la topologie n'a pas ouvert l'API 8090."
echo "Consulte : logs/topology.log"
exit 1
