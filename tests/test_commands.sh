#!/usr/bin/env bash
set -euo pipefail

echo "Commandes a executer dans le CLI Mininet:"
echo "  pingall"
echo "  h1 ping -c 4 h2"
echo "  h2 ping -c 4 web1"
echo "  h1 curl http://10.0.0.100"
echo "  sh ovs-ofctl dump-flows s1 -O OpenFlow13"
echo "  sh ovs-ofctl dump-flows s2 -O OpenFlow13"
