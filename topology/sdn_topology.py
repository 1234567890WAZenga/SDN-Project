#!/usr/bin/env python3
import contextlib
import io
import json
import shlex
import socket
import subprocess
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "topology_config.json"
MININET_API_PORT = 8090


def load_config():
    with CONFIG_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def wait_for_controller(host, port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


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


def node_ip(node):
    ip_address = node.IP()
    return ip_address.split("/")[0] if ip_address else ""


def translate_host_names(command, hosts):
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command

    translated = []
    for token in tokens:
        if token in hosts:
            translated.append(node_ip(hosts[token]))
        else:
            translated.append(token)

    return shlex.join(translated)


def make_command_handler(net, hosts, switches):
    class MininetCommandHandler(BaseHTTPRequestHandler):
        def _json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return False
            return True

        def do_OPTIONS(self):
            self._json({"ok": True})

        def do_GET(self):
            if self.path != "/api/status":
                self._json({"error": "not found"}, 404)
                return

            self._json(
                {
                    "ok": True,
                    "switches": sorted(switches.keys()),
                    "hosts": {
                        name: {"ip": node_ip(host), "mac": host.MAC()}
                        for name, host in sorted(hosts.items())
                    },
                    "commands": [
                        "pingall",
                        "nodes",
                        "net",
                        "links",
                        "dump",
                        "h1 ping -c 4 h2",
                        "h3 ping -c 4 h4",
                        "sh ovs-ofctl dump-flows s1 -O OpenFlow13",
                    ],
                }
            )

        def do_POST(self):
            if self.path != "/api/command":
                self._json({"error": "not found"}, 404)
                return

            length = int(self.headers.get("Content-Length", "0"))
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._json({"error": "invalid json"}, 400)
                return

            command = str(payload.get("command", "")).strip()
            if not command:
                self._json({"error": "empty command"}, 400)
                return

            try:
                output = execute_mininet_command(command, net, hosts, switches)
                response = {"ok": True, "command": command, "output": output}
                status = 200
            except Exception as error:
                response = {"ok": False, "command": command, "error": str(error)}
                status = 500

            self._json(response, status)

        def log_message(self, fmt, *args):
            return

    return MininetCommandHandler


def execute_mininet_command(command, net, hosts, switches):
    if command == "pingall":
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            loss = net.pingAll()
        output = buffer.getvalue()
        return output + f"\nPacket loss: {loss}%"

    if command == "nodes":
        return " ".join(sorted(net.nameToNode.keys()))

    if command == "net":
        return "\n".join(str(link) for link in net.links)

    if command == "links":
        return "\n".join(f"{link}: {link.status()}" for link in net.links)

    if command == "dump":
        lines = []
        for node in net.hosts + net.switches + net.controllers:
            lines.append(f"{node.name}: IP={node.IP()} MAC={node.MAC() if hasattr(node, 'MAC') else '-'}")
        return "\n".join(lines)

    parts = command.split(maxsplit=1)
    first = parts[0]
    rest = parts[1] if len(parts) > 1 else ""

    if first in hosts:
        if not rest:
            return f"{first}: no host command provided"
        translated = translate_host_names(rest, hosts)
        process = hosts[first].popen(translated, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            output, _ = process.communicate(timeout=25)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
            output += "\nCommand timeout after 25 seconds."
        return output.strip() or "(no output)"

    if first == "sh":
        if not rest:
            return "No shell command provided."
        process = subprocess.run(rest, shell=True, capture_output=True, text=True, timeout=25)
        output = (process.stdout or "") + (process.stderr or "")
        return output.strip() or f"(exit code {process.returncode})"

    if first.startswith("s") and first[1:].isdigit() and first in {f"s{key}" for key in switches}:
        return f"{first} is a switch. Use: sh ovs-ofctl dump-flows {first} -O OpenFlow13"

    return (
        "Commande non prise en charge par l'API Mininet.\n"
        "Utilise pingall, nodes, net, links, dump, une commande hôte comme 'h1 ping -c 4 h2', "
        "ou une commande shell préfixée par 'sh'."
    )


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def start_mininet_api(net, hosts, switches):
    handler = make_command_handler(net, hosts, switches)
    try:
        server = ReusableThreadingHTTPServer(("0.0.0.0", MININET_API_PORT), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        info(f"*** API Mininet disponible sur le port {MININET_API_PORT}\n")
        return server
    except OSError as error:
        info(f"*** ATTENTION : API Mininet indisponible sur le port {MININET_API_PORT} ({error})\n")
        info("*** La topologie continue, mais la console du dashboard ne pourra pas exécuter de commandes.\n")
        return None


def build_topology():
    config = load_config()
    controller = config["controller"]
    topology = config["topology"]
    controller_host = controller.get("host", "127.0.0.1")
    controller_port = int(controller.get("openflow_port", 6653))
    switch_count = int(topology.get("switches", 2))
    hosts_config = generate_hosts(config)

    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    started_servers = []
    api_server = None

    try:
        info(f"*** Vérification du contrôleur Ryu {controller_host}:{controller_port}\n")
        if not wait_for_controller(controller_host, controller_port):
            raise SystemExit(
                f"ERREUR : le contrôleur Ryu n'écoute pas sur {controller_host}:{controller_port}.\n"
                "Lance d'abord ./scripts/run_controller.sh dans un autre terminal et vérifie qu'il reste actif."
            )

        info("*** Ajout du contrôleur distant Ryu\n")
        c0 = net.addController(
            "c0",
            controller=RemoteController,
            ip=controller_host,
            port=controller_port,
        )

        info(f"*** Création de {switch_count} switches OpenFlow 1.3\n")
        switches = {
            switch_id: net.addSwitch(f"s{switch_id}", protocols="OpenFlow13")
            for switch_id in range(1, switch_count + 1)
        }

        info(f"*** Création de {len(hosts_config)} hôtes\n")
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

        api_server = start_mininet_api(net, hosts, switches)

        info("*** Topologie SDN prête\n")
        info("*** Commandes utiles : pingall, h1 ping -c 4 h2, h3 ping -c 4 h4\n")
        info("*** Pour voir OpenFlow : sh ovs-ofctl dump-flows s1 -O OpenFlow13\n")

        CLI(net)

    finally:
        info("*** Arrêt des services et nettoyage Mininet\n")
        try:
            api_server.shutdown()
            api_server.server_close()
        except Exception:
            pass
        for host in started_servers:
            host.cmd("pkill -f 'python3 -m http.server 80' || true")
        net.stop()


if __name__ == "__main__":
    setLogLevel("info")
    build_topology()
