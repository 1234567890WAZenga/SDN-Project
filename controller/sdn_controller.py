#!/usr/bin/env python3
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ether_types, ethernet, icmp, ipv4, packet, tcp, udp
from ryu.ofproto import ofproto_v1_3


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_FILE = os.path.join(BASE_DIR, "policies", "firewall_rules.json")

STATE = {
    "started_at": time.time(),
    "switches": {},
    "hosts": {},
    "events": [],
    "flows": [],
    "rules": [],
}
STATE_LOCK = threading.Lock()
CONTROLLER_APP = None


def add_event(message):
    with STATE_LOCK:
        STATE["events"].insert(0, {"time": time.strftime("%H:%M:%S"), "message": message})
        STATE["events"] = STATE["events"][:80]


def load_rules():
    if not os.path.exists(POLICY_FILE):
        return []
    with open(POLICY_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_rules(rules):
    with open(POLICY_FILE, "w", encoding="utf-8") as handle:
        json.dump(rules, handle, indent=2)


def ip_proto_name(proto):
    if proto == 1:
        return "icmp"
    if proto == 6:
        return "tcp"
    if proto == 17:
        return "udp"
    return "any"


class DashboardApiHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
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
        self._send_json({"ok": True})

    def do_GET(self):
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
        global CONTROLLER_APP
        path = urlparse(self.path).path
        if path == "/api/rules/toggle":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            rule_id = data.get("id")
            rules = load_rules()
            changed = False
            for rule in rules:
                if rule.get("id") == rule_id:
                    rule["enabled"] = not bool(rule.get("enabled"))
                    changed = True
                    add_event(f"Regle {rule_id} -> {'activee' if rule['enabled'] else 'desactivee'}")
                    break
            if not changed:
                self._send_json({"error": "rule not found"}, 404)
                return
            save_rules(rules)
            with STATE_LOCK:
                STATE["rules"] = rules
            if CONTROLLER_APP:
                CONTROLLER_APP.install_policy_rules()
            self._send_json({"ok": True, "rules": rules})
            return
        self._send_json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        return


def start_api_server():
    server = ThreadingHTTPServer(("0.0.0.0", 8080), DashboardApiHandler)
    add_event("API controleur disponible sur le port 8080")
    server.serve_forever()


class SdnController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SdnController, self).__init__(*args, **kwargs)
        global CONTROLLER_APP
        CONTROLLER_APP = self
        self.mac_to_port = {}
        self.datapaths = {}
        with STATE_LOCK:
            STATE["rules"] = load_rules()
        hub.spawn(self._stats_loop)
        thread = threading.Thread(target=start_api_server, daemon=True)
        thread.start()

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath
        self.mac_to_port.setdefault(datapath.id, {})

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        add_event(f"Switch s{datapath.id} connecte")
        with STATE_LOCK:
            STATE["switches"][str(datapath.id)] = {"dpid": datapath.id, "status": "connected"}

        self.install_policy_rules(datapath)

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    def install_policy_rules(self, datapath=None):
        datapaths = [datapath] if datapath else list(self.datapaths.values())
        rules = load_rules()
        with STATE_LOCK:
            STATE["rules"] = rules
        for dp in datapaths:
            self.delete_policy_rules(dp)
            for rule in rules:
                if not rule.get("enabled") or rule.get("action") != "deny":
                    continue
                match_kwargs = {"eth_type": ether_types.ETH_TYPE_IP}
                if rule.get("src_ip"):
                    match_kwargs["ipv4_src"] = rule["src_ip"]
                if rule.get("dst_ip"):
                    match_kwargs["ipv4_dst"] = rule["dst_ip"]
                proto = rule.get("proto", "any").lower()
                if proto == "icmp":
                    match_kwargs["ip_proto"] = 1
                elif proto == "tcp":
                    match_kwargs["ip_proto"] = 6
                elif proto == "udp":
                    match_kwargs["ip_proto"] = 17
                match = dp.ofproto_parser.OFPMatch(**match_kwargs)
                self.add_flow(dp, 100, match, [], idle_timeout=0, hard_timeout=0)
        add_event("Regles de politique appliquees")

    def delete_policy_rules(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            priority=100,
            match=parser.OFPMatch(),
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        arp_pkt = pkt.get_protocol(arp.arp)
        if ip_pkt:
            with STATE_LOCK:
                STATE["hosts"][ip_pkt.src] = {"mac": src, "switch": dpid, "port": in_port}
        elif arp_pkt:
            with STATE_LOCK:
                STATE["hosts"][arp_pkt.src_ip] = {"mac": src, "switch": dpid, "port": in_port}

        out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self.add_flow(datapath, 10, match, actions, idle_timeout=30)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    def _stats_loop(self):
        while True:
            for datapath in list(self.datapaths.values()):
                parser = datapath.ofproto_parser
                req = parser.OFPFlowStatsRequest(datapath)
                datapath.send_msg(req)
            hub.sleep(5)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        flows = []
        for stat in ev.msg.body:
            if stat.priority == 0:
                continue
            match = dict(stat.match)
            proto = ip_proto_name(match.get("ip_proto"))
            flows.append({
                "switch": ev.msg.datapath.id,
                "priority": stat.priority,
                "match": match,
                "proto": proto,
                "packets": stat.packet_count,
                "bytes": stat.byte_count,
                "duration": int(stat.duration_sec),
            })
        with STATE_LOCK:
            other = [f for f in STATE["flows"] if f.get("switch") != ev.msg.datapath.id]
            STATE["flows"] = other + flows
