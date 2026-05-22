#!/bin/bash

# Arrêter le script dès qu'une erreur apparaît
set -e

echo "=== Mise à jour du système ==="
sudo apt update
sudo apt upgrade -y

echo "=== Installation de Mininet, Open vSwitch et outils réseau ==="
sudo apt install -y \
mininet \
openvswitch-switch \
openvswitch-common \
iproute2 \
iputils-ping \
net-tools \
curl \
wget \
tcpdump \
iperf \
xterm

echo "=== Installation de Python 3.8 et dépendances de compilation ==="
sudo apt install -y \
python3.8 \
python3.8-venv \
python3.8-dev \
python3-pip \
python3-testresources \
build-essential \
gcc \
make \
libffi-dev \
libssl-dev \
libxml2-dev \
libxslt1-dev \
zlib1g-dev \
git \
nano

echo "=== Démarrage de Open vSwitch ==="
sudo service openvswitch-switch start

echo "=== Création de l'environnement virtuel Python ==="
cd "$(dirname "$0")/.."

# Supprimer l'ancien environnement seulement si tu veux une installation propre
if [ -d "venv" ]; then
    echo "Ancien environnement virtuel détecté : suppression..."
    rm -rf venv
fi

python3.8 -m venv venv

echo "=== Activation de l'environnement virtuel ==="
source venv/bin/activate

echo "=== Vérification de Python utilisé ==="
which python
python --version

echo "=== Installation des versions Python compatibles avec Ryu ==="
python -m pip install --force-reinstall --no-cache-dir \
"pip==23.3.2" \
"setuptools==67.7.2" \
"wheel==0.41.3"

python -m pip install --no-cache-dir --no-build-isolation \
"dnspython==1.16.0" \
"eventlet==0.30.2" \
"ryu==4.34" \
"Flask==2.3.3" \
"requests==2.31.0"

echo "=== Test Mininet ==="
sudo mn --test pingall
sudo mn -c

echo "=== Installation terminée ==="
echo ""
echo "IMPORTANT : avant de lancer Ryu ou Flask, active l'environnement virtuel :"
echo "source venv/bin/activate"
echo ""
echo "Exemple :"
echo "cd ~/sdn_project"
echo "source venv/bin/activate"
echo "./scripts/run_controller.sh"