#!/bin/bash

set -e

cd "$(dirname "$0")/.."

if [ "$EUID" -ne 0 ]; then
    echo "ERREUR : ce script doit etre lance avec sudo."
    echo "Utilise : sudo ./scripts/install_dashboard_sudoers.sh"
    exit 1
fi

DASHBOARD_USER="${SUDO_USER:-$USER}"
RESTART_SCRIPT="$(pwd)/scripts/restart_topology.sh"
SUDOERS_FILE="/etc/sudoers.d/sdn-dashboard"

chmod +x "$RESTART_SCRIPT"

cat > "$SUDOERS_FILE" <<EOF
$DASHBOARD_USER ALL=(root) NOPASSWD: $RESTART_SCRIPT
EOF

chmod 440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE"

echo "Permission installee pour $DASHBOARD_USER."
echo "Le dashboard peut maintenant relancer Mininet avec : sudo -n $RESTART_SCRIPT"
