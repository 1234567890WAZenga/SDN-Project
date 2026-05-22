# Projet SDN - Mininet, Ryu et Dashboard

Ce projet implemente une infrastructure SDN virtualisee avec Mininet, Open vSwitch, un controleur Ryu et un dashboard web Flask.

## Objectif

Montrer qu'un reseau peut etre gere dynamiquement depuis un controleur central:

- creation d'une topologie reseau virtuelle;
- communication entre hotes;
- installation automatique de regles OpenFlow;
- blocage ou autorisation de certains flux;
- collecte de statistiques;
- affichage des flux et metriques dans un dashboard.

## Architecture

```text
Dashboard Flask : http://adresse-vm:3000
        |
        | API HTTP
        v
Controleur Ryu
        |
        | OpenFlow
        v
Open vSwitch / Mininet
        |
        v
h1, h2, h3, h4, web1
```

## Structure

```text
sdn_project/
  controller/
    sdn_controller.py
  topology/
    sdn_topology.py
  dashboard/
    app.py
    templates/index.html
    static/styles.css
  policies/
    firewall_rules.json
  scripts/
    install_ubuntu.sh
    run_controller.sh
    run_topology.sh
  tests/
    test_commands.sh
  requirements.txt
```

## Installation Ubuntu

Dans la VM Ubuntu:

```bash
cd ~/sdn_project
chmod +x scripts/*.sh tests/*.sh
./scripts/install_ubuntu.sh
```

## Lancement

Terminal 1, lancer le controleur Ryu:

```bash
cd ~/sdn_project
./scripts/run_controller.sh
```

Terminal 2, lancer la topologie Mininet:

```bash
cd ~/sdn_project
sudo ./scripts/run_topology.sh
```

Terminal 3, lancer le dashboard:

```bash
cd ~/sdn_project
./scripts/run_dashboard.sh
```

Puis ouvrir depuis la VM ou un autre poste du meme reseau:

```text
http://ADRESSE_IP_DE_LA_VM:3000
```

## Tests utiles dans Mininet

```bash
pingall
h1 ping -c 4 h2
h2 ping -c 4 web1
h1 curl http://10.0.0.100
sh ovs-ofctl dump-flows s1 -O OpenFlow13
sh ovs-ofctl dump-flows s2 -O OpenFlow13
```

## Idee de demonstration

1. Lancer Ryu.
2. Lancer Mininet.
3. Ouvrir le dashboard.
4. Faire un `pingall`.
5. Observer les flux et les statistiques dans le dashboard.
6. Bloquer un flux depuis le dashboard.
7. Refaire le test et montrer que le trafic est bloque.
