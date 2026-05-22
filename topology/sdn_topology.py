#!/usr/bin/env python3

# Import de l'interface CLI Mininet
from mininet.cli import CLI

# Import du type de lien avec possibilité de configurer bande passante, délai, pertes, etc.
from mininet.link import TCLink

# Import des fonctions de log Mininet
from mininet.log import setLogLevel, info

# Import de l'objet principal Mininet
from mininet.net import Mininet

# Import du contrôleur distant et du switch Open vSwitch
from mininet.node import RemoteController, OVSSwitch


def build_topology():
    """
    Crée une topologie SDN avec :
    - 1 contrôleur Ryu distant ;
    - 2 switches Open vSwitch en OpenFlow 1.3 ;
    - 5 hôtes : h1, h2, h3, h4 et web1 ;
    - un serveur HTTP simple lancé sur web1.
    """

    # Création du réseau Mininet sans contrôleur par défaut
    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )

    try:
        info("*** Ajout du contrôleur distant Ryu\n")

        # Le contrôleur Ryu doit être lancé sur le même port : 6653
        c0 = net.addController(
            "c0",
            controller=RemoteController,
            ip="127.0.0.1",
            port=6653
        )

        info("*** Création des switches OpenFlow 1.3\n")

        # Switches Open vSwitch configurés pour OpenFlow 1.3
        s1 = net.addSwitch("s1", protocols="OpenFlow13")
        s2 = net.addSwitch("s2", protocols="OpenFlow13")

        info("*** Création des hôtes\n")

        # Hôtes du réseau
        h1 = net.addHost("h1", ip="10.0.0.1/24")
        h2 = net.addHost("h2", ip="10.0.0.2/24")
        h3 = net.addHost("h3", ip="10.0.0.3/24")
        h4 = net.addHost("h4", ip="10.0.0.4/24")

        # Hôte utilisé comme serveur web
        web1 = net.addHost("web1", ip="10.0.0.100/24")

        info("*** Création des liens\n")

        # Switch s1 : h1, h2 et web1
        net.addLink(h1, s1)
        net.addLink(h2, s1)
        net.addLink(web1, s1)

        # Lien entre les deux switches
        net.addLink(s1, s2)

        # Switch s2 : h3 et h4
        net.addLink(h3, s2)
        net.addLink(h4, s2)

        info("*** Démarrage du réseau\n")

        # Construction du réseau
        net.build()

        # Démarrage du contrôleur
        c0.start()

        # Démarrage des switches avec le contrôleur Ryu
        s1.start([c0])
        s2.start([c0])

        info("*** Lancement du serveur web simple sur web1:80\n")

        # Lancement d'un serveur HTTP simple sur web1
        web1.cmd("cd /tmp && python3 -m http.server 80 >/tmp/web1-http.log 2>&1 &")

        info("*** Topologie prête\n")
        info("*** Commandes utiles :\n")
        info("    pingall\n")
        info("    h1 ping -c 4 h2\n")
        info("    h1 ping -c 4 web1\n")
        info("    h1 curl http://10.0.0.100\n")
        info("    sh ovs-ofctl dump-flows s1 -O OpenFlow13\n")
        info("    sh ovs-ofctl dump-flows s2 -O OpenFlow13\n")

        # Ouverture de la CLI Mininet
        CLI(net)

    finally:
        info("*** Arrêt du serveur web sur web1\n")

        # Arrêter le serveur web si web1 existe
        try:
            web1.cmd("pkill -f 'python3 -m http.server 80' || true")
        except Exception:
            pass

        info("*** Arrêt du réseau Mininet\n")

        # Nettoyage du réseau
        net.stop()


if __name__ == "__main__":
    # Niveau de log Mininet
    setLogLevel("info")

    # Construction et lancement de la topologie
    build_topology()