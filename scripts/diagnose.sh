#!/bin/bash

set +e

cd "$(dirname "$0")/.."

echo "=== SDN PROJECT DIAGNOSTIC ==="
echo

echo "1) Dossier et branche Git"
pwd
git status --short 2>/dev/null || true
git log --oneline -1 2>/dev/null || true
echo

echo "2) Fichiers de configuration JSON"
for file in topology_config.json policies/firewall_rules.json; do
    if python3 -m json.tool "$file" >/dev/null 2>&1; then
        echo "OK : $file"
    else
        echo "ERREUR : $file invalide"
        python3 -m json.tool "$file" 2>&1 | head -5
    fi
done
echo

echo "3) Scripts et permissions"
for file in scripts/*.sh; do
    [ -e "$file" ] || continue
    if [ -x "$file" ]; then
        flag="OK"
    else
        flag="NON EXECUTABLE"
    fi

    first_line="$(head -1 "$file" | cat -v)"
    if echo "$first_line" | grep -q '\^M'; then
        line_status="CRLF A CORRIGER"
    else
        line_status="LF"
    fi

    echo "$flag | $line_status | $file"
done
echo

echo "4) Permission sudo dashboard"
restart_path="$(pwd)/scripts/restart_topology.sh"
if sudo -n -l "$restart_path" >/dev/null 2>&1; then
    echo "OK : sudo sans mot de passe autorise pour $restart_path"
else
    echo "ATTENTION : sudo sans mot de passe non confirme pour $restart_path"
    echo "Commande a lancer une fois : sudo ./scripts/install_dashboard_sudoers.sh"
fi
echo

echo "5) Processus importants"
pgrep -a -f "ryu-manager|sdn_controller.py|sdn_topology.py|dashboard/app.py" || echo "Aucun processus projet detecte."
echo

echo "6) Ports"
for port in 3000 6653 8080 8090; do
    if command -v ss >/dev/null 2>&1; then
        ss -ltnp 2>/dev/null | grep ":$port " || echo "Port $port : pas en ecoute"
    else
        netstat -ltnp 2>/dev/null | grep ":$port " || echo "Port $port : pas en ecoute"
    fi
done
echo

echo "7) Test controleur Ryu OpenFlow 127.0.0.1:6653"
python3 - <<'PY'
import socket
sock = socket.socket()
sock.settimeout(2)
try:
    sock.connect(("127.0.0.1", 6653))
    print("OK : Ryu ecoute sur 127.0.0.1:6653")
except OSError as exc:
    print(f"ERREUR : Ryu inaccessible sur 127.0.0.1:6653 ({exc})")
finally:
    sock.close()
PY
echo

echo "8) Interfaces Mininet restantes"
if command -v ip >/dev/null 2>&1; then
    leftovers="$(ip -o link show | awk -F': ' '{print $2}' | cut -d@ -f1 | grep -E '^[[:alnum:]_.-]+-eth[0-9]+$')"
    if [ -n "$leftovers" ]; then
        echo "$leftovers"
        echo "ATTENTION : lancer sudo ./scripts/restart_topology.sh ou sudo mn -c"
    else
        echo "OK : aucune interface Mininet restante"
    fi
fi
echo

echo "9) Bridges Open vSwitch"
if command -v ovs-vsctl >/dev/null 2>&1; then
    sudo ovs-vsctl list-br
    echo
    for bridge in $(sudo ovs-vsctl list-br); do
        echo "--- $bridge ---"
        echo "controllers:"
        sudo ovs-vsctl get-controller "$bridge"
        echo "flows:"
        sudo ovs-ofctl dump-flows "$bridge" -O OpenFlow13 2>/dev/null | head -20 || true
    done
else
    echo "ovs-vsctl introuvable."
fi
echo

echo "10) API locales"
python3 - <<'PY'
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
echo

echo "11) Dernieres lignes logs/topology.log"
if [ -f logs/topology.log ]; then
    tail -30 logs/topology.log
else
    echo "Aucun logs/topology.log"
fi
