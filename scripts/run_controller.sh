#!/bin/bash

set -e

cd "$(dirname "$0")/.."

if [ ! -d "venv" ]; then
    echo "ERREUR : l'environnement virtuel n'existe pas."
    echo "Lance d'abord : ./scripts/install_ubuntu.sh"
    exit 1
fi

source venv/bin/activate

echo "Environnement virtuel active : $VIRTUAL_ENV"
echo "Python utilise : $(which python)"

python - <<'PY'
import sys

version = sys.version_info[:2]
if version not in ((3, 8), (3, 9)):
    print(f"ERREUR : ce venv utilise Python {sys.version.split()[0]}.")
    print("Ryu 4.34 avec eventlet 0.30.2 n'est pas compatible avec Python 3.12.")
    print("Recree le venv avec Python 3.8 ou 3.9 :")
    print("  FORCE_RECREATE_VENV=1 ./scripts/install_ubuntu.sh")
    raise SystemExit(1)

try:
    import eventlet
    from eventlet.wsgi import ALREADY_HANDLED
    import ryu
except Exception as exc:
    print(f"ERREUR : environnement Ryu invalide ({exc})")
    print("Recree le venv avec :")
    print("  FORCE_RECREATE_VENV=1 ./scripts/install_ubuntu.sh")
    raise SystemExit(1)
PY

echo "Lancement du controleur Ryu sur le port OpenFlow 6653..."

ryu-manager --ofp-tcp-listen-port 6653 controller/sdn_controller.py
