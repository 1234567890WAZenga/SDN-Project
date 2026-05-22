#!/bin/bash

# Arrêter le script dès qu'une erreur apparaît
set -e

echo "=== Mise à jour du système ==="
sudo apt update
sudo apt upgrade -y

echo "=== Installation des paquets système de base ==="
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
xterm \
git \
nano \
software-properties-common

echo "=== Tentative d'installation du module Python Mininet via apt ==="

# Certains dépôts Ubuntu fournissent python3-mininet, d'autres non.
# On tente l'installation sans bloquer tout le script si le paquet n'existe pas.
if apt-cache show python3-mininet >/dev/null 2>&1; then
    sudo apt install -y python3-mininet
else
    echo "Paquet python3-mininet non disponible dans ce dépôt Ubuntu."
fi

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
zlib1g-dev

echo "=== Démarrage de Open vSwitch ==="
sudo service openvswitch-switch start

echo "=== Vérification du module Python Mininet ==="

# Si Python 3 ne trouve pas le module mininet, on installe Mininet depuis les sources.
if python3 -c "from mininet.cli import CLI; print('Mininet Python OK')" >/dev/null 2>&1; then
    echo "Mininet Python déjà disponible pour python3."
else
    echo "Module Python Mininet absent. Installation de Mininet depuis les sources..."

    cd /tmp
    rm -rf mininet

    git clone https://github.com/mininet/mininet.git
    cd mininet

    # Version stable classique de Mininet
    git checkout 2.3.0

    # Installer uniquement Mininet core + dépendances avec Python 3
    sudo PYTHON=python3 ./util/install.sh -n
fi

echo "=== Vérification finale de Mininet Python ==="
python3 -c "from mininet.cli import CLI; print('Mininet Python OK')"
sudo python3 -c "from mininet.cli import CLI; print('Mininet Python OK avec sudo')"

echo "=== Vérification de la commande mn ==="
mn --version || true

echo "=== Création de l'environnement virtuel Python pour Ryu et Flask ==="

# Retourner à la racine du projet
cd "$(dirname "$0")/.."

# Supprimer l'ancien environnement virtuel pour éviter les conflits
if [ -d "venv" ]; then
    echo "Ancien environnement virtuel détecté : suppression..."
    rm -rf venv
fi

# Créer l'environnement virtuel avec Python 3.8
python3.8 -m venv venv

echo "=== Activation de l'environnement virtuel ==="
source venv/bin/activate

echo "=== Vérification de Python utilisé dans l'environnement virtuel ==="
which python
python --version

echo "=== Installation des versions Python compatibles avec Ryu 4.34 ==="

# Versions figées pour éviter les erreurs avec Ryu
python -m pip install --force-reinstall --no-cache-dir \
"pip==23.3.2" \
"setuptools==67.7.2" \
"wheel==0.41.3"

# Installation de Ryu, Flask et dépendances compatibles
python -m pip install --no-cache-dir --no-build-isolation \
"dnspython==1.16.0" \
"eventlet==0.30.2" \
"ryu==4.34" \
"Flask==2.3.3" \
"requests==2.31.0"

echo "=== Vérification de Ryu ==="
ryu-manager --version

echo "=== Test Mininet ==="
sudo mn --test pingall
sudo mn -c

echo "=== Installation terminée ==="
echo ""
echo "IMPORTANT : Ryu et Flask utilisent l'environnement virtuel."
echo "Avant de lancer le contrôleur ou le dashboard, fais :"
echo ""
echo "cd ~/sdn_project"
echo "source venv/bin/activate"
echo ""
echo "Puis lance :"
echo "./scripts/run_controller.sh"
echo "./scripts/run_dashboard.sh"
echo ""
echo "Pour Mininet, n'utilise pas le venv. Lance :"
echo "sudo ./scripts/run_topology.sh"