#!/bin/bash

# Lance le dashboard Web Flask sur le port 3000.
# Il permet de visualiser, tester et gerer l'infrastructure SDN.

set -e

# Se placer a la racine du projet.
cd "$(dirname "$0")/.."

# Le dashboard utilise le meme environnement virtuel que le controleur.
if [ ! -d "venv" ]; then
    echo "ERREUR : l'environnement virtuel n'existe pas."
    echo "Lance d'abord : ./scripts/install_ubuntu.sh"
    exit 1
fi

# Activer les dependances Python : Flask, requests, Ryu, etc.
source venv/bin/activate

echo "Environnement virtuel active : $VIRTUAL_ENV"
echo "Python utilise : $(which python)"
echo "Lancement du dashboard Flask..."

# Flask expose l'interface Web sur http://IP_VM:3000.
python dashboard/app.py
