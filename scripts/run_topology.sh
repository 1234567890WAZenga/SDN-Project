#!/bin/bash

# Arrêter le script en cas d'erreur
set -e

# Aller à la racine du projet
cd "$(dirname "$0")/.."

# Vérifier que le script est lancé avec sudo
if [ "$EUID" -ne 0 ]; then
    echo "ERREUR : la topologie Mininet doit être lancée avec sudo."
    echo "Utilise : sudo ./scripts/run_topology.sh"
    exit 1
fi

echo "Lancement de la topologie Mininet..."
echo "Note : Mininet utilise le Python système, pas l'environnement virtuel Ryu."

# Nettoyer les anciennes instances Mininet
mn -c

# Lancer la topologie
python3 topology/sdn_topology.py