#!/usr/bin/env python3
import copy
import json
import os
import subprocess
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request


BASE_DIR = Path(__file__).resolve().parents[1]
TOPOLOGY_CONFIG = BASE_DIR / "topology_config.json"
CONTROLLER_API = os.environ.get("CONTROLLER_API", "http://127.0.0.1:8080")
MININET_API = os.environ.get("MININET_API", "http://127.0.0.1:8090")
RESTART_TOPOLOGY_SCRIPT = BASE_DIR / "scripts" / "restart_topology.sh"

app = Flask(__name__)


def read_topology_config():
    with TOPOLOGY_CONFIG.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_topology_config(config):
    with TOPOLOGY_CONFIG.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def validated_topology_update(payload):
    current = read_topology_config()
    updated = copy.deepcopy(current)
    topology = updated.setdefault("topology", {})

    switches = int(payload.get("switches", topology.get("switches", 2)))
    hosts_per_switch = int(payload.get("hosts_per_switch", topology.get("hosts_per_switch", 2)))

    if switches < 1 or switches > 12:
        raise ValueError("Le nombre de switches doit être entre 1 et 12.")
    if hosts_per_switch < 1 or hosts_per_switch > 20:
        raise ValueError("Le nombre d'hôtes par switch doit être entre 1 et 20.")

    topology["type"] = payload.get("type", topology.get("type", "linear"))
    topology["switches"] = switches
    topology["hosts_per_switch"] = hosts_per_switch
    topology["servers"] = []

    return updated


@app.route("/")
def index():
    return render_template("index.html", controller_api=CONTROLLER_API)


@app.route("/api/state")
def state():
    try:
        response = requests.get(f"{CONTROLLER_API}/api/state", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error)}), 503


@app.route("/api/rules")
def rules():
    try:
        response = requests.get(f"{CONTROLLER_API}/api/rules", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error), "rules": []}), 503


@app.route("/api/rules/toggle", methods=["POST"])
def toggle_rule():
    try:
        response = requests.post(
            f"{CONTROLLER_API}/api/rules/toggle",
            json=request.get_json(force=True),
            timeout=3,
        )
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error)}), 503


@app.route("/api/rules/create", methods=["POST"])
def create_rule():
    try:
        response = requests.post(
            f"{CONTROLLER_API}/api/rules/create",
            json=request.get_json(force=True),
            timeout=3,
        )
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error)}), 503


@app.route("/api/rules/delete", methods=["POST"])
def delete_rule():
    try:
        response = requests.post(
            f"{CONTROLLER_API}/api/rules/delete",
            json=request.get_json(force=True),
            timeout=3,
        )
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error)}), 503


@app.route("/api/topology-config")
def topology_config():
    try:
        return jsonify({"ok": True, "config": read_topology_config()})
    except (OSError, json.JSONDecodeError) as error:
        return jsonify({"ok": False, "error": str(error)}), 500


@app.route("/api/topology-config", methods=["POST"])
def save_topology_config():
    try:
        config = validated_topology_update(request.get_json(force=True))
        write_topology_config(config)
        return jsonify(
            {
                "ok": True,
                "config": config,
                "message": "Configuration sauvegardée. Relance la topologie Mininet pour appliquer les changements.",
            }
        )
    except (ValueError, OSError, json.JSONDecodeError) as error:
        return jsonify({"ok": False, "error": str(error)}), 400


@app.route("/api/mininet/status")
def mininet_status():
    try:
        response = requests.get(f"{MININET_API}/api/status", timeout=2)
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error)}), 503


@app.route("/api/mininet/command", methods=["POST"])
def mininet_command():
    try:
        response = requests.post(
            f"{MININET_API}/api/command",
            json=request.get_json(force=True),
            timeout=30,
        )
        return jsonify(response.json()), response.status_code
    except requests.RequestException as error:
        return jsonify({"ok": False, "error": str(error)}), 503


@app.route("/api/mininet/restart", methods=["POST"])
def restart_mininet():
    command = ["sudo", "-n", str(RESTART_TOPOLOGY_SCRIPT)]
    try:
        process = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=40,
        )
    except subprocess.TimeoutExpired:
        return jsonify(
            {
                "ok": False,
                "error": "Le redemarrage de Mininet a depasse le delai.",
                "hint": "Verifie logs/topology.log dans la VM.",
            }
        ), 504
    except OSError as error:
        return jsonify({"ok": False, "error": str(error)}), 500

    output = (process.stdout or "") + (process.stderr or "")
    if process.returncode != 0:
        hint = (
            "Lance une fois : sudo ./scripts/install_dashboard_sudoers.sh "
            "pour autoriser le dashboard a relancer Mininet sans mot de passe."
        )
        return jsonify({"ok": False, "error": output.strip() or hint, "hint": hint}), 500

    return jsonify({"ok": True, "output": output.strip()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=False)
