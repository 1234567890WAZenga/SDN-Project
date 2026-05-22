#!/usr/bin/env python3
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch


def build_topology():
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)

    info("*** Ajout du controleur distant Ryu\n")
    c0 = net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6633,
    )

    info("*** Creation des switches OpenFlow\n")
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    s2 = net.addSwitch("s2", protocols="OpenFlow13")

    info("*** Creation des hotes\n")
    h1 = net.addHost("h1", ip="10.0.0.1/24")
    h2 = net.addHost("h2", ip="10.0.0.2/24")
    h3 = net.addHost("h3", ip="10.0.0.3/24")
    h4 = net.addHost("h4", ip="10.0.0.4/24")
    web1 = net.addHost("web1", ip="10.0.0.100/24")

    info("*** Creation des liens\n")
    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(web1, s1)
    net.addLink(s1, s2)
    net.addLink(h3, s2)
    net.addLink(h4, s2)

    info("*** Demarrage du reseau\n")
    net.build()
    c0.start()
    s1.start([c0])
    s2.start([c0])

    info("*** Lancement d'un serveur web simple sur web1:80\n")
    web1.cmd("python3 -m http.server 80 >/tmp/web1-http.log 2>&1 &")

    info("*** Topologie prete\n")
    info("*** Commandes utiles: pingall, h1 ping h2, h1 curl http://10.0.0.100\n")
    CLI(net)

    info("*** Arret du reseau\n")
    web1.cmd("pkill -f 'python3 -m http.server 80' || true")
    net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
