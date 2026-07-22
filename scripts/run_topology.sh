#!/bin/bash

# Lance la topologie Mininet.
# A executer avec sudo, car Mininet cree des interfaces reseau Linux.

set -Eeuo pipefail

# Se placer a la racine du projet.
cd "$(dirname "$0")/.."

# Langue neutre pour eviter certains problemes de parsing dans les sorties Mininet.
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

# Mininet est installe dans le Python systeme, pas dans le venv Ryu.
info "Verification du module Python Mininet..."
python3 -c "from mininet.cli import CLI; print('Mininet Python OK')"

# La topologie est generee depuis topology_config.json.
info "Verification de topology_config.json..."
python3 -m json.tool topology_config.json >/dev/null

# Les switches doivent trouver Ryu avant le demarrage de Mininet.
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

# Arrete les anciennes topologies pour eviter les ports et interfaces deja utilises.
info "Arret des anciennes instances de topologie..."
pkill -f "python3 topology/sdn_topology.py" >/dev/null 2>&1 || true
pkill -f "topology/sdn_topology.py" >/dev/null 2>&1 || true
pkill -f "mininet:" >/dev/null 2>&1 || true

# Le port 8090 sert a l'API Mininet utilisee par le dashboard.
if command -v fuser >/dev/null 2>&1; then
    info "Liberation du port API Mininet 8090 si necessaire..."
    fuser -k 8090/tcp >/dev/null 2>&1 || true
fi

# Par defaut, on evite mn -c car il peut couper Ryu selon l'installation.
if [ "${DEEP_MININET_CLEAN:-0}" = "1" ]; then
    info "Nettoyage profond Mininet avec mn -c..."
    info "Attention : ce mode peut interrompre le controleur sur certaines installations."
    mn -c >/dev/null 2>&1 || true
else
    info "Nettoyage cible Mininet sans arreter Ryu..."
fi

# Supprime les interfaces s1-ethX, h1-ethX, etc. restees apres un mauvais arret.
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

# Supprime les anciens bridges OVS nommes s1, s2, s3...
info "Suppression des bridges Open vSwitch sX restants..."
if command -v ovs-vsctl >/dev/null 2>&1; then
    ovs-vsctl --timeout=2 list-br 2>/dev/null \
        | grep -E '^s[0-9]+$' \
        | while read -r bridge; do
            ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
        done || true
fi

# Dernier controle : le nettoyage ne doit pas avoir coupe Ryu.
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

# Lance le fichier Python qui construit les switches, les hotes et les liens Mininet.
python3 topology/sdn_topology.py
