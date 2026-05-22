#!/usr/bin/env python3
import os

import requests
from flask import Flask, jsonify, render_template, request


CONTROLLER_API = os.environ.get("CONTROLLER_API", "http://127.0.0.1:8080")

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", controller_api=CONTROLLER_API)


@app.route("/api/state")
def state():
    response = requests.get(f"{CONTROLLER_API}/api/state", timeout=2)
    return jsonify(response.json())


@app.route("/api/rules")
def rules():
    response = requests.get(f"{CONTROLLER_API}/api/rules", timeout=2)
    return jsonify(response.json())


@app.route("/api/rules/toggle", methods=["POST"])
def toggle_rule():
    response = requests.post(
        f"{CONTROLLER_API}/api/rules/toggle",
        json=request.get_json(force=True),
        timeout=3,
    )
    return jsonify(response.json()), response.status_code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
