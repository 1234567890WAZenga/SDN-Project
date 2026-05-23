#!/usr/bin/env python3
import json
from pathlib import Path

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "topology_config.json"


def load_config():
    with CONFIG_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def host_ip(config, last_octet):
    prefix = config["addressing"].get("host_prefix", "10.0.0.")
    return f"{prefix}{last_octet}/24"


def generate_hosts(config):
    topology = config["topology"]
    addressing = config["addressing"]
    switch_count = int(topology.get("switches", 2))
    hosts_per_switch = int(topology.get("hosts_per_switch", 2))
    next_host = int(addressing.get("host_start", 1))

    hosts = []
    for switch_id in range(1, switch_count + 1):
        for _ in range(hosts_per_switch):
            hosts.append(
                {
                    "name": f"h{next_host}",
                    "label": f"H{next_host}",
                    "switch": switch_id,
                    "ip": host_ip(config, next_host),
                    "service": "client",
                }
            )
            next_host += 1

    for server in topology.get("servers", []):
        last_octet = int(server.get("ip_last_octet", addressing.get("server_start", 100)))
        hosts.append(
            {
                "name": server["name"],
                "label": server.get("label", server["name"]),
                "switch": int(server.get("switch", 1)),
                "ip": host_ip(config, last_octet),
                "service": server.get("service", "server"),
            }
        )

    return hosts


def build_topology():
    config = load_config()
    controller = config["controller"]
    topology = config["topology"]
    switch_count = int(topology.get("switches", 2))
    hosts_config = generate_hosts(config)

    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    started_servers = []

    try:
        info("*** Ajout du contrôleur distant Ryu\n")
        c0 = net.addController(
            "c0",
            controller=RemoteController,
            ip=controller.get("host", "127.0.0.1"),
            port=int(controller.get("openflow_port", 6653)),
        )

        info(f"*** Création de {switch_count} switches OpenFlow 1.3\n")
        switches = {
            switch_id: net.addSwitch(f"s{switch_id}", protocols="OpenFlow13")
            for switch_id in range(1, switch_count + 1)
        }

        info(f"*** Création de {len(hosts_config)} hôtes/serveurs\n")
        hosts = {}
        for host_cfg in hosts_config:
            host = net.addHost(host_cfg["name"], ip=host_cfg["ip"])
            hosts[host_cfg["name"]] = host
            net.addLink(host, switches[int(host_cfg["switch"])])
            info(f"    {host_cfg['name']} ({host_cfg['label']}) -> s{host_cfg['switch']} / {host_cfg['ip']}\n")

        info("*** Création des liens inter-switches\n")
        for switch_id in range(1, switch_count):
            net.addLink(switches[switch_id], switches[switch_id + 1])
            info(f"    s{switch_id} -- s{switch_id + 1}\n")

        info("*** Démarrage du réseau\n")
        net.build()
        c0.start()
        for switch in switches.values():
            switch.start([c0])

        for host_cfg in hosts_config:
            if host_cfg.get("service") == "http":
                host = hosts[host_cfg["name"]]
                info(f"*** Lancement HTTP sur {host_cfg['name']}:80\n")
                host.cmd("cd /tmp && python3 -m http.server 80 >/tmp/mininet-http.log 2>&1 &")
                started_servers.append(host)

        info("*** Topologie SDN prête\n")
        info("*** Commandes utiles : pingall, h1 ping -c 4 h2, h1 curl http://10.0.0.100\n")
        info("*** Pour voir OpenFlow : sh ovs-ofctl dump-flows s1 -O OpenFlow13\n")

        CLI(net)

    finally:
        info("*** Arrêt des services et nettoyage Mininet\n")
        for host in started_servers:
            host.cmd("pkill -f 'python3 -m http.server 80' || true")
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
