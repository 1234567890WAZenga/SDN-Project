# Implémentation d'une infrastructure réseau agile basée sur le SDN

Ce projet met en place une infrastructure SDN virtualisée avec **Mininet**, **Open vSwitch**, **Ryu**, **OpenFlow** et un **dashboard Flask**.

L'objectif est de montrer comment un réseau SDN fonctionne : le contrôleur Ryu prend les décisions, les switches Open vSwitch appliquent les règles OpenFlow, et le dashboard permet de visualiser, tester et gérer le réseau.

## Architecture

```text
Navigateur : http://IP_VM:3000
        |
        v
Dashboard Flask
        |
        +--> API Ryu : état, flux, règles, événements
        |
        +--> API Mininet : commandes et état de la topologie

Contrôleur Ryu
        |
        | OpenFlow 1.3
        v
Open vSwitch / Mininet
        |
        v
Hôtes virtuels h1, h2, h3...
```

## Rôle du dashboard

Le dashboard a trois rôles simples :

- **Visualiser** : contrôleur, switches, hôtes, flux OpenFlow et événements.
- **Tester** : lancer des commandes Mininet comme `pingall` ou `h1 ping -c 4 h2`.
- **Gérer** : configurer la topologie et créer des règles SDN dynamiques.

## Structure du projet

```text
sdn_project/
  controller/sdn_controller.py      # Contrôleur Ryu, API, règles, statistiques
  topology/sdn_topology.py          # Topologie Mininet configurable
  dashboard/app.py                  # Serveur Flask
  dashboard/templates/index.html    # Interface du dashboard
  dashboard/static/styles.css       # Style du dashboard
  policies/firewall_rules.json      # Règles SDN dynamiques
  scripts/install_ubuntu.sh         # Installation Ubuntu
  scripts/run_controller.sh         # Lance Ryu
  scripts/run_topology.sh           # Lance Mininet
  scripts/run_dashboard.sh          # Lance Flask
  scripts/diagnose.sh               # Diagnostic des services
  topology_config.json              # Nombre de switches et hôtes
  requirements.txt                  # Dépendances Python
```

## Topologie configurable

La topologie est définie dans `topology_config.json`.

Exemple :

```json
{
  "topology": {
    "type": "linear",
    "switches": 3,
    "hosts_per_switch": 2,
    "servers": []
  }
}
```

Avec cette configuration, Mininet crée :

- `s1`, `s2`, `s3` ;
- `h1` à `h6` ;
- des liens inter-switches en topologie linéaire ;
- un adressage automatique dans `10.0.0.0/24`.

## Lancement

Dans la VM Ubuntu, ouvrir trois terminaux.

Terminal 1 :

```bash
./scripts/run_controller.sh
```

Terminal 2 :

```bash
sudo ./scripts/run_topology.sh
```

Terminal 3 :

```bash
./scripts/run_dashboard.sh
```

Puis ouvrir :

```text
http://IP_DE_LA_VM:3000
```

## Relance Mininet depuis le dashboard

Pour que la page Configuration puisse sauvegarder puis relancer Mininet automatiquement, installer une fois la permission sudo dediee :

```bash
chmod +x scripts/restart_topology.sh scripts/install_dashboard_sudoers.sh
sudo ./scripts/install_dashboard_sudoers.sh
```

Ensuite, depuis le dashboard :

1. ouvrir la page `Configuration` ;
2. modifier le nombre de switches ou d'hotes ;
3. cliquer sur `Sauvegarder`.

Le dashboard sauvegarde `topology_config.json`, relance Mininet en arriere-plan et actualise la topologie.

La relance peut aussi etre faite manuellement :

```bash
sudo ./scripts/restart_topology.sh
```

## Commandes de démonstration

Depuis le dashboard ou la console Mininet :

```bash
pingall
h1 ping -c 4 h2
h1 ping -c 4 h6
h3 ping -c 4 h4
nodes
net
links
dump
```

Pour voir les règles OpenFlow :

```bash
sh ovs-ofctl dump-flows s1 -O OpenFlow13
sh ovs-ofctl dump-flows s2 -O OpenFlow13
sh ovs-ofctl dump-flows s3 -O OpenFlow13
```

## Exemple de règle SDN

Les règles sont stockées dans `policies/firewall_rules.json`.

Exemple :

```json
{
  "id": "block_h3_to_h4_icmp",
  "enabled": true,
  "src_ip": "10.0.0.3",
  "dst_ip": "10.0.0.4",
  "proto": "icmp",
  "action": "deny",
  "description": "Bloquer ICMP de H3 vers H4"
}
```

Cette règle montre que le contrôleur peut modifier le comportement du réseau sans configurer manuellement chaque switch.

## Preuves attendues

Le projet est validé si :

- les switches apparaissent dans le dashboard ;
- les hôtes apparaissent après `pingall` ;
- les événements `Packet-In`, décision et `Flow-Mod` apparaissent ;
- les flux OpenFlow sont visibles avec `dump-flows` ;
- une règle dynamique bloque réellement une communication ;
- les compteurs de paquets changent quand du trafic est généré.

## Diagnostic

```bash
./scripts/diagnose.sh
```

Ce script vérifie les processus, ports, bridges Open vSwitch, flux OpenFlow et API locales.

## Nettoyage

Si Mininet reste bloqué :

```bash
sudo mn -c
sudo systemctl restart openvswitch-switch
```

Puis relancer Ryu, Mininet et le dashboard.
