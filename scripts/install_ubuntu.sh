#!/bin/bash

# Arrêter le script dès qu'une erreur apparaît
set -e

echo "=================================================="
echo " Installation Ubuntu pour projet SDN"
echo " Mininet + Open vSwitch + Ryu + Dashboard Flask"
echo "=================================================="

echo ""
echo "=== Mise à jour du système ==="
sudo apt update
sudo apt upgrade -y

echo ""
echo "=== Installation des paquets système de base ==="
sudo apt install -y \
git \
curl \
wget \
nano \
vim \
xterm \
net-tools \
iproute2 \
iputils-ping \
tcpdump \
iperf \
build-essential \
gcc \
make \
software-properties-common

echo ""
echo "=== Installation de Open vSwitch ==="
sudo apt install -y \
openvswitch-switch \
openvswitch-common

echo ""
echo "=== Démarrage de Open vSwitch ==="
sudo service openvswitch-switch start

echo ""
echo "=== Installation de Python 3.8 et dépendances Python ==="
sudo apt install -y \
python3.8 \
python3.8-venv \
python3.8-dev \
python3-pip \
python3-setuptools \
python3-dev \
python3-testresources \
libffi-dev \
libssl-dev \
libxml2-dev \
libxslt1-dev \
zlib1g-dev

echo ""
echo "=== Installation de Mininet via apt ==="

# Installer Mininet depuis les dépôts Ubuntu
sudo apt install -y mininet

# Installer python3-mininet si le paquet existe dans le dépôt Ubuntu
if apt-cache show python3-mininet >/dev/null 2>&1; then
    echo "Paquet python3-mininet disponible : installation..."
    sudo apt install -y python3-mininet
else
    echo "Paquet python3-mininet non disponible dans ce dépôt."
fi

echo ""
echo "=== Vérification du module Python Mininet ==="

# Vérifier si le module Python mininet est disponible
if /usr/bin/python3 -c "from mininet.cli import CLI; print('Mininet Python OK')" >/dev/null 2>&1; then
    echo "Mininet Python est déjà disponible pour /usr/bin/python3."
else
    echo "Module Python Mininet absent."
    echo "Installation de Mininet depuis les sources..."

    cd /tmp
    rm -rf mininet

    # Télécharger Mininet depuis le dépôt officiel
    git clone https://github.com/mininet/mininet.git
    cd mininet

    # Utiliser une version stable classique
    git checkout 2.3.0

    # Installer Mininet core avec Python 3
    sudo PYTHON=/usr/bin/python3 ./util/install.sh -n

    echo ""
    echo "=== Installation forcée du module Python Mininet ==="

    # Installer explicitement le module Python Mininet pour /usr/bin/python3
    sudo /usr/bin/python3 -m pip install --force-reinstall --no-cache-dir .

    echo ""
    echo "=== Vérification après installation depuis les sources ==="
    /usr/bin/python3 -c "from mininet.cli import CLI; print('Mininet Python OK')"
fi

echo ""
echo "=== Vérification Mininet avec sudo ==="
sudo /usr/bin/python3 -c "from mininet.cli import CLI; print('Mininet Python OK avec sudo')"

echo ""
echo "=== Vérification de la commande mn ==="
mn --version || true

echo ""
echo "=== Test rapide de Mininet ==="
sudo mn --test pingall
sudo mn -c

echo ""
echo "=== Création de l'environnement virtuel pour Ryu et Flask ==="

# Retourner à la racine du projet
cd "$(dirname "$0")/.."

# Supprimer l'ancien environnement virtuel pour éviter les conflits
if [ -d "venv" ]; then
    echo "Ancien environnement virtuel détecté : suppression..."
    rm -rf venv
fi

# Créer l'environnement virtuel avec Python 3.8
python3.8 -m venv venv

echo ""
echo "=== Activation de l'environnement virtuel ==="
source venv/bin/activate

echo ""
echo "=== Vérification de Python dans le venv ==="
which python
python --version

echo ""
echo "=== Installation des versions compatibles avec Ryu 4.34 ==="

# Versions figées pour éviter les erreurs setuptools / Ryu
python -m pip install --force-reinstall --no-cache-dir \
"pip==23.3.2" \
"setuptools==67.7.2" \
"wheel==0.41.3"

# Dépendances compatibles avec Ryu 4.34
python -m pip install --no-cache-dir --no-build-isolation \
"dnspython==1.16.0" \
"eventlet==0.30.2" \
"ryu==4.34" \
"Flask==2.3.3" \
"requests==2.31.0"

echo ""
echo "=== Vérification de Ryu ==="
ryu-manager --version

echo ""
echo "=================================================="
echo " Installation terminée"
echo "=================================================="

echo ""
echo "IMPORTANT : Ryu et Flask utilisent l'environnement virtuel."
echo ""
echo "Avant de lancer le contrôleur Ryu ou le dashboard Flask :"
echo ""
echo "cd ~/SDN-Project"
echo "source venv/bin/activate"
echo ""
echo "Puis lance :"
echo "./scripts/run_controller.sh"
echo "./scripts/run_dashboard.sh"
echo ""
echo "Pour Mininet, n'utilise pas le venv."
echo "Lance simplement :"
echo ""
echo "cd ~/SDN-Project"
echo "sudo ./scripts/run_topology.sh"
echo ""
echo "Rappel :"
echo "Ryu + Flask  -> venv"
echo "Mininet      -> sudo + /usr/bin/python3"