#!/bin/bash

set +e

cd "$(dirname "$0")/.."

echo "=== SDN PROJECT DIAGNOSTIC ==="
echo

echo "1) Processus importants"
pgrep -a -f "ryu-manager|sdn_controller.py|sdn_topology.py|dashboard/app.py" || echo "Aucun processus projet détecté."
echo

echo "2) Ports"
for port in 3000 6653 8080 8090; do
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | grep ":$port " || echo "Port $port : pas en écoute"
    else
        netstat -ltnp 2>/dev/null | grep ":$port " || echo "Port $port : pas en écoute"
    fi
done
echo

echo "3) Test contrôleur Ryu OpenFlow 127.0.0.1:6653"
python3 - <<'PY'
import socket
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", 6653))
    print("OK : Ryu écoute sur 127.0.0.1:6653")
except OSError as exc:
    print(f"ERREUR : Ryu inaccessible sur 127.0.0.1:6653 ({exc})")
finally:
    sock.close()
PY
echo

echo "4) Bridges Open vSwitch"
if command -v ovs-vsctl >/dev/null 2>&1; then
    sudo ovs-vsctl list-br
    echo
    for bridge in $(sudo ovs-vsctl list-br); do
        echo "--- $bridge ---"
        echo "controllers:"
        sudo ovs-vsctl get-controller "$bridge"
        echo "is-connected:"
        sudo ovs-vsctl get Controller "$(sudo ovs-vsctl get-controller "$bridge" 2>/dev/null)" is_connected 2>/dev/null || true
        echo "flows:"
        sudo ovs-ofctl dump-flows "$bridge" -O OpenFlow13 2>/dev/null | head -20 || true
    done
else
    echo "ovs-vsctl introuvable."
fi
echo

echo "5) API locales"
python3 - <<'PY'
import json
import urllib.request

for name, url in [
    ("Dashboard", "http://127.0.0.1:3000/"),
    ("Ryu API", "http://127.0.0.1:8080/api/state"),
    ("Mininet API", "http://127.0.0.1:8090/api/status"),
]:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            print(f"OK : {name} -> HTTP {response.status}")
    except Exception as exc:
        print(f"ERREUR : {name} inaccessible ({exc})")
PY
