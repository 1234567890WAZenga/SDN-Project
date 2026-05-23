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
  topology_config.json
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

## Topologie configurable

La topologie est définie dans `topology_config.json`.

Paramètres importants :

```json
{
  "topology": {
    "type": "linear",
    "switches": 3,
    "hosts_per_switch": 2,
    "servers": [
      {
        "name": "web1",
        "label": "Serveur Web",
        "switch": 1,
        "service": "http",
        "ip_last_octet": 100
      }
    ]
  }
}
```

Avec cette configuration, Mininet crée automatiquement :

- 3 switches : `s1`, `s2`, `s3` ;
- 2 hôtes par switch : `h1` à `h6` ;
- 1 serveur web : `web1` avec l'adresse `10.0.0.100`.

L'adressage est automatique dans `10.0.0.0/24`.

## Idee de demonstration

1. Lancer Ryu.
2. Lancer Mininet.
3. Ouvrir le dashboard.
4. Faire un `pingall`.
5. Observer les flux et les statistiques dans le dashboard.
6. Bloquer un flux depuis le dashboard.
7. Refaire le test et montrer que le trafic est bloque.

## Ce que le dashboard prouve

Le dashboard montre le fonctionnement SDN à travers :

- les switches connectés au contrôleur Ryu ;
- les hôtes détectés par les paquets ;
- les événements `Packet-In` ;
- les décisions du contrôleur ;
- les règles `Flow-Mod` installées ;
- les flux autorisés ou bloqués ;
- les compteurs de paquets et d'octets ;
- les graphiques de trafic, protocoles et charge par switch.
