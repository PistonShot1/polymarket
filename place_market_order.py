#!/usr/bin/env python3
"""Place a MARKET order on Polymarket via the v2 CLOB SDK (deposit wallet / POLY_1271).

A "market order" is a marketable limit order with FOK or FAK type:
  - FOK (Fill-Or-Kill): fill the whole order immediately or cancel.
  - FAK (Fill-And-Kill): fill what's available now, cancel the remainder.
  - BUY  -> `amount` is the USDC (pUSD) dollar amount to spend.
  - SELL -> `amount` is the number of shares to sell.

SAFETY: defaults to a DRY RUN (preview only). Pass --yes to actually submit.

Setup (signature type 3 / deposit wallet):
  - .env has PRIVATE_KEY (owner/session signer) and DEPOSIT_WALLET_ADDRESS (funder).
  - pUSD/USDC funded INTO the deposit wallet, with Exchange approvals set
    (done in the polymarket.com console).

Usage:
  python place_market_order.py --token <TOKEN_ID> --side BUY  --amount 5        # preview $5 buy
  python place_market_order.py --token <TOKEN_ID> --side BUY  --amount 5 --yes  # submit
  python place_market_order.py --token <TOKEN_ID> --side SELL --amount 10 --type FAK --yes
"""
import argparse
import os
import sys

from dotenv import load_dotenv
from py_clob_client_v2 import (
    AssetType,
    BalanceAllowanceParams,
    ClobClient,
    MarketOrderArgsV2,
    OrderType,
    PartialCreateOrderOptions,
    SignatureTypeV2,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Place a Polymarket market order (v2 / POLY_1271).")
    p.add_argument("--token", default=os.getenv("TOKEN_ID", ""), help="Outcome token id.")
    p.add_argument("--side", required=True, choices=["BUY", "SELL"])
    p.add_argument(
        "--amount", required=True, type=float,
        help="BUY: USDC dollars to spend. SELL: number of shares.",
    )
    p.add_argument("--type", default="FOK", choices=["FOK", "FAK"], help="Market order type.")
    p.add_argument("--yes", action="store_true", help="Actually submit. Omit for dry-run preview.")
    return p.parse_args()


def build_trading_client() -> ClobClient:
    host = os.getenv("CLOB_HOST", "https://clob.polymarket.com").strip()
    chain_id = int(os.getenv("CHAIN_ID", "137"))
    private_key = os.getenv("PRIVATE_KEY", "").strip()
    funder = os.getenv("DEPOSIT_WALLET_ADDRESS", "").strip()

    if not private_key or private_key == "0xyour_private_key_here":
        sys.exit("ERROR: PRIVATE_KEY missing in .env.")
    if not funder:
        sys.exit("ERROR: DEPOSIT_WALLET_ADDRESS missing in .env (your funder wallet).")

    # Derive L2 API creds from the signer (creates them server-side if needed).
    temp = ClobClient(host, chain_id=chain_id, key=private_key)
    creds = temp.create_or_derive_api_key()

    return ClobClient(
        host,
        chain_id=chain_id,
        key=private_key,
        creds=creds,
        signature_type=int(SignatureTypeV2.POLY_1271),  # 3
        funder=funder,
    )


def main() -> None:
    load_dotenv()
    args = parse_args()
    if not args.token:
        sys.exit("ERROR: no token id. Pass --token or set TOKEN_ID in .env.")

    client = build_trading_client()
    order_type = OrderType.FOK if args.type == "FOK" else OrderType.FAK

    # Sync the CLOB's balance/allowance cache for the deposit wallet (sig type 3).
    client.update_balance_allowance(
        BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=int(SignatureTypeV2.POLY_1271),
        )
    )
    bal = client.get_balance_allowance(
        BalanceAllowanceParams(
            asset_type=AssetType.COLLATERAL,
            signature_type=int(SignatureTypeV2.POLY_1271),
        )
    )

    # Market metadata + a slippage-aware fill estimate.
    tick_size = client.get_tick_size(args.token)
    neg_risk = client.get_neg_risk(args.token)
    est_price = client.calculate_market_price(args.token, args.side, args.amount, order_type)

    print("=== Market order preview ===")
    print(f"  token        : {args.token}")
    print(f"  side         : {args.side}")
    unit = "USDC" if args.side == "BUY" else "shares"
    print(f"  amount       : {args.amount} {unit}")
    print(f"  order type   : {args.type} (market)")
    print(f"  tick size    : {tick_size}")
    print(f"  neg risk     : {neg_risk}")
    print(f"  est. fill px : {est_price}")
    print(f"  collateral   : {bal}")

    if not args.yes:
        print("\nDRY RUN — nothing submitted. Re-run with --yes to place this order.")
        return

    print("\nSubmitting...")
    resp = client.create_and_post_market_order(
        MarketOrderArgsV2(
            token_id=args.token,
            amount=args.amount,
            side=args.side,
            order_type=order_type,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk),
        order_type=order_type,
    )
    print("Response:", resp)
    status = resp.get("status") if isinstance(resp, dict) else getattr(resp, "status", None)
    order_id = resp.get("orderID") if isinstance(resp, dict) else getattr(resp, "orderID", None)
    print(f"Order ID: {order_id}")
    print(f"Status:   {status}")


if __name__ == "__main__":
    main()
