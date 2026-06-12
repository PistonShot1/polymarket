"""Shared Polymarket helpers: market listing (Gamma) + v2 trading client (POLY_1271)."""
import json
import os
import ssl
import urllib.parse
import urllib.request
from functools import lru_cache

import certifi
from py_clob_client_v2 import (
    AssetType,
    BalanceAllowanceParams,
    ClobClient,
    MarketOrderArgsV2,
    OrderType,
    PartialCreateOrderOptions,
    SignatureTypeV2,
)

CLOB_HOST = os.getenv("CLOB_HOST", "https://clob.polymarket.com").strip()
GAMMA_HOST = os.getenv("GAMMA_HOST", "https://gamma-api.polymarket.com").strip()
DATA_API_HOST = os.getenv("DATA_API_HOST", "https://data-api.polymarket.com").strip()
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))
SIG_TYPE = int(SignatureTypeV2.POLY_1271)  # 3

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "polymarket-webui"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------- market data
def fetch_markets(search: str = "", limit: int = 50, offset: int = 0) -> list:
    """List tradable markets from the Gamma API, normalized for the UI."""
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(limit),
        "offset": str(offset),
        "order": "volume24hr",
        "ascending": "false",
    }
    url = f"{GAMMA_HOST}/markets?{urllib.parse.urlencode(params)}"
    raw = _get_json(url)

    needle = search.lower().strip()
    out = []
    for m in raw:
        if not m.get("enableOrderBook") or not m.get("acceptingOrders"):
            continue
        if needle and needle not in (m.get("question", "").lower()):
            continue
        try:
            token_ids = json.loads(m.get("clobTokenIds") or "[]")
            outcomes = json.loads(m.get("outcomes") or "[]")
            prices = json.loads(m.get("outcomePrices") or "[]")
        except json.JSONDecodeError:
            continue
        if not token_ids or len(token_ids) != len(outcomes):
            continue
        out.append({
            "question": m.get("question"),
            "conditionId": m.get("conditionId"),
            "negRisk": bool(m.get("negRisk")),
            "tickSize": str(m.get("orderPriceMinTickSize")),
            "outcomes": [
                {
                    "name": outcomes[i],
                    "tokenId": token_ids[i],
                    "price": prices[i] if i < len(prices) else None,
                }
                for i in range(len(token_ids))
            ],
        })
    return out


# ---------------------------------------------------------------- clob clients
@lru_cache(maxsize=1)
def get_public_client() -> ClobClient:
    """Unauthenticated client for orderbook/price reads."""
    return ClobClient(CLOB_HOST, chain_id=CHAIN_ID)


@lru_cache(maxsize=1)
def get_trading_client() -> ClobClient:
    """Authenticated deposit-wallet client (signature type 3). Needs env creds."""
    private_key = os.getenv("PRIVATE_KEY", "").strip()
    funder = os.getenv("DEPOSIT_WALLET_ADDRESS", "").strip()
    if not private_key or private_key == "0xyour_private_key_here":
        raise RuntimeError("PRIVATE_KEY missing in .env")
    if not funder:
        raise RuntimeError("DEPOSIT_WALLET_ADDRESS missing in .env")

    temp = ClobClient(CLOB_HOST, chain_id=CHAIN_ID, key=private_key)
    creds = temp.create_or_derive_api_key()
    return ClobClient(
        CLOB_HOST,
        chain_id=CHAIN_ID,
        key=private_key,
        creds=creds,
        signature_type=SIG_TYPE,
        funder=funder,
    )


def _order_type(name: str) -> OrderType:
    return OrderType.FOK if name.upper() == "FOK" else OrderType.FAK


# ---------------------------------------------------------------- order ops
def preview_order(token_id: str, side: str, amount: float, order_type: str = "FOK") -> dict:
    """Public preview: tick size, neg risk, slippage-aware estimated fill price."""
    c = get_public_client()
    return {
        "tokenId": token_id,
        "side": side,
        "amount": amount,
        "tickSize": c.get_tick_size(token_id),
        "negRisk": c.get_neg_risk(token_id),
        "estPrice": c.calculate_market_price(token_id, side, amount, _order_type(order_type)),
    }


def get_collateral_balance() -> dict:
    c = get_trading_client()
    params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=SIG_TYPE)
    c.update_balance_allowance(params)
    return {"collateral": c.get_balance_allowance(params)}


def get_open_orders() -> list:
    """Resting (open) orders for the authenticated account."""
    return get_trading_client().get_open_orders()


def fetch_positions(address: str) -> list:
    """Active positions for ANY wallet address, via the public Data API."""
    query = urllib.parse.urlencode({
        "user": address,
        "sizeThreshold": "0.1",
        "sortBy": "CURRENT",
        "sortDirection": "DESC",
    })
    return _get_json(f"{DATA_API_HOST}/positions?{query}")


def get_positions() -> list:
    """Active positions for the funder (deposit) wallet."""
    funder = os.getenv("DEPOSIT_WALLET_ADDRESS", "").strip()
    if not funder:
        raise RuntimeError("DEPOSIT_WALLET_ADDRESS missing in .env")
    return fetch_positions(funder)


# ---------------------------------------------------------------- copy-trade profiles
PROFILES_PATH = os.path.join(os.path.dirname(__file__), "profiles.json")


def load_profiles() -> list:
    if not os.path.exists(PROFILES_PATH):
        return []
    with open(PROFILES_PATH) as f:
        return json.load(f)


def save_profiles(profiles: list) -> None:
    with open(PROFILES_PATH, "w") as f:
        json.dump(profiles, f, indent=2)


def upsert_profile(address: str, label: str = "") -> list:
    address = address.strip().lower()
    if not address.startswith("0x") or len(address) != 42:
        raise ValueError("Invalid address (expected 0x + 40 hex chars).")
    profiles = load_profiles()
    for p in profiles:
        if p["address"] == address:
            p["label"] = label
            break
    else:
        profiles.append({"address": address, "label": label})
    save_profiles(profiles)
    return profiles


def remove_profile(address: str) -> list:
    address = address.strip().lower()
    profiles = [p for p in load_profiles() if p["address"] != address]
    save_profiles(profiles)
    return profiles


def copy_positions() -> list:
    """For each tracked profile, return their active positions (token id = `asset`)."""
    result = []
    for p in load_profiles():
        entry = {"address": p["address"], "label": p.get("label", "")}
        try:
            positions = fetch_positions(p["address"])
            entry["positions"] = [
                {
                    "tokenId": pos.get("asset"),
                    "title": pos.get("title"),
                    "outcome": pos.get("outcome"),
                    "size": pos.get("size"),
                    "avgPrice": pos.get("avgPrice"),
                    "curPrice": pos.get("curPrice"),
                    "currentValue": pos.get("currentValue"),
                    "percentPnl": pos.get("percentPnl"),
                    "negRisk": bool(pos.get("negativeRisk")),
                    "slug": pos.get("slug"),
                }
                for pos in positions
            ]
        except Exception as e:  # noqa: BLE001
            entry["error"] = str(e)
            entry["positions"] = []
        result.append(entry)
    return result


def place_market_order(token_id: str, side: str, amount: float, order_type: str = "FOK") -> dict:
    """Submit a real market order. Caller is responsible for confirmation/guards."""
    c = get_trading_client()
    ot = _order_type(order_type)
    tick_size = c.get_tick_size(token_id)
    neg_risk = c.get_neg_risk(token_id)
    resp = c.create_and_post_market_order(
        MarketOrderArgsV2(token_id=token_id, amount=amount, side=side, order_type=ot),
        options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        order_type=ot,
    )
    return resp if isinstance(resp, dict) else {"raw": str(resp)}
