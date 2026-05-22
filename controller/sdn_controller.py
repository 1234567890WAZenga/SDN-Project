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


# État global exposé au dashboard
STATE = {
    "started_at": time.time(),
    "switches": {},
    "hosts": {},
    "events": [],
    "flows": [],
    "rules": [],
}


# Verrou pour sécuriser les accès concurrents à STATE
STATE_LOCK = threading.Lock()

# Référence globale vers l'application Ryu
CONTROLLER_APP = None


def add_event(message):
    """
    Ajoute un événement visible depuis le dashboard.
    """

    with STATE_LOCK:
        STATE["events"].insert(
            0,
            {
                "time": time.strftime("%H:%M:%S"),
                "message": message,
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


class DashboardApiHandler(BaseHTTPRequestHandler):
    """
    API HTTP interne utilisée par le dashboard.

    Routes :
    - GET  /api/state
    - GET  /api/rules
    - POST /api/rules/toggle
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
                    add_event(f"Regle {rule_id} -> {status}")

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
        server = ReusableThreadingHTTPServer(("0.0.0.0", 8080), DashboardApiHandler)
        add_event("API controleur disponible sur le port 8080")
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

        add_event(f"Switch s{datapath.id} connecte")

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
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            priority=100,
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
                )

        add_event("Regles de politique appliquees")

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

        if ip_pkt:
            with STATE_LOCK:
                STATE["hosts"][ip_pkt.src] = {
                    "mac": src,
                    "switch": dpid,
                    "port": in_port,
                }

        elif arp_pkt:
            with STATE_LOCK:
                STATE["hosts"][arp_pkt.src_ip] = {
                    "mac": src,
                    "switch": dpid,
                    "port": in_port,
                }

        # Trouver le port de sortie
        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)

        actions = [parser.OFPActionOutput(out_port)]

        # Installer un flux temporaire si la destination est connue
        if out_port != ofproto.OFPP_FLOOD:
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

            flows.append(
                {
                    "switch": switch_id,
                    "priority": stat.priority,
                    "match": match,
                    "proto": proto,
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