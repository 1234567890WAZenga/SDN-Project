#!/bin/bash

set -Eeuo pipefail

cd "$(dirname "$0")/.."

PROJECT_DIR="$(pwd)"

info() {
    echo
    echo "=== $* ==="
}

fail() {
    echo "ERREUR : $*" >&2
    exit 1
}

require_ubuntu() {
    if [ ! -f /etc/os-release ]; then
        fail "systeme non reconnu. Ce script est prevu pour Ubuntu."
    fi

    . /etc/os-release
    if [ "${ID:-}" != "ubuntu" ]; then
        echo "ATTENTION : systeme detecte : ${PRETTY_NAME:-inconnu}."
        echo "Le projet est teste principalement sur Ubuntu 20.04/22.04."
    else
        echo "Systeme detecte : ${PRETTY_NAME:-Ubuntu}"
    fi
}

install_system_packages() {
    info "Mise a jour et installation des paquets systeme"
    sudo apt update
    sudo apt install -y \
        git curl wget nano vim xterm \
        net-tools iproute2 iputils-ping psmisc \
        tcpdump iperf iperf3 dos2unix \
        build-essential gcc make software-properties-common \
        python3 python3-pip python3-venv python3-dev python3-setuptools \
        python3-testresources libffi-dev libssl-dev libxml2-dev libxslt1-dev zlib1g-dev \
        openvswitch-switch openvswitch-common \
        mininet
}

prepare_scripts() {
    info "Preparation des scripts du projet"
    mkdir -p logs

    if command -v dos2unix >/dev/null 2>&1; then
        dos2unix scripts/*.sh >/dev/null 2>&1 || true
    else
        sed -i 's/\r$//' scripts/*.sh
    fi

    chmod +x scripts/*.sh
}

start_openvswitch() {
    info "Demarrage de Open vSwitch"
    sudo systemctl enable openvswitch-switch >/dev/null 2>&1 || true
    sudo systemctl restart openvswitch-switch || sudo service openvswitch-switch restart
    sudo ovs-vsctl --version | head -1
}

install_mininet_python_if_needed() {
    info "Verification du module Python Mininet"
    if /usr/bin/python3 -c "from mininet.cli import CLI; print('Mininet Python OK')" >/dev/null 2>&1; then
        echo "Mininet Python est disponible pour /usr/bin/python3."
    else
        echo "Module Python Mininet absent. Installation depuis les sources..."
        cd /tmp
        rm -rf mininet
        git clone https://github.com/mininet/mininet.git
        cd mininet
        git checkout 2.3.0
        sudo PYTHON=/usr/bin/python3 ./util/install.sh -n
        sudo /usr/bin/python3 -m pip install --force-reinstall --no-cache-dir .
        cd "$PROJECT_DIR"
    fi

    sudo /usr/bin/python3 -c "from mininet.cli import CLI; print('Mininet Python OK avec sudo')"
    mn --version || true
}

clean_mininet_once() {
    info "Nettoyage initial Mininet"
    sudo mn -c >/dev/null 2>&1 || true

    if command -v ip >/dev/null 2>&1; then
        ip -o link show \
            | awk -F': ' '{print $2}' \
            | cut -d@ -f1 \
            | grep -E '^[[:alnum:]_.-]+-eth[0-9]+$' \
            | while read -r intf; do
                sudo ip link delete "$intf" >/dev/null 2>&1 || true
            done || true
    fi

    if command -v ovs-vsctl >/dev/null 2>&1; then
        sudo ovs-vsctl --timeout=2 list-br 2>/dev/null \
            | grep -E '^s[0-9]+$' \
            | while read -r bridge; do
                sudo ovs-vsctl --if-exists del-br "$bridge" >/dev/null 2>&1 || true
            done || true
    fi
}

create_python_venv() {
    info "Creation de l'environnement virtuel Ryu/Flask"
    rm -rf venv
    python3 -m venv venv
    # shellcheck disable=SC1091
    source venv/bin/activate

    python -m pip install --upgrade --no-cache-dir \
        "pip==23.3.2" \
        "setuptools==67.7.2" \
        "wheel==0.41.3"

    python -m pip install --no-cache-dir --no-build-isolation \
        "dnspython==1.16.0" \
        "eventlet==0.30.2" \
        "ryu==4.34" \
        "Flask==2.3.3" \
        "requests==2.31.0"

    ryu-manager --version
}

validate_project_files() {
    info "Validation des fichiers de configuration"
    python3 -m json.tool topology_config.json >/dev/null
    python3 -m json.tool policies/firewall_rules.json >/dev/null
    python3 -m py_compile controller/sdn_controller.py dashboard/app.py topology/sdn_topology.py
}

install_dashboard_permission() {
    info "Installation de la permission sudo pour relancer Mininet depuis le dashboard"
    sudo ./scripts/install_dashboard_sudoers.sh
}

configure_firewall_if_active() {
    info "Pare-feu Ubuntu"
    if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
        sudo ufw allow 3000/tcp
        sudo ufw allow 6653/tcp
        sudo ufw allow 8080/tcp
        sudo ufw allow 8090/tcp
        sudo ufw status
    else
        echo "UFW inactif ou absent. Aucune regle ajoutee."
    fi
}

final_message() {
    info "Installation terminee"
    cat <<EOF
Commandes a retenir :

1) Lancer le controleur Ryu :
   ./scripts/run_controller.sh

2) Lancer le dashboard :
   ./scripts/run_dashboard.sh

3) Relancer Mininet proprement :
   sudo ./scripts/restart_topology.sh

4) Diagnostic :
   ./scripts/diagnose.sh

Depuis le navigateur Windows :
   http://IP_DE_LA_VM:3000

La page Configuration du dashboard peut maintenant sauvegarder la topologie,
executer un nettoyage Mininet complet, relancer la topologie et actualiser
l'affichage automatiquement.
EOF
}

require_ubuntu
install_system_packages
prepare_scripts
start_openvswitch
install_mininet_python_if_needed
clean_mininet_once
create_python_venv
validate_project_files
install_dashboard_permission
configure_firewall_if_active
final_message
