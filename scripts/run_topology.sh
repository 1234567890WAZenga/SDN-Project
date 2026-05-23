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

if command -v fuser >/dev/null 2>&1; then
    echo "Libération du port API Mininet 8090 si nécessaire..."
    fuser -k 8090/tcp >/dev/null 2>&1 || true
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
