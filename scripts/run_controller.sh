#!/bin/bash

set -e

cd "$(dirname "$0")/.."

if [ ! -d "venv" ]; then
    echo "ERREUR : l'environnement virtuel n'existe pas."
    echo "Lance d'abord : ./scripts/install_ubuntu.sh"
    exit 1
fi

source venv/bin/activate

echo "Environnement virtuel activé : $VIRTUAL_ENV"
echo "Python utilisé : $(which python)"
echo "Lancement du contrôleur Ryu sur le port OpenFlow 6653..."

ryu-manager --ofp-tcp-listen-port 6653 controller/sdn_controller.py