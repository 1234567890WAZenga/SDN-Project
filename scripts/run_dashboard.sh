#!/bin/bash

# Arrêter le script en cas d'erreur
set -e

# Aller à la racine du projet
cd "$(dirname "$0")/.."

# Vérifier que l'environnement virtuel existe
if [ ! -d "venv" ]; then
    echo "ERREUR : l'environnement virtuel n'existe pas."
    echo "Lance d'abord : ./scripts/install_ubuntu.sh"
    exit 1
fi

# Activer l'environnement virtuel
source venv/bin/activate

# Rappel visible
echo "Environnement virtuel activé : $VIRTUAL_ENV"
echo "Python utilisé : $(which python)"
echo "Lancement du dashboard Flask..."

# Lancer le dashboard Flask
python dashboard/app.py