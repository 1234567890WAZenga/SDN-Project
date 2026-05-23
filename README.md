# Implémentation d'une infrastructure réseau agile basée sur le SDN

Ce projet met en place une infrastructure SDN virtualisée avec **Mininet**, **Open vSwitch**, **Ryu**, **OpenFlow** et un **dashboard web Flask**.

L'objectif est de montrer concrètement comment fonctionne le SDN : les switches transportent les paquets, tandis qu'un contrôleur central prend les décisions, installe les règles OpenFlow, applique des politiques dynamiques et collecte les statistiques du réseau.

## Objectifs du projet

- Créer une topologie réseau virtuelle avec Mininet.
- Connecter des switches Open vSwitch à un contrôleur Ryu.
- Observer le fonctionnement `Packet-In` puis `Flow-Mod`.
- Installer dynamiquement des règles OpenFlow.
- Autoriser ou bloquer certains flux réseau.
- Collecter les statistiques de trafic : paquets, octets, protocoles, durée.
- Afficher l'état du réseau dans un dashboard.
- Rendre la topologie configurable : nombre de switches, hôtes et serveurs.

## Architecture SDN

```text
Dashboard Flask : http://IP_VM:3000
        |
        | API HTTP : port 8080
        v
Contrôleur Ryu
        |
        | OpenFlow : port 6653
        v
Open vSwitch / Mininet
        |
        v
Hôtes, switches et serveurs virtuels
```

Le projet sépare clairement :

- **Plan de contrôle** : le contrôleur Ryu prend les décisions.
- **Plan de données** : Open vSwitch applique les règles et transfère les paquets.

## Structure du projet

```text
sdn_project/
  controller/
    sdn_controller.py        # Contrôleur Ryu, API, règles et statistiques
  topology/
    sdn_topology.py          # Génération de la topologie Mininet
  dashboard/
    app.py                   # Serveur Flask du dashboard
    templates/index.html     # Interface web
    static/styles.css        # Style de l'interface
  policies/
    firewall_rules.json      # Règles dynamiques de blocage/autorisation
  scripts/
    install_ubuntu.sh        # Installation des dépendances
    run_controller.sh        # Lance Ryu
    run_topology.sh          # Lance Mininet
    run_dashboard.sh         # Lance Flask
  tests/
    test_commands.sh         # Commandes utiles de vérification
  topology_config.json       # Configuration de la topologie
  requirements.txt           # Dépendances Python
```

## Topologie configurable

La topologie est définie dans [topology_config.json](./topology_config.json).

Exemple actuel :

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

- `s1`, `s2`, `s3`;
- `h1` à `h6`;
- `web1` sur `10.0.0.100`;
- des liens inter-switches en topologie linéaire;
- un serveur HTTP simple sur `web1`.

L'adressage est généré automatiquement dans le réseau `10.0.0.0/24`.

## Installation dans Ubuntu

Le projet doit être exécuté dans une VM Ubuntu, car Mininet et Open vSwitch nécessitent Linux.

Depuis la racine du projet :

```bash
cd ~/sdn_project
chmod +x scripts/*.sh tests/*.sh
./scripts/install_ubuntu.sh
```

Vérifier les outils :

```bash
python3 --version
mn --version
ovs-vsctl --version
ryu-manager --version
```

## Lancement

Ouvrir trois terminaux dans `~/sdn_project`.

Terminal 1 : contrôleur Ryu

```bash
./scripts/run_controller.sh
```

Terminal 2 : topologie Mininet

```bash
sudo ./scripts/run_topology.sh
```

La topologie ouvre aussi une API locale sur le port `8090`. Cette API permet au dashboard d'exécuter des commandes Mininet dans la topologie active.

Important : le script de topologie ne lance plus `mn -c` automatiquement, car `mn -c` peut arrêter `ryu-manager`. Si un nettoyage complet est nécessaire, utilise :

```bash
sudo CLEAN_MININET=1 ./scripts/run_topology.sh
```

Après un nettoyage complet, relance le contrôleur Ryu si celui-ci a été arrêté.

Terminal 3 : dashboard

```bash
./scripts/run_dashboard.sh
```

Depuis la VM ou un autre poste du même réseau :

```text
http://IP_DE_LA_VM:3000
```

## Vérification du fonctionnement SDN

Depuis le dashboard, utiliser la section **Console Mininet** ou taper les commandes dans la console Mininet.

Commandes utiles :

```bash
pingall
h1 ping -c 4 h2
h1 ping -c 4 h6
h1 curl http://10.0.0.100
h2 curl http://10.0.0.100
nodes
net
links
dump
```

Afficher les règles OpenFlow :

```bash
sh ovs-ofctl dump-flows s1 -O OpenFlow13
sh ovs-ofctl dump-flows s2 -O OpenFlow13
sh ovs-ofctl dump-flows s3 -O OpenFlow13
```

Depuis le dashboard, les commandes OpenFlow doivent être préfixées par `sh`, par exemple :

```bash
sh ovs-ofctl dump-flows s1 -O OpenFlow13
```

## Ce que le dashboard doit montrer

Le dashboard sert à prouver le fonctionnement de l'infrastructure SDN.

Il doit afficher :

- contrôleur Ryu connecté;
- switches Open vSwitch connectés;
- hôtes détectés;
- console Mininet interactive;
- événements `Packet-In`;
- décisions du contrôleur;
- règles `Flow-Mod` installées;
- flux autorisés ou bloqués;
- compteurs de paquets et d'octets;
- trafic dans le temps;
- charge par switch;
- répartition par protocole;
- top communications;
- règles dynamiques actives.

## Politiques réseau

Les règles sont définies dans [policies/firewall_rules.json](./policies/firewall_rules.json).

Exemple :

```json
{
  "id": "block_h2_to_web",
  "enabled": true,
  "src_ip": "10.0.0.2",
  "dst_ip": "10.0.0.100",
  "proto": "any",
  "action": "deny",
  "description": "Bloquer H2 vers le serveur web"
}
```

Quand une règle est activée, le contrôleur installe une règle OpenFlow de priorité élevée dans les switches. Le trafic correspondant est bloqué sans modifier manuellement chaque switch.

## Preuves attendues

Le projet fonctionne correctement si :

- les switches apparaissent dans le dashboard;
- les hôtes apparaissent après `pingall`;
- les événements `Packet-In` apparaissent dans le journal;
- des règles `Flow-Mod` sont visibles;
- les compteurs augmentent quand du trafic est généré;
- le dashboard affiche des flux autorisés et bloqués;
- `ovs-ofctl dump-flows` montre les règles dans les switches;
- une politique dynamique change le comportement du réseau.

## Commandes de nettoyage

Si Mininet reste bloqué ou si une ancienne topologie continue d'exister :

```bash
sudo mn -c
sudo systemctl restart openvswitch-switch
```

Puis relancer :

```bash
./scripts/run_controller.sh
sudo ./scripts/run_topology.sh
./scripts/run_dashboard.sh
```

## Résultat attendu

À la fin, le projet démontre une infrastructure SDN :

- centralisée;
- programmable;
- configurable;
- supervisable;
- capable de gérer dynamiquement les flux réseau.

Cette infrastructure montre que le comportement du réseau peut être modifié depuis un contrôleur central, grâce aux règles OpenFlow, sans reconfigurer manuellement chaque équipement.
