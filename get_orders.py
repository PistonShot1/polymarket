#!/usr/bin/env python3
"""Authenticate to the Polymarket CLOB API and fetch open orders.

Flow:
  1. L1 auth  — sign with PRIVATE_KEY (the EOA).
  2. L2 auth  — derive (or create) API key/secret/passphrase from the L1 signer.
  3. Call authenticated endpoints (open orders, optionally trades/balances).

Fill in .env (see .env.example) before running.
"""
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

import certifi
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw else default


def build_client() -> ClobClient:
    host = os.getenv("CLOB_HOST", "https://clob.polymarket.com").strip()
    chain_id = env_int("CHAIN_ID", 137)
    private_key = os.getenv("PRIVATE_KEY", "").strip()
    if not private_key or private_key == "0xyour_private_key_here":
        sys.exit("ERROR: PRIVATE_KEY missing. Copy .env.example to .env and set it.")

    sig_type = env_int("SIGNATURE_TYPE", 0)
    funder = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip() or None

    # EOA accounts (sig_type 0) don't need a funder; proxy accounts do.
    if sig_type == 0:
        client = ClobClient(host, key=private_key, chain_id=chain_id)
    else:
        if not funder:
            sys.exit("ERROR: SIGNATURE_TYPE is %d but POLYMARKET_PROXY_ADDRESS is empty." % sig_type)
        client = ClobClient(
            host,
            key=private_key,
            chain_id=chain_id,
            signature_type=sig_type,
            funder=funder,
        )
    return client


def attach_l2_creds(client: ClobClient) -> None:
    key = os.getenv("CLOB_API_KEY", "").strip()
    secret = os.getenv("CLOB_API_SECRET", "").strip()
    passphrase = os.getenv("CLOB_API_PASSPHRASE", "").strip()

    if key and secret and passphrase:
        creds = ApiCreds(api_key=key, api_secret=secret, api_passphrase=passphrase)
        print("Using L2 API creds from .env")
    else:
        # Deterministically derive creds from the L1 signer (creates them if needed).
        creds = client.create_or_derive_api_creds()
        print("Derived L2 API creds from PRIVATE_KEY:")
        print(f"  CLOB_API_KEY={creds.api_key}")
        print(f"  CLOB_API_SECRET={creds.api_secret}")
        print(f"  CLOB_API_PASSPHRASE={creds.api_passphrase}")
    client.set_api_creds(creds)


def fetch_positions(address: str) -> list:
    """Active positions come from the Data API, not the CLOB client.

    GET https://data-api.polymarket.com/positions?user=<funded-address>
    `address` must be the funded wallet (proxy address for email/Magic accounts,
    else the EOA signer). No auth header needed — it's public per-address data.
    """
    base = os.getenv("DATA_API_HOST", "https://data-api.polymarket.com").strip()
    query = urllib.parse.urlencode({
        "user": address,
        "sizeThreshold": "0.1",       # hide dust
        "sortBy": "CURRENT",          # by current value
        "sortDirection": "DESC",
    })
    url = f"{base}/positions?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "polymarket-cli"})
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    load_dotenv()
    client = build_client()
    print(f"Authenticated address: {client.get_address()}")

    attach_l2_creds(client)

    # ok() pings the authenticated server; confirms L2 creds are valid.
    print(f"Server reachable: {client.get_ok()}")

    print("\n=== Open orders ===")
    orders = client.get_orders(OpenOrderParams())
    if not orders:
        print("(none)")
    else:
        print(json.dumps(orders, indent=2))
    print(f"\nTotal open orders: {len(orders)}")

    # Active positions = funded wallet's holdings. Use proxy address if set,
    # otherwise the L1 signer address.
    funder = os.getenv("POLYMARKET_PROXY_ADDRESS", "").strip()
    pos_address = funder or client.get_address()
    print(f"\n=== Active positions (user={pos_address}) ===")
    positions = fetch_positions(pos_address)
    if not positions:
        print("(none)")
    else:
        for p in positions:
            print(
                f"- {p.get('title', '?')} [{p.get('outcome', '?')}] "
                f"size={p.get('size')} avg={p.get('avgPrice')} "
                f"cur={p.get('curPrice')} value={p.get('currentValue')} "
                f"pnl={p.get('cashPnl')} ({p.get('percentPnl')}%)"
            )
    print(f"\nTotal active positions: {len(positions)}")


if __name__ == "__main__":
    main()
