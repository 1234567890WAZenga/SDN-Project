#!/bin/bash

set -e

cd "$(dirname "$0")/.."

if [ "$EUID" -ne 0 ]; then
    echo "ERREUR : la topologie Mininet doit être lancée avec sudo."
    echo "Utilise : sudo ./scripts/run_topology.sh"
    exit 1
fi

echo "Lancement de la topologie Mininet..."
echo "Note : Mininet utilise le Python système, pas l'environnement virtuel Ryu."

export LANG=C
export LC_ALL=C

echo "Vérification du module Python Mininet..."
python3 -c "from mininet.cli import CLI; print('Mininet Python OK')"

echo "Vérification du contrôleur Ryu sur 127.0.0.1:6653..."
python3 - <<'PY'
import socket
import sys

sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", 6653))
except OSError:
    print("ERREUR : Ryu n'écoute pas sur 127.0.0.1:6653.")
    print("Lance d'abord : ./scripts/run_controller.sh")
    sys.exit(1)
finally:
    sock.close()

print("Contrôleur Ryu joignable.")
PY

if command -v fuser >/dev/null 2>&1; then
    echo "Libération du port API Mininet 8090 si nécessaire..."
    fuser -k 8090/tcp >/dev/null 2>&1 || true
fi

echo "Suppression des anciennes interfaces Mininet si necessaire..."
if command -v ip >/dev/null 2>&1; then
    ip -o link show | awk -F': ' '{print $2}' | cut -d@ -f1 | grep -E '^[[:alnum:]_.-]+-eth[0-9]+$' | while read -r intf; do
        ip link delete "$intf" >/dev/null 2>&1 || true
    done
fi

echo "Suppression des anciens bridges sX si necessaire..."
if command -v ovs-vsctl >/dev/null 2>&1; then
    ovs-vsctl --timeout=2 list-br 2>/dev/null | grep -E '^s[0-9]+$' | while read -r bridge; do
        ovs-vsctl --if-exists del-br "$bridge" || true
    done
fi

if [ "${CLEAN_MININET:-0}" = "1" ]; then
    echo "Nettoyage Mininet complet demandé avec CLEAN_MININET=1."
    echo "Attention : mn -c peut arrêter ryu-manager. Relance le contrôleur ensuite si besoin."
    mn -c
else
    echo "Nettoyage Mininet complet ignoré pour ne pas arrêter le contrôleur Ryu."
    echo "Si nécessaire : sudo CLEAN_MININET=1 ./scripts/run_topology.sh"
fi

python3 topology/sdn_topology.py
