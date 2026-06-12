#!/usr/bin/env python3
"""Local web UI for browsing Polymarket markets and placing BUY market orders.

Run:
  ./.venv/bin/python app.py
  open http://127.0.0.1:5000

Safety:
  - Binds to localhost only.
  - Real order submission requires env TRADING_ENABLED=1. Without it the
    /api/order endpoint refuses and only preview works — prevents accidents.
"""
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory

load_dotenv()

import polyclient  # noqa: E402  (after load_dotenv so env is populated)

app = Flask(__name__, static_folder="static", static_url_path="")
TRADING_ENABLED = os.getenv("TRADING_ENABLED", "").strip() == "1"


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/config")
def config():
    return jsonify({"tradingEnabled": TRADING_ENABLED})


@app.get("/api/markets")
def markets():
    search = request.args.get("search", "")
    limit = min(int(request.args.get("limit", "50")), 100)
    offset = max(int(request.args.get("offset", "0")), 0)
    try:
        return jsonify(polyclient.fetch_markets(search, limit, offset))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 502


@app.get("/api/positions")
def positions():
    try:
        return jsonify(polyclient.get_positions())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


@app.get("/api/orders")
def open_orders():
    try:
        return jsonify(polyclient.get_open_orders())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


@app.get("/api/balance")
def balance():
    try:
        return jsonify(polyclient.get_collateral_balance())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


@app.get("/api/profiles")
def list_profiles():
    return jsonify(polyclient.load_profiles())


@app.post("/api/profiles")
def add_profile():
    d = request.get_json(force=True)
    try:
        return jsonify(polyclient.upsert_profile(d["address"], d.get("label", "")))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


@app.delete("/api/profiles")
def delete_profile():
    addr = request.args.get("address", "")
    return jsonify(polyclient.remove_profile(addr))


@app.get("/api/copy/positions")
def copy_positions():
    try:
        return jsonify(polyclient.copy_positions())
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


@app.post("/api/preview")
def preview():
    d = request.get_json(force=True)
    try:
        return jsonify(polyclient.preview_order(
            d["tokenId"], d.get("side", "BUY"), float(d["amount"]), d.get("type", "FOK")
        ))
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


@app.post("/api/order")
def order():
    if not TRADING_ENABLED:
        return jsonify({"error": "Trading disabled. Start with TRADING_ENABLED=1 to submit real orders."}), 403
    d = request.get_json(force=True)
    if not d.get("confirm"):
        return jsonify({"error": "Missing confirm flag."}), 400
    try:
        resp = polyclient.place_market_order(
            d["tokenId"], d.get("side", "BUY"), float(d["amount"]), d.get("type", "FOK")
        )
        return jsonify(resp)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    # Localhost only. Do not expose this to a network — it can move real funds.
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
