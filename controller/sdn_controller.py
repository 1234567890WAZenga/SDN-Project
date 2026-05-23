#!/usr/bin/env python3

"""
Contrôleur SDN Ryu pour le projet :
Mininet + Open vSwitch + Ryu + Dashboard Flask.

Fonctions principales :
- apprentissage MAC ;
- forwarding L2 simple ;
- application de règles firewall dynamiques ;
- collecte des statistiques OpenFlow ;
- API HTTP interne pour le dashboard.
"""

import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ether_types, ethernet, ipv4, packet
from ryu.ofproto import ofproto_v1_3


# Racine du projet
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Fichier des règles firewall
POLICY_FILE = os.path.join(BASE_DIR, "policies", "firewall_rules.json")
TOPOLOGY_CONFIG_FILE = os.path.join(BASE_DIR, "topology_config.json")

def load_topology_config():
    """
    Charge la configuration partagee par Mininet, Ryu et le dashboard.
    """

    default_config = {
        "name": "Infrastructure SDN agile",
        "controller": {"api_port": 8080},
        "addressing": {"host_prefix": "10.0.0.", "host_start": 1, "server_start": 100},
        "topology": {"type": "linear", "switches": 2, "hosts_per_switch": 2, "servers": []},
    }

    if not os.path.exists(TOPOLOGY_CONFIG_FILE):
        return default_config

    try:
        with open(TOPOLOGY_CONFIG_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default_config


def build_expected_hosts(config):
    """
    Genere les hotes attendus et leur adressage IP automatique.
    """

    topology = config.get("topology", {})
    addressing = config.get("addressing", {})
    prefix = addressing.get("host_prefix", "10.0.0.")
    switch_count = int(topology.get("switches", 2))
    hosts_per_switch = int(topology.get("hosts_per_switch", 2))
    next_host = int(addressing.get("host_start", 1))
    expected = []

    for switch_id in range(1, switch_count + 1):
        for _ in range(hosts_per_switch):
            expected.append(
                {
                    "name": f"h{next_host}",
                    "label": f"H{next_host}",
                    "ip": f"{prefix}{next_host}",
                    "switch": switch_id,
                    "service": "client",
                }
            )
            next_host += 1

    for server in topology.get("servers", []):
        last_octet = int(server.get("ip_last_octet", addressing.get("server_start", 100)))
        expected.append(
            {
                "name": server.get("name", f"srv{last_octet}"),
                "label": server.get("label", server.get("name", f"Serveur {last_octet}")),
                "ip": f"{prefix}{last_octet}",
                "switch": int(server.get("switch", 1)),
                "service": server.get("service", "server"),
            }
        )

    return expected


TOPOLOGY_CONFIG = load_topology_config()
EXPECTED_HOSTS = build_expected_hosts(TOPOLOGY_CONFIG)
HOST_NAMES = {host["ip"]: host["label"] for host in EXPECTED_HOSTS}


# État global exposé au dashboard
STATE = {
    "started_at": time.time(),
    "switches": {},
    "hosts": {},
    "events": [],
    "flows": [],
    "rules": [],
    "topology": {
        "name": TOPOLOGY_CONFIG.get("name", "Infrastructure SDN agile"),
        "type": TOPOLOGY_CONFIG.get("topology", {}).get("type", "linear"),
        "switches": int(TOPOLOGY_CONFIG.get("topology", {}).get("switches", 2)),
        "expected_hosts": EXPECTED_HOSTS,
    },
    "summary": {
        "allowed_flows": 0,
        "blocked_flows": 0,
        "total_packets": 0,
        "total_bytes": 0,
        "by_switch": {},
        "by_protocol": {},
        "top_flows": [],
        "history": [],
    },
}


# Verrou pour sécuriser les accès concurrents à STATE
STATE_LOCK = threading.Lock()

# Référence globale vers l'application Ryu
CONTROLLER_APP = None


def add_event(message, event_type="info", meta=None):
    """
    Ajoute un événement visible depuis le dashboard.
    """

    with STATE_LOCK:
        STATE["events"].insert(
            0,
            {
                "time": time.strftime("%H:%M:%S"),
                "type": event_type,
                "message": message,
                "meta": meta or {},
            },
        )

        # Garder seulement les 80 derniers événements
        STATE["events"] = STATE["events"][:80]


def load_rules():
    """
    Charge les règles firewall depuis policies/firewall_rules.json.
    """

    if not os.path.exists(POLICY_FILE):
        return []

    try:
        with open(POLICY_FILE, "r", encoding="utf-8") as handle:
            return json.load(handle)

    except json.JSONDecodeError:
        add_event("Erreur : fichier firewall_rules.json invalide")
        return []


def save_rules(rules):
    """
    Sauvegarde les règles firewall.
    """

    os.makedirs(os.path.dirname(POLICY_FILE), exist_ok=True)

    with open(POLICY_FILE, "w", encoding="utf-8") as handle:
        json.dump(rules, handle, indent=2)


def validate_rule_payload(data, existing_rule=None):
    """
    Valide et normalise une regle saisie depuis le dashboard.
    """

    rule = dict(existing_rule or {})
    rule["id"] = rule.get("id") or f"rule_{int(time.time() * 1000)}"
    rule["description"] = str(data.get("description") or rule.get("description") or "Regle SDN").strip()[:80]
    rule["src_ip"] = str(data.get("src_ip") or "").strip()
    rule["dst_ip"] = str(data.get("dst_ip") or "").strip()
    rule["proto"] = str(data.get("proto") or rule.get("proto") or "any").strip().lower()
    rule["action"] = str(data.get("action") or rule.get("action") or "deny").strip().lower()
    rule["enabled"] = bool(data.get("enabled", rule.get("enabled", True)))

    ip_pattern = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
    for field in ("src_ip", "dst_ip"):
        value = rule[field]
        if value and not ip_pattern.match(value):
            raise ValueError(f"{field} invalide")
        if value:
            octets = [int(part) for part in value.split(".")]
            if any(octet < 0 or octet > 255 for octet in octets):
                raise ValueError(f"{field} invalide")

    if not rule["src_ip"] and not rule["dst_ip"]:
        raise ValueError("Definis au moins une IP source ou destination.")

    if rule["proto"] not in {"any", "icmp", "tcp", "udp"}:
        raise ValueError("Protocole invalide.")

    if rule["action"] != "deny":
        raise ValueError("Seules les regles deny sont supportees pour le moment.")

    return rule


def ip_proto_name(proto):
    """
    Convertit un numéro de protocole IP en texte.
    """

    if proto == 1:
        return "icmp"

    if proto == 6:
        return "tcp"

    if proto == 17:
        return "udp"

    return "any"


def host_label(ip_address):
    """
    Retourne un nom lisible pour une adresse IP Mininet.
    """

    if not ip_address:
        return "*"

    return HOST_NAMES.get(ip_address, ip_address)


def build_summary(flows, previous_history=None):
    """
    Agrege les flux pour alimenter les graphiques du dashboard.
    """

    by_switch = {}
    by_protocol = {}
    total_packets = 0
    total_bytes = 0

    expected_switches = int(TOPOLOGY_CONFIG.get("topology", {}).get("switches", 0))
    for switch_id in range(1, expected_switches + 1):
        by_switch[f"S{switch_id}"] = {"flows": 0, "packets": 0, "bytes": 0}

    for flow in flows:
        switch_key = f"S{flow.get('switch')}"
        proto_key = flow.get("proto") or "any"
        packets = int(flow.get("packets") or 0)
        byte_count = int(flow.get("bytes") or 0)

        total_packets += packets
        total_bytes += byte_count

        by_switch.setdefault(switch_key, {"flows": 0, "packets": 0, "bytes": 0})
        by_switch[switch_key]["flows"] += 1
        by_switch[switch_key]["packets"] += packets
        by_switch[switch_key]["bytes"] += byte_count

        by_protocol.setdefault(proto_key, {"flows": 0, "packets": 0, "bytes": 0})
        by_protocol[proto_key]["flows"] += 1
        by_protocol[proto_key]["packets"] += packets
        by_protocol[proto_key]["bytes"] += byte_count

    history = list(previous_history or [])
    history.append(
        {
            "time": time.strftime("%H:%M:%S"),
            "packets": total_packets,
            "bytes": total_bytes,
            "flows": len(flows),
        }
    )
    history = history[-24:]

    top_flows = sorted(flows, key=lambda item: int(item.get("packets") or 0), reverse=True)[:5]

    return {
        "allowed_flows": sum(1 for flow in flows if flow.get("action") == "autorise"),
        "blocked_flows": sum(1 for flow in flows if flow.get("action") == "bloque"),
        "total_packets": total_packets,
        "total_bytes": total_bytes,
        "by_switch": by_switch,
        "by_protocol": by_protocol,
        "top_flows": top_flows,
        "history": history,
    }


class DashboardApiHandler(BaseHTTPRequestHandler):
    """
    API HTTP interne utilisée par le dashboard.

    Routes :
    - GET  /api/state
    - GET  /api/rules
    - POST /api/rules/create
    - POST /api/rules/toggle
    - POST /api/rules/delete
    """

    def _send_json(self, payload, status=200):
        """
        Envoie une réponse JSON.
        """

        body = json.dumps(payload).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)

    def do_OPTIONS(self):
        """
        Réponse CORS preflight.
        """

        self._send_json({"ok": True})

    def do_GET(self):
        """
        Gère les requêtes GET.
        """

        path = urlparse(self.path).path

        if path == "/api/state":
            with STATE_LOCK:
                payload = dict(STATE)
                payload["uptime_seconds"] = int(time.time() - STATE["started_at"])

            self._send_json(payload)
            return

        if path == "/api/rules":
            self._send_json({"rules": load_rules()})
            return

        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        """
        Gère les requêtes POST.
        """

        global CONTROLLER_APP

        path = urlparse(self.path).path

        if path == "/api/rules/toggle":
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")

            try:
                data = json.loads(raw_body or "{}")

            except json.JSONDecodeError:
                self._send_json({"error": "invalid json"}, 400)
                return

            rule_id = data.get("id")

            rules = load_rules()
            changed = False

            for rule in rules:
                if rule.get("id") == rule_id:
                    rule["enabled"] = not bool(rule.get("enabled"))
                    changed = True

                    status = "activee" if rule["enabled"] else "desactivee"
                    add_event(
                        f"Politique dynamique : {rule_id} -> {status}",
                        "policy_toggle",
                        {"rule_id": rule_id, "enabled": rule["enabled"]},
                    )

                    break

            if not changed:
                self._send_json({"error": "rule not found"}, 404)
                return

            save_rules(rules)

            with STATE_LOCK:
                STATE["rules"] = rules

            # Réinstaller les règles sur les switches connectés
            if CONTROLLER_APP:
                CONTROLLER_APP.install_policy_rules()

            self._send_json({"ok": True, "rules": rules})
            return

        if path == "/api/rules/create":
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")

            try:
                data = json.loads(raw_body or "{}")
                new_rule = validate_rule_payload(data)

            except json.JSONDecodeError:
                self._send_json({"error": "invalid json"}, 400)
                return

            except ValueError as error:
                self._send_json({"error": str(error)}, 400)
                return

            rules = load_rules()
            rules.append(new_rule)
            save_rules(rules)

            with STATE_LOCK:
                STATE["rules"] = rules

            add_event(
                f"Nouvelle politique : {new_rule['description']} ({host_label(new_rule.get('src_ip'))} -> {host_label(new_rule.get('dst_ip'))})",
                "policy_create",
                {"rule_id": new_rule["id"]},
            )

            if CONTROLLER_APP:
                CONTROLLER_APP.install_policy_rules()

            self._send_json({"ok": True, "rules": rules, "rule": new_rule})
            return

        if path == "/api/rules/delete":
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")

            try:
                data = json.loads(raw_body or "{}")

            except json.JSONDecodeError:
                self._send_json({"error": "invalid json"}, 400)
                return

            rule_id = data.get("id")
            rules = load_rules()
            updated_rules = [rule for rule in rules if rule.get("id") != rule_id]

            if len(updated_rules) == len(rules):
                self._send_json({"error": "rule not found"}, 404)
                return

            save_rules(updated_rules)

            with STATE_LOCK:
                STATE["rules"] = updated_rules

            add_event(
                f"Politique supprimee : {rule_id}",
                "policy_delete",
                {"rule_id": rule_id},
            )

            if CONTROLLER_APP:
                CONTROLLER_APP.install_policy_rules()

            self._send_json({"ok": True, "rules": updated_rules})
            return

        self._send_json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        """
        Désactive les logs HTTP par défaut.
        """

        return


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    """
    Serveur HTTP réutilisable pour éviter certains blocages après redémarrage.
    """

    allow_reuse_address = True


def start_api_server():
    """
    Lance l'API HTTP interne du contrôleur sur le port 8080.
    """

    try:
        api_port = int(TOPOLOGY_CONFIG.get("controller", {}).get("api_port", 8080))
        server = ReusableThreadingHTTPServer(("0.0.0.0", api_port), DashboardApiHandler)
        add_event(f"API controleur disponible sur le port {api_port}", "api")
        server.serve_forever()

    except OSError as error:
        add_event(f"Erreur API controleur : {error}")


class SdnController(app_manager.RyuApp):
    """
    Contrôleur SDN principal basé sur Ryu.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        """
        Initialise le contrôleur.
        """

        super(SdnController, self).__init__(*args, **kwargs)

        global CONTROLLER_APP
        CONTROLLER_APP = self

        # Table MAC : self.mac_to_port[dpid][mac] = port
        self.mac_to_port = {}

        # Switches connectés : self.datapaths[dpid] = datapath
        self.datapaths = {}
        self.seen_hosts = set()
        self.recent_packet_events = {}

        # Charger les règles au démarrage
        with STATE_LOCK:
            STATE["rules"] = load_rules()

        # Lancer la collecte périodique des statistiques
        hub.spawn(self._stats_loop)

        # Lancer l'API HTTP dans un thread séparé
        api_thread = threading.Thread(target=start_api_server, daemon=True)
        api_thread.start()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Appelé lorsqu'un switch OpenFlow se connecte au contrôleur.
        """

        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Enregistrer le switch
        self.datapaths[datapath.id] = datapath
        self.mac_to_port.setdefault(datapath.id, {})

        # Règle table-miss :
        # les paquets inconnus sont envoyés au contrôleur
        match = parser.OFPMatch()

        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]

        self.add_flow(
            datapath=datapath,
            priority=0,
            match=match,
            actions=actions,
        )

        add_event(
            f"Switch S{datapath.id} connecte au controleur Ryu",
            "switch_connected",
            {"switch": datapath.id},
        )

        with STATE_LOCK:
            STATE["switches"][str(datapath.id)] = {
                "dpid": datapath.id,
                "status": "connected",
            }

        # Installer les règles firewall sur ce switch
        self.install_policy_rules(datapath)

    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions,
        idle_timeout=0,
        hard_timeout=0,
        cookie=0,
    ):
        """
        Ajoute une règle OpenFlow dans un switch.
        """

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            cookie=cookie,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )

        datapath.send_msg(flow_mod)

    def delete_policy_rules(self, datapath):
        """
        Supprime les anciennes règles firewall de priorité 100.
        """

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        flow_mod = parser.OFPFlowMod(
            datapath=datapath,
            cookie=1,
            cookie_mask=0xFFFFFFFFFFFFFFFF,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=parser.OFPMatch(),
        )

        datapath.send_msg(flow_mod)

    def install_policy_rules(self, datapath=None):
        """
        Installe les règles firewall de type deny.

        Si datapath est fourni, applique les règles seulement à ce switch.
        Sinon, applique les règles à tous les switches connectés.
        """

        datapaths = [datapath] if datapath else list(self.datapaths.values())

        rules = load_rules()

        with STATE_LOCK:
            STATE["rules"] = rules

        for dp in datapaths:
            # Supprimer les anciennes règles firewall
            self.delete_policy_rules(dp)

            for rule in rules:
                # Appliquer uniquement les règles activées
                if not rule.get("enabled"):
                    continue

                # Appliquer uniquement les règles deny
                if rule.get("action") != "deny":
                    continue

                match_kwargs = {
                    "eth_type": ether_types.ETH_TYPE_IP,
                }

                # IP source
                if rule.get("src_ip"):
                    match_kwargs["ipv4_src"] = rule["src_ip"]

                # IP destination
                if rule.get("dst_ip"):
                    match_kwargs["ipv4_dst"] = rule["dst_ip"]

                # Protocole
                proto = rule.get("proto", "any").lower()

                if proto == "icmp":
                    match_kwargs["ip_proto"] = 1

                elif proto == "tcp":
                    match_kwargs["ip_proto"] = 6

                elif proto == "udp":
                    match_kwargs["ip_proto"] = 17

                match = dp.ofproto_parser.OFPMatch(**match_kwargs)

                # Aucune action = drop
                self.add_flow(
                    datapath=dp,
                    priority=100,
                    match=match,
                    actions=[],
                    idle_timeout=0,
                    hard_timeout=0,
                    cookie=1,
                )
                add_event(
                    f"Flux bloque par politique sur S{dp.id} : {host_label(rule.get('src_ip'))} -> {host_label(rule.get('dst_ip'))}",
                    "flow_blocked",
                    {
                        "switch": dp.id,
                        "rule_id": rule.get("id"),
                        "src_ip": rule.get("src_ip"),
                        "dst_ip": rule.get("dst_ip"),
                        "proto": proto,
                    },
                )

        add_event("Regles de politique appliquees aux switches", "policy_apply")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Gère les Packet-In envoyés par les switches.

        Fonctionnement :
        - apprentissage MAC ;
        - découverte des hôtes ;
        - forwarding L2 ;
        - installation de flux temporaires.
        """

        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Port d'entrée du paquet
        in_port = msg.match["in_port"]

        # Analyse du paquet Ethernet
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Sécurité : ignorer les paquets non Ethernet
        if eth is None:
            return

        # Ignorer LLDP
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst

        # Initialiser la table MAC du switch
        self.mac_to_port.setdefault(dpid, {})

        # Apprendre l'adresse MAC source
        self.mac_to_port[dpid][src] = in_port

        # Détection IP ou ARP pour le dashboard
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        arp_pkt = pkt.get_protocol(arp.arp)
        src_ip = None
        dst_ip = None

        if ip_pkt:
            src_ip = ip_pkt.src
            dst_ip = ip_pkt.dst
            with STATE_LOCK:
                STATE["hosts"][ip_pkt.src] = {
                    "name": host_label(ip_pkt.src),
                    "mac": src,
                    "switch": dpid,
                    "port": in_port,
                }

            if ip_pkt.src not in self.seen_hosts:
                self.seen_hosts.add(ip_pkt.src)
                add_event(
                    f"Hote detecte : {host_label(ip_pkt.src)} ({ip_pkt.src}) sur S{dpid}, port {in_port}",
                    "host_detected",
                    {"ip": ip_pkt.src, "switch": dpid, "port": in_port},
                )

        elif arp_pkt:
            src_ip = arp_pkt.src_ip
            dst_ip = arp_pkt.dst_ip
            with STATE_LOCK:
                STATE["hosts"][arp_pkt.src_ip] = {
                    "name": host_label(arp_pkt.src_ip),
                    "mac": src,
                    "switch": dpid,
                    "port": in_port,
                }
            if arp_pkt.src_ip not in self.seen_hosts:
                self.seen_hosts.add(arp_pkt.src_ip)
                add_event(
                    f"Hote detecte : {host_label(arp_pkt.src_ip)} ({arp_pkt.src_ip}) sur S{dpid}, port {in_port}",
                    "host_detected",
                    {"ip": arp_pkt.src_ip, "switch": dpid, "port": in_port},
                )

        packet_key = (dpid, src_ip or src, dst_ip or dst)
        now = time.time()
        if now - self.recent_packet_events.get(packet_key, 0) > 3:
            self.recent_packet_events[packet_key] = now
            add_event(
                f"Packet-In recu depuis S{dpid} : {host_label(src_ip)} -> {host_label(dst_ip)}",
                "packet_in",
                {"switch": dpid, "src_ip": src_ip, "dst_ip": dst_ip, "in_port": in_port},
            )

        # Trouver le port de sortie
        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)

        actions = [parser.OFPActionOutput(out_port)]
        decision = "flood" if out_port == ofproto.OFPP_FLOOD else "autoriser"
        add_event(
            f"Decision du controleur : {decision} {host_label(src_ip)} -> {host_label(dst_ip)} sur S{dpid}",
            "decision",
            {"switch": dpid, "src_ip": src_ip, "dst_ip": dst_ip, "out_port": out_port},
        )

        # Installer un flux temporaire si la destination est connue
        if out_port != ofproto.OFPP_FLOOD:
            if ip_pkt:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ipv4_src=ip_pkt.src,
                    ipv4_dst=ip_pkt.dst,
                    ip_proto=ip_pkt.proto,
                )
            else:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_src=src,
                    eth_dst=dst,
                )

            self.add_flow(
                datapath=datapath,
                priority=10,
                match=match,
                actions=actions,
                idle_timeout=30,
            )
            add_event(
                f"Flow-Mod installe sur S{dpid} : {host_label(src_ip)} -> {host_label(dst_ip)} via port {out_port}",
                "flow_mod",
                {"switch": dpid, "src_ip": src_ip, "dst_ip": dst_ip, "out_port": out_port},
            )

        # Envoyer le paquet
        data = None

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        packet_out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )

        datapath.send_msg(packet_out)

    def match_to_dict(self, match):
        """
        Convertit un objet OFPMatch Ryu en dictionnaire Python.

        Important :
        Ne jamais utiliser dict(stat.match), car cela peut provoquer :
        KeyError: 0
        """

        result = {}

        fields = getattr(match, "_fields2", [])

        for key, value in fields:
            if isinstance(value, bytes):
                result[key] = value.hex()

            elif isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = value

            elif isinstance(value, (list, tuple)):
                result[key] = [str(item) for item in value]

            else:
                result[key] = str(value)

        return result

    def _stats_loop(self):
        """
        Demande les statistiques de flux aux switches toutes les 5 secondes.
        """

        while True:
            for datapath in list(self.datapaths.values()):
                parser = datapath.ofproto_parser

                request = parser.OFPFlowStatsRequest(datapath)

                datapath.send_msg(request)

            hub.sleep(5)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """
        Traite les statistiques de flux reçues depuis les switches.
        """

        flows = []
        switch_id = ev.msg.datapath.id

        for stat in ev.msg.body:
            # Ignorer la règle table-miss
            if stat.priority == 0:
                continue

            # Correction importante :
            # ne pas faire dict(stat.match)
            match = self.match_to_dict(stat.match)

            proto = ip_proto_name(match.get("ip_proto"))
            src_ip = match.get("ipv4_src")
            dst_ip = match.get("ipv4_dst")
            action = "bloque" if stat.priority >= 100 else "autorise"
            readable = f"{host_label(src_ip)} -> {host_label(dst_ip)}"

            if not src_ip and not dst_ip:
                readable = "Flux Ethernet appris"

            flows.append(
                {
                    "switch": switch_id,
                    "priority": stat.priority,
                    "match": match,
                    "proto": proto,
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "src_name": host_label(src_ip),
                    "dst_name": host_label(dst_ip),
                    "action": action,
                    "readable": readable,
                    "packets": stat.packet_count,
                    "bytes": stat.byte_count,
                    "duration": int(stat.duration_sec),
                }
            )

        with STATE_LOCK:
            other_flows = [
                flow
                for flow in STATE["flows"]
                if flow.get("switch") != switch_id
            ]

            STATE["flows"] = other_flows + flows
            STATE["summary"] = build_summary(
                STATE["flows"],
                STATE.get("summary", {}).get("history", []),
            )
