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

echo "Vérification du module Python Mininet..."
python3 -c "from mininet.cli import CLI; print('Mininet Python OK')"

mn -c

python3 topology/sdn_topology.py